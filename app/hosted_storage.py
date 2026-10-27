"""Native PostgreSQL tables, transaction-local actor scope and forced RLS.

An actor locks only its registry row; local decisions and outgoing messages
commit together. The trusted host selects the actor. RLS protects omitted scope
predicates, not arbitrary SQL execution or compromise of database credentials.
"""
from contextlib import ExitStack
import re
import threading

from postgres_schema import TABLE, LEGACY_TABLE, DATA_SCHEMA, initialize


def _key(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 200 or '\x00' in value:
        raise ValueError('A nonempty bounded node storage key is required')
    return value


def _bindings(statement):
    """Translate DB-API bind markers only, never interpolate argument values."""
    result, quote, i = [], None, 0
    while i < len(statement):
        char = statement[i]
        if char == '%':
            # psycopg interprets percent bind syntax even inside SQL literals.
            result.append('%%')
        elif quote:
            result.append(char)
            if char == quote:
                if i + 1 < len(statement) and statement[i + 1] == quote:
                    result.append(statement[i + 1])
                    i += 1
                else:
                    quote = None
        elif char in ("'", '"'):
            quote = char
            result.append(char)
        elif char == '?':
            result.append('%s')
        else:
            result.append('%%' if char == '%' else char)
        i += 1
    return ''.join(result)


class MaterializedCursor:
    """Rows remain usable after the short pooled transaction has committed."""
    def __init__(self, cursor, statement, row_factory=None):
        self.rowcount, self.lastrowid = cursor.rowcount, None
        self.description, self._rows, self._index = None, [], 0
        if cursor.description is not None:
            hide = bool(re.search(r'\bSELECT\s+(?:\w+\.)?\*', statement, re.I))
            indices = [i for i, col in enumerate(cursor.description)
                       if not hide or col.name not in ('owner_node_id', 'rowid')]
            self.description = [cursor.description[i] for i in indices]
            for row in cursor.fetchall():
                values = tuple(row[i] for i in indices)
                self._rows.append(row_factory(self, values) if row_factory else values)

    def fetchone(self):
        if self._index == len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def fetchall(self):
        rows = self._rows[self._index:]
        self._index = len(self._rows)
        return rows

    def fetchmany(self, size=1):
        return [row for _ in range(size) if (row := self.fetchone()) is not None]

    def __iter__(self):
        return self

    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row


class PgStoreFactory:
    """Privileged registry/provisioning; never passed to clearing algorithms."""
    def __init__(self, dsn, *, max_connections=5, timeout=15):
        from psycopg_pool import ConnectionPool
        self._pool = ConnectionPool(
            conninfo=dsn, min_size=0, max_size=max_connections, timeout=timeout,
            kwargs={'autocommit': True, 'options':
                    '-c statement_timeout=30000 -c lock_timeout=5000 '
                    '-c idle_in_transaction_session_timeout=30000'},
            max_idle=30, open=True)

    def initialize(self):
        with self._pool.connection() as connection, connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(hashtext('ledgerloops-native-schema-v1'))")
            initialize(connection)

    @staticmethod
    def _check_legacy(connection, key):
        exists = connection.execute('SELECT to_regclass(%s)', ('public.' + LEGACY_TABLE,)).fetchone()[0]
        if exists:
            old = connection.execute(f'SELECT version FROM public.{LEGACY_TABLE} WHERE node_id=%s', (key,)).fetchone()
            if old:
                migrated = connection.execute(f'SELECT legacy_snapshot_version FROM public.{TABLE} WHERE node_id=%s', (key,)).fetchone()
                if not migrated or migrated[0] is None:
                    raise RuntimeError('Legacy snapshot requires explicit offline migration before use')
                if migrated[0] != old[0]:
                    raise RuntimeError('Legacy snapshot changed after migration; refusing split-brain state')

    def create(self, node_id):
        node_id = _key(node_id)
        with self._pool.connection() as connection, connection.transaction():
            self._check_legacy(connection, node_id)
            connection.execute(f'INSERT INTO public.{TABLE}(node_id) VALUES(%s) ON CONFLICT DO NOTHING', (node_id,))

    def assert_ready(self):
        """Release gate: never start a partially imported hosted installation."""
        with self._pool.connection() as connection:
            if not connection.execute('SELECT to_regclass(%s)', ('public.' + LEGACY_TABLE,)).fetchone()[0]:
                return
            pending = connection.execute(f'''SELECT EXISTS(
                SELECT 1 FROM public.{LEGACY_TABLE} old
                LEFT JOIN public.{TABLE} native ON native.node_id=old.node_id
                WHERE native.legacy_snapshot_version IS DISTINCT FROM old.version
                   OR native.legacy_snapshot_sha256 IS NULL)''').fetchone()[0]
            if pending:
                raise RuntimeError('Complete offline migration of all legacy scopes is required before release')

    def connection(self, node_id):
        return PostgresConnection(self._pool, _key(node_id))

    def list_nodes(self):
        with self._pool.connection() as connection:
            return [row[0] for row in connection.execute(f'SELECT node_id FROM public.{TABLE} ORDER BY node_id')]

    def node_versions(self):
        with self._pool.connection() as connection:
            return dict(connection.execute(f'SELECT node_id,version FROM public.{TABLE} ORDER BY node_id'))

    def close(self):
        self._pool.close()


class PostgresConnection:
    dialect = 'postgres'

    def __init__(self, pool, node_id):
        self._pool, self._node_id = pool, node_id
        self._lock, self._depth = threading.RLock(), 0
        self._closed, self._rollback_only = False, False
        self._stack, self._pg, self.row_factory = None, None, None

    def __enter__(self):
        self._lock.acquire()
        try:
            if self._closed:
                raise RuntimeError('Cannot operate on a closed database')
            if self._depth == 0:
                self._stack = ExitStack()
                try:
                    self._pg = self._stack.enter_context(self._pool.connection())
                    self._stack.enter_context(self._pg.transaction())
                    role = self._pg.execute('''SELECT rolsuper,rolbypassrls FROM pg_roles
                        WHERE rolname=current_user''').fetchone()
                    if any(role):
                        raise RuntimeError('Hosted actors require a non-superuser, non-BYPASSRLS database role')
                    self._pg.execute('SET LOCAL synchronous_commit = on')
                    self._pg.execute("SELECT set_config('ledgerloops.owner_node_id', %s, true)", (self._node_id,))
                    self._pg.execute("SELECT set_config('ledgerloops.dirty', '', true)")
                    self._pg.execute(f'SET LOCAL search_path = {DATA_SCHEMA}, pg_catalog')
                    PgStoreFactory._check_legacy(self._pg, self._node_id)
                    row = self._pg.execute(f'SELECT version FROM public.{TABLE} WHERE node_id=%s FOR UPDATE', (self._node_id,)).fetchone()
                    if row is None:
                        raise ValueError('Node storage has not been provisioned')
                    self._rollback_only = False
                except BaseException:
                    import sys
                    self._discard(*sys.exc_info())
                    raise
            self._depth += 1
            return self
        except BaseException:
            self._lock.release()
            raise

    def _discard(self, exc_type=None, exc=None, traceback=None):
        stack, self._stack = self._stack, None
        self._pg = None
        if stack is not None:
            stack.__exit__(exc_type, exc, traceback)

    def __exit__(self, exc_type, exc, traceback):
        try:
            self._depth -= 1
            if exc_type is not None:
                self._rollback_only = True
            if self._depth:
                return False
            if self._rollback_only:
                if exc_type is None:
                    error = RuntimeError('Nested node transaction was rolled back')
                    self._discard(type(error), error, None)
                    raise error
                self._discard(exc_type, exc, traceback)
                return False
            try:
                if self._pg.execute("SELECT current_setting('ledgerloops.dirty', true)").fetchone()[0] == '1':
                    self._pg.execute(f'''UPDATE public.{TABLE} SET version=version+1,
                        updated_at=CURRENT_TIMESTAMP WHERE node_id=%s''', (self._node_id,))
            except BaseException:
                import sys
                self._discard(*sys.exc_info())
                raise
            self._discard()
            return False
        finally:
            self._lock.release()

    def execute(self, statement, parameters=()):
        # SQL here is trusted application code, not a browser query language.
        # Keep accidental infrastructure references out of this capability;
        # database RLS separately enforces all financial row ownership.
        identifiers = re.sub(r"'(?:''|[^'])*'", "''", statement)
        if (not re.match(r'^\s*(SELECT|INSERT|UPDATE|DELETE|WITH)\b', statement, re.I)
                or re.search(r'\bset_config\s*\(', identifiers, re.I)
                or re.search(r'\b(public|information_schema|pg_catalog|ledgerloops_nodes|ledgerloops_node_snapshots)\b',
                             identifiers, re.I)):
            raise ValueError('Schema, scope and transaction controls are infrastructure-only')
        with self._lock:
            if not self._depth:
                with self:
                    return self.execute(statement, parameters)
            cursor = self._pg.execute(_bindings(statement), parameters)
            return MaterializedCursor(cursor, statement, self.row_factory)

    def executemany(self, statement, parameters):
        with self:
            for values in parameters:
                self.execute(statement, values)

    def executescript(self, script):
        raise ValueError('Native schema is provisioned by release migrations')

    @property
    def in_transaction(self):
        return self._depth > 0

    def close(self):
        with self._lock:
            if self._depth:
                raise RuntimeError('Cannot close an active node transaction')
            self._closed = True
