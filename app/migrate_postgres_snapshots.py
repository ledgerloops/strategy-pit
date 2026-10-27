#!/usr/bin/env python3
"""Offline, lossless export of legacy node images into native PostgreSQL tables.

SQLite is used only by this explicitly invoked migration, never by hosted runtime
storage. Stop every old web/worker process before running. Original images are
retained and fenced against old-writer updates after successful migration.
"""
import argparse
import hashlib
import json
import os
import sqlite3


def _definitions():
    from postgres_schema import TABLES
    return TABLES


def _scope_tables(scope):
    names = set(_definitions())
    if scope == 'accounts' or scope.endswith(':accounts'):
        return {name for name in names if name.startswith('auth_')}
    if scope == 'enrollment' or scope.endswith(':enrollment'):
        return {'channel_keys'}
    return {name for name in names if not name.startswith('auth_') and name != 'channel_keys'}


def export_image(image, scope):
    """Read only known stored columns; never execute a snapshot's schema SQL."""
    definitions = _definitions()
    allowed = _scope_tables(scope)
    db = sqlite3.connect(':memory:')
    try:
        db.deserialize(bytes(image))
        db.execute('PRAGMA query_only=ON')
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('Legacy snapshot integrity check failed')
        if db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('view','trigger') LIMIT 1").fetchone():
            raise ValueError('Legacy snapshot has unsupported views or triggers')
        names = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if names - allowed:
            raise ValueError('Legacy snapshot has unsupported or out-of-scope tables')
        exported = {}
        for table in sorted(names):
            expected = tuple(definitions[table]['columns'])
            columns = tuple(row[1] for row in db.execute(f'PRAGMA table_info("{table}")'))
            if set(columns) - set(expected):
                raise ValueError(f'Legacy {table} has unsupported columns')
            missing = set(expected) - set(columns)
            invitation_defaults = {'peer_name', 'max_trust', 'accepted_max_trust'}
            if missing and (table != 'hosted_invites' or missing - invitation_defaults):
                raise ValueError(f'Legacy {table} is missing required columns')
            # Only known invitation additions can inherit native defaults.
            selected = ','.join('"' + column + '"' for column in columns)
            rows = db.execute(f'SELECT rowid,{selected} FROM "{table}" ORDER BY rowid').fetchall()
            exported[table] = (columns, rows)
        return exported
    except sqlite3.DatabaseError as error:
        raise ValueError('Legacy snapshot cannot be read safely') from error
    finally:
        db.close()


def install_legacy_fence(connection):
    """Prevent an old deployment from writing an already migrated scope."""
    connection.execute('''CREATE OR REPLACE FUNCTION public.ledgerloops_guard_legacy_snapshot()
        RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
        DECLARE scope text;
        BEGIN
          scope := CASE WHEN TG_OP = 'DELETE' THEN OLD.node_id ELSE NEW.node_id END;
          IF EXISTS (SELECT 1 FROM public.ledgerloops_nodes
                     WHERE node_id=scope AND legacy_snapshot_sha256 IS NOT NULL)
             OR (TG_OP = 'UPDATE' AND EXISTS (
                     SELECT 1 FROM public.ledgerloops_nodes
                     WHERE node_id=OLD.node_id AND legacy_snapshot_sha256 IS NOT NULL)) THEN
            RAISE EXCEPTION 'Legacy storage scope has been migrated; stop the old runtime'
              USING ERRCODE='55000';
          END IF;
          IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END $$''')
    connection.execute('DROP TRIGGER IF EXISTS ledgerloops_migrated_snapshot_fence '
                       'ON public.ledgerloops_node_snapshots')
    connection.execute('''CREATE TRIGGER ledgerloops_migrated_snapshot_fence
        BEFORE INSERT OR UPDATE OR DELETE ON public.ledgerloops_node_snapshots
        FOR EACH ROW EXECUTE FUNCTION public.ledgerloops_guard_legacy_snapshot()''')


def migrate_scope(connection, scope):
    """One scope's import and completed marker commit or rollback together."""
    from psycopg import sql
    from postgres_schema import SCHEMA
    with connection.transaction():
        connection.execute('SET LOCAL synchronous_commit=on')
        connection.execute("SELECT pg_advisory_xact_lock(hashtext('ledgerloops_native_snapshot_migration'))")
        row = connection.execute('''SELECT version,image FROM public.ledgerloops_node_snapshots
            WHERE node_id=%s FOR UPDATE''', (scope,), binary=True).fetchone()
        if row is None:
            raise ValueError('Requested legacy scope does not exist')
        version, image = row[0], bytes(row[1])
        image_hash = hashlib.sha256(image).hexdigest()
        connection.execute('INSERT INTO public.ledgerloops_nodes(node_id) VALUES(%s) '
                           'ON CONFLICT(node_id) DO NOTHING', (scope,))
        native = connection.execute('''SELECT version,legacy_snapshot_version,legacy_snapshot_sha256
            FROM public.ledgerloops_nodes WHERE node_id=%s FOR UPDATE''', (scope,)).fetchone()
        if native[2] is not None:
            if native[1] != version or native[2] != image_hash:
                raise ValueError('Legacy source differs from the completed migration')
            return {'status': 'already_migrated', 'rows': 0}
        if native[0] != 0:
            raise ValueError('Native scope has already changed; refusing to overwrite it')
        connection.execute("SELECT set_config('ledgerloops.owner_node_id',%s,true)", (scope,))
        for table in sorted(_scope_tables(scope)):
            # The administrative importer may legitimately use a superuser or
            # BYPASSRLS role. Do not depend on actor RLS to scope this check.
            exists = connection.execute(sql.SQL(
                'SELECT EXISTS(SELECT 1 FROM {}.{} WHERE owner_node_id=%s)').format(
                sql.Identifier(SCHEMA), sql.Identifier(table)), (scope,)).fetchone()[0]
            if exists:
                raise ValueError('Native scope is not empty; refusing to overwrite it')
        exported = export_image(image, scope)
        count = 0
        for table, (columns, rows) in exported.items():
            names = ('rowid',) + columns + ('owner_node_id',)
            statement = sql.SQL('INSERT INTO {}.{} ({}) OVERRIDING SYSTEM VALUE VALUES({})').format(
                sql.Identifier(SCHEMA), sql.Identifier(table),
                sql.SQL(',').join(map(sql.Identifier, names)),
                sql.SQL(',').join(sql.Placeholder() for _ in names))
            with connection.cursor() as cursor:
                cursor.executemany(statement, [tuple(row) + (scope,) for row in rows])
            count += len(rows)
            if rows:
                # Sequence changes can leave harmless gaps after rollback. Never
                # lower a shared sequence when several scopes had equal rowids.
                sequence = connection.execute('SELECT pg_get_serial_sequence(%s,%s)',
                    (SCHEMA + '.' + table, 'rowid')).fetchone()[0]
                if sequence:
                    connection.execute('SELECT setval(%s,GREATEST(%s,nextval(%s)),true)',
                                       (sequence, max(row[0] for row in rows), sequence))
        connection.execute('''UPDATE public.ledgerloops_nodes
            SET version=%s,legacy_snapshot_version=%s,legacy_snapshot_sha256=%s,
                updated_at=CURRENT_TIMESTAMP WHERE node_id=%s''',
            (max(1, version), version, image_hash, scope))
        return {'status': 'migrated', 'rows': count}


def migrate(factory, scopes=None):
    """Explicit administrative entry point. Caller must ensure global downtime."""
    from postgres_schema import initialize
    results = []
    with factory._pool.connection() as connection:
        # Serialize the complete admin operation, including schema DDL. Otherwise
        # a second import's ALTER TABLE can deadlock with the first import's
        # registry/data locks. Use this connection for setup too: CLI pools can
        # contain only one connection. PostgreSQL releases this lock on a broken
        # connection, and the finally block releases it before normal pool reuse.
        # Share the schema-initialization lock with release/startup setup, so
        # those processes wait instead of issuing DDL during an active import.
        connection.execute("SELECT pg_advisory_lock(hashtext('ledgerloops-native-schema-v1'))")
        try:
            with connection.transaction():
                connection.execute("SELECT pg_advisory_xact_lock(hashtext('ledgerloops-native-schema-v1'))")
                initialize(connection)
            if not connection.execute("SELECT to_regclass('public.ledgerloops_node_snapshots')").fetchone()[0]:
                return results
            with connection.transaction():
                install_legacy_fence(connection)
            if scopes is None:
                scopes = [row[0] for row in connection.execute(
                    'SELECT node_id FROM public.ledgerloops_node_snapshots ORDER BY node_id')]
            for scope in scopes:
                results.append(migrate_scope(connection, scope))
        finally:
            connection.execute("SELECT pg_advisory_unlock(hashtext('ledgerloops-native-schema-v1'))")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-offline', action='store_true',
                        help='Confirm all old web/worker writers are stopped')
    parser.add_argument('--scope', action='append', help='Migrate only this storage scope (repeatable)')
    args = parser.parse_args()
    if not args.confirm_offline:
        parser.error('--confirm-offline is required; stop every web and worker writer first')
    dsn = os.environ.get('DATABASE_URL')
    if not dsn:
        parser.error('DATABASE_URL must be configured without printing its value')
    from hosted_storage import PgStoreFactory
    factory = None
    try:
        factory = PgStoreFactory(dsn, max_connections=1)
        results = migrate(factory, args.scope)
        print(json.dumps({'scopes': len(results),
                          'migrated': sum(r['status'] == 'migrated' for r in results),
                          'already_migrated': sum(r['status'] == 'already_migrated' for r in results),
                          'rows': sum(r['rows'] for r in results)}))
    except Exception:
        # PostgreSQL errors may include failing row values (credentials or
        # unreleased secrets). Do not expose exception text or a traceback.
        parser.exit(1, 'Migration failed; the current import was rolled back. '
                       'Retained images and previously completed scopes remain. '
                       'Review schema compatibility before retrying.\n')
    finally:
        if factory is not None:
            factory.close()


if __name__ == '__main__':
    main()
