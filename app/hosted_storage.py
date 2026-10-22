"""Authoritative PostgreSQL storage for isolated hosted TEST-node ledgers.

Each node runs its existing SQLite statements against its own in-memory database.
The durable database is a PostgreSQL row containing that node's SQLite image.
An outer transaction locks ONLY that row, reloads it, performs local work, and
atomically publishes a new image/version before returning. Local SQLite files
are never authoritative. Crashes before commit leave the old image; uncertain
commit results are resolved by reloading PostgreSQL on the next operation.

This intentionally trades O(node-state-size) I/O for exact SQLite compatibility
in a small TEST alpha. It is not the scalable native PostgreSQL ledger design.
The fixed-key adapter is a trusted software capability, not a Python sandbox:
the hosting operator and database administrator retain access to all records.
"""
from contextlib import ExitStack
import sqlite3
import threading


TABLE = 'ledgerloops_node_snapshots'


class MaterializedCursor:
    """Rows outlive the short PostgreSQL transaction and in-memory connection."""

    def __init__(self, cursor):
        self.description = cursor.description
        self.rowcount = cursor.rowcount
        self.lastrowid = cursor.lastrowid
        self._rows = cursor.fetchall() if self.description is not None else []
        self._index = 0

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
        rows = self._rows[self._index:self._index+size]
        self._index += len(rows)
        return rows

    def __iter__(self):
        return self

    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row


def _key(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 200 or '\x00' in value:
        raise ValueError('A nonempty bounded node storage key is required')
    return value


def _empty_image():
    with sqlite3.connect(':memory:') as db:
        # Materialize an otherwise empty SQLite database without adding a table.
        db.execute('PRAGMA user_version=1')
        image = db.serialize()
    db.close()
    return image


class PgStoreFactory:
    """Privileged infrastructure provisioning, never an actor decision input.

    Construct once per web/worker process; do not share pools across fork().
    initialize() belongs in release/provisioning, not an untrusted node request.
    create()/list_nodes() are registry operations outside the clearing algorithm.
    Actors receive connection(key), not this factory or a PostgreSQL cursor.
    """

    def __init__(self, dsn, *, max_connections=5, timeout=15):
        from psycopg_pool import ConnectionPool
        self._pool = ConnectionPool(
            conninfo=dsn, min_size=0, max_size=max_connections, timeout=timeout,
            kwargs={'autocommit': True}, open=True,
        )

    def initialize(self):
        with self._pool.connection() as connection:
            connection.execute(f'''CREATE TABLE IF NOT EXISTS {TABLE} (
                node_id TEXT PRIMARY KEY,
                version BIGINT NOT NULL DEFAULT 0,
                image BYTEA NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )''')

    def create(self, node_id):
        node_id = _key(node_id)
        with self._pool.connection() as connection:
            connection.execute(
                f'INSERT INTO {TABLE}(node_id, image) VALUES (%s, %s) '
                'ON CONFLICT (node_id) DO NOTHING', (node_id, _empty_image()))

    def connection(self, node_id):
        return PostgresSnapshotConnection(self._pool, _key(node_id))

    def list_nodes(self):
        """Infrastructure scheduling only; never pass its result to nodes."""
        with self._pool.connection() as connection:
            return [row[0] for row in connection.execute(
                f'SELECT node_id FROM {TABLE} ORDER BY node_id')]

    def close(self):
        self._pool.close()


class PostgresSnapshotConnection:
    """SQLite-compatible, fixed-node capability with durable local transactions.

    SQLite SQL can access only this node's in-memory tables. ATTACH/DETACH and
    extension loading are disabled. Every operation outside an explicit context
    becomes its own transaction. Use ``with db:`` for related read/write/outbox
    work. There is no API to settle several nodes in a shared transaction.
    """

    def __init__(self, pool, node_id):
        self._pool = pool
        self._node_id = node_id
        self._lock = threading.RLock()
        self._depth = 0
        self._closed = False
        self._rollback_only = False
        self._stack = None
        self._sqlite = None
        self.row_factory = None

    @property
    def row_factory(self):
        return self._row_factory

    @row_factory.setter
    def row_factory(self, value):
        with self._lock:
            self._row_factory = value
            if self._sqlite is not None:
                self._sqlite.row_factory = value

    @staticmethod
    def _authorize(action, arg1, arg2, database, trigger):
        if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION and str(arg2).lower() == 'load_extension':
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def __enter__(self):
        self._lock.acquire()
        try:
            if self._closed:
                raise sqlite3.ProgrammingError('Cannot operate on a closed database')
            if self._depth == 0:
                self._stack = ExitStack()
                try:
                    self._pg = self._stack.enter_context(self._pool.connection())
                    self._stack.enter_context(self._pg.transaction())
                    # The PostgreSQL commit, not SQLite PRAGMAs, is durability.
                    self._pg.execute('SET LOCAL synchronous_commit = on')
                    row = self._pg.execute(
                        f'SELECT version, image FROM {TABLE} WHERE node_id=%s FOR UPDATE',
                        (self._node_id,)).fetchone()
                    if row is None:
                        raise ValueError('Node storage has not been provisioned')
                    self._version, self._before = row[0], bytes(row[1])
                    self._sqlite = sqlite3.connect(':memory:', check_same_thread=False)
                    self._sqlite.deserialize(self._before)
                    self._sqlite.row_factory = self.row_factory
                    self._sqlite.set_authorizer(self._authorize)
                    self._sqlite.execute('BEGIN')
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
        """Drop every local view after success, failure or uncertain PG commit."""
        sqlite_db, stack = self._sqlite, self._stack
        self._sqlite, self._stack = None, None
        self._pg = None
        try:
            if sqlite_db is not None:
                sqlite_db.close()
        finally:
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
                    exc = sqlite3.OperationalError('Nested node transaction was rolled back')
                    self._discard(type(exc), exc, None)
                    raise exc
                self._discard(exc_type, exc, traceback)
                return False
            try:
                self._sqlite.commit()
                image = self._sqlite.serialize()
                if image != self._before:
                    updated = self._pg.execute(
                        f'UPDATE {TABLE} SET image=%s, version=version+1, '
                        'updated_at=CURRENT_TIMESTAMP WHERE node_id=%s AND version=%s',
                        (image, self._node_id, self._version))
                    if updated.rowcount != 1:
                        raise RuntimeError('Node storage version changed under its lock')
            except BaseException:
                import sys
                self._discard(*sys.exc_info())
                raise
            # ExitStack commits PostgreSQL before the caller sees success.
            self._discard()
            return False
        finally:
            self._lock.release()

    def _call(self, method, *args):
        with self._lock:
            if self._depth:
                return MaterializedCursor(getattr(self._sqlite, method)(*args))
            with self:
                return MaterializedCursor(getattr(self._sqlite, method)(*args))

    def execute(self, sql, parameters=()):
        return self._call('execute', sql, parameters)

    def executemany(self, sql, parameters):
        return self._call('executemany', sql, parameters)

    def executescript(self, script):
        # executescript's implicit SQLite commit cannot publish to PostgreSQL;
        # the enclosing outer PG transaction still commits the complete image.
        return self._call('executescript', script)

    @property
    def in_transaction(self):
        return self._depth > 0

    def close(self):
        with self._lock:
            if self._depth:
                raise sqlite3.ProgrammingError('Cannot close an active node transaction')
            self._closed = True
