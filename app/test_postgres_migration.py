"""Migration checks use only fabricated data and a disposable PostgreSQL database."""
import hashlib
import io
import os
import sqlite3
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from migrate_postgres_snapshots import export_image, main, migrate, migrate_scope


def image(script):
    with sqlite3.connect(':memory:') as db:
        db.executescript(script)
        return db.serialize()


class SnapshotExportTests(unittest.TestCase):
    def test_preserves_order_and_exact_state(self):
        source = image("""CREATE TABLE balances(peer TEXT PRIMARY KEY,balance INTEGER NOT NULL);
            INSERT INTO balances(rowid,peer,balance) VALUES(11,'fictional-peer',1000000000000);
            CREATE TABLE outbox(id TEXT PRIMARY KEY,peer TEXT NOT NULL,data TEXT NOT NULL);
            INSERT INTO outbox VALUES('message-one','fictional-peer','{"kind":"fulfill"}');""")
        data = export_image(source, 'node:fictional')
        self.assertEqual(data['balances'], (('peer', 'balance'), [(11, 'fictional-peer', 1000000000000)]))
        self.assertEqual(data['outbox'][1][0][1:],
                         ('message-one', 'fictional-peer', '{"kind":"fulfill"}'))

    def test_rejects_unknown_tables_and_columns(self):
        for script in ['CREATE TABLE surprise(secret TEXT)',
                       'CREATE TABLE balances(peer TEXT,balance INTEGER,forgotten TEXT)',
                       'CREATE TABLE balances(peer TEXT)']:
            with self.subTest(script=script), self.assertRaises(ValueError):
                export_image(image(script), 'node:fictional')

    def test_rejects_out_of_scope_auth_and_enrollment(self):
        for scope, script in [('node:fictional', 'CREATE TABLE auth_sessions(token_hash TEXT)'),
                              ('accounts', 'CREATE TABLE balances(peer TEXT,balance INTEGER)'),
                              ('enrollment', 'CREATE TABLE private_secrets(id TEXT,preimage TEXT)')]:
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                export_image(image(script), scope)

    def test_rejects_unmigrated_view_or_trigger_behavior(self):
        with self.assertRaisesRegex(ValueError, 'views or triggers'):
            export_image(image('CREATE TABLE balances(peer TEXT,balance INTEGER); '
                               'CREATE VIEW hidden AS SELECT * FROM balances'), 'node:fictional')

    def test_corrupt_input_fails_closed(self):
        with self.assertRaises(ValueError):
            export_image(b'not a SQLite database', 'node:fictional')

    def test_cli_does_not_print_database_failure_details(self):
        stderr = io.StringIO()
        with patch.dict(os.environ, {'DATABASE_URL': 'fabricated-dsn'}), \
                patch('sys.argv', ['migrate', '--confirm-offline']), \
                patch('sys.stderr', stderr), \
                patch('hosted_storage.PgStoreFactory', side_effect=ValueError('fabricated-private-secret')):
            with self.assertRaises(SystemExit) as result:
                main()
        self.assertEqual(result.exception.code, 1)
        self.assertNotIn('fabricated-private-secret', stderr.getvalue())

    def test_admin_import_does_not_depend_on_rls_for_destination_scope(self):
        # Model an administrative connection that bypasses RLS and can see
        # another actor's balance. An unscoped EXISTS must report nonempty;
        # only an explicit owner predicate can establish our empty destination.
        source = image('CREATE TABLE balances(peer TEXT PRIMARY KEY,balance INTEGER NOT NULL); '
                       "INSERT INTO balances VALUES('target-peer',17)")
        scope, checked = 'migration-target', []
        connection = MagicMock()

        def execute(statement, parameters=(), **kwargs):
            query = statement if isinstance(statement, str) else statement.as_string()
            normalized = ' '.join(query.split())
            if normalized.startswith('SELECT version,image'):
                row = (7, source)
            elif normalized.startswith('SELECT version,legacy_snapshot_version'):
                row = (0, None, None)
            elif normalized.startswith('SELECT EXISTS(SELECT 1 FROM'):
                is_scoped = 'WHERE owner_node_id=%s' in normalized and parameters == (scope,)
                checked.append(is_scoped)
                row = (not is_scoped,)
            elif normalized.startswith('SELECT pg_get_serial_sequence'):
                row = (None,)
            else:
                row = None
            return SimpleNamespace(fetchone=lambda: row)

        connection.execute.side_effect = execute
        result = migrate_scope(connection, scope)
        self.assertEqual(result, {'status': 'migrated', 'rows': 1})
        self.assertTrue(checked)
        self.assertTrue(all(checked))
        inserted = connection.cursor.return_value.__enter__.return_value.executemany.call_args.args[1]
        self.assertEqual(inserted, [(1, 'target-peer', 17, scope)])


@unittest.skipUnless(os.environ.get('LEDGERLOOPS_TEST_POSTGRES_DSN'),
                     'Set LEDGERLOOPS_TEST_POSTGRES_DSN for a disposable database')
class NativeMigrationTests(unittest.TestCase):
    def setUp(self):
        from hosted_storage import PgStoreFactory
        self.factory = PgStoreFactory(os.environ['LEDGERLOOPS_TEST_POSTGRES_DSN'])
        self.factory.initialize()
        self.scope = 'migration-test-' + uuid.uuid4().hex
        self.scopes = [self.scope]
        self.source = image("""CREATE TABLE balances(peer TEXT PRIMARY KEY,balance INTEGER NOT NULL);
            INSERT INTO balances(rowid,peer,balance) VALUES(41,'fictional-peer',17);
            CREATE TABLE outbox(id TEXT PRIMARY KEY,peer TEXT NOT NULL,data TEXT NOT NULL);
            INSERT INTO outbox VALUES('stable-message','fictional-peer','{"kind":"ready"}');
            CREATE TABLE inbox(id TEXT PRIMARY KEY);
            INSERT INTO inbox VALUES('already-processed');
            CREATE TABLE reservations(peer TEXT PRIMARY KEY,proposal TEXT NOT NULL);
            INSERT INTO reservations VALUES('fictional-peer','unfinished-proposal');
            CREATE TABLE private_secrets(id TEXT PRIMARY KEY,preimage TEXT NOT NULL);
            INSERT INTO private_secrets VALUES('unfinished-proposal','fabricated-secret');""")
        with self.factory._pool.connection() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS public.ledgerloops_node_snapshots(
                node_id TEXT PRIMARY KEY,version BIGINT NOT NULL DEFAULT 0,image BYTEA NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
            conn.execute('INSERT INTO public.ledgerloops_node_snapshots(node_id,version,image) '
                         'VALUES(%s,7,%s)', (self.scope, self.source))

    def tearDown(self):
        with self.factory._pool.connection() as conn:
            # Remove the completion marker before deleting only this test's
            # retained image. The fence must remain installed for other scopes.
            conn.execute('UPDATE public.ledgerloops_nodes SET legacy_snapshot_sha256=NULL '
                         'WHERE node_id=ANY(%s)', (self.scopes,))
            conn.execute('DELETE FROM public.ledgerloops_node_snapshots WHERE node_id=ANY(%s)', (self.scopes,))
            conn.execute('DELETE FROM public.ledgerloops_nodes WHERE node_id=ANY(%s)', (self.scopes,))
        self.factory.close()

    def test_lossless_idempotent_import_and_old_writer_fence(self):
        result = migrate(self.factory, [self.scope])
        self.assertEqual(result[0]['status'], 'migrated')
        self.assertEqual(migrate(self.factory, [self.scope])[0]['status'], 'already_migrated')
        db = self.factory.connection(self.scope)
        try:
            with db:
                self.assertEqual(db.execute('SELECT peer,balance,rowid FROM balances').fetchone(),
                                 ('fictional-peer', 17, 41))
                self.assertEqual(db.execute('SELECT id FROM inbox').fetchone()[0], 'already-processed')
                self.assertEqual(db.execute('SELECT proposal FROM reservations').fetchone()[0], 'unfinished-proposal')
                self.assertEqual(db.execute('SELECT preimage FROM private_secrets').fetchone()[0], 'fabricated-secret')
                db.execute('INSERT INTO balances(peer,balance) VALUES(?,?)', ('second-fictional-peer', 3))
                self.assertGreater(db.execute('SELECT rowid FROM balances WHERE peer=?',
                                             ('second-fictional-peer',)).fetchone()[0], 41)
        finally:
            db.close()
        from psycopg.errors import ObjectNotInPrerequisiteState
        with self.factory._pool.connection() as conn:
            marker = conn.execute('SELECT legacy_snapshot_version,legacy_snapshot_sha256 '
                                  'FROM public.ledgerloops_nodes WHERE node_id=%s', (self.scope,)).fetchone()
            self.assertEqual(marker, (7, hashlib.sha256(self.source).hexdigest()))
            retained = conn.execute('SELECT image FROM public.ledgerloops_node_snapshots '
                                    'WHERE node_id=%s', (self.scope,)).fetchone()[0]
            self.assertEqual(bytes(retained), self.source)
            with self.assertRaises(ObjectNotInPrerequisiteState):
                conn.execute('UPDATE public.ledgerloops_node_snapshots SET version=version+1 '
                             'WHERE node_id=%s', (self.scope,))

    def test_nonempty_native_scope_is_not_overwritten(self):
        with self.factory._pool.connection() as conn:
            conn.execute('INSERT INTO public.ledgerloops_nodes(node_id,version) VALUES(%s,1)', (self.scope,))
        with self.assertRaisesRegex(ValueError, 'already changed'):
            migrate(self.factory, [self.scope])

    def test_account_credentials_sessions_and_enrollment_survive(self):
        accounts, enrollment = self.scope + ':accounts', self.scope + ':enrollment'
        self.scopes.extend([accounts, enrollment])
        account_image = image("""CREATE TABLE auth_accounts(
                id TEXT PRIMARY KEY,node_id TEXT NOT NULL UNIQUE,name TEXT NOT NULL,created INTEGER NOT NULL);
            INSERT INTO auth_accounts VALUES('fictional-account','fictional-node','Fictional User',100);
            CREATE TABLE auth_credentials(id TEXT PRIMARY KEY,account_id TEXT NOT NULL,
                public_key TEXT NOT NULL,sign_count INTEGER NOT NULL,created INTEGER NOT NULL);
            INSERT INTO auth_credentials VALUES('fictional-credential','fictional-account','fictional-public-key',9,100);
            CREATE TABLE auth_sessions(token_hash TEXT PRIMARY KEY,account_id TEXT NOT NULL,
                csrf TEXT NOT NULL,expires INTEGER NOT NULL);
            INSERT INTO auth_sessions VALUES('fictional-session-hash','fictional-account','fictional-csrf',9999999999);
            CREATE TABLE auth_challenges(id TEXT PRIMARY KEY,kind TEXT NOT NULL,challenge TEXT NOT NULL,
                context TEXT NOT NULL,expires INTEGER NOT NULL,consumed INTEGER NOT NULL DEFAULT 0);
            INSERT INTO auth_challenges VALUES('fictional-challenge','register','fictional-challenge-value','{}',9999999999,0);
            CREATE TABLE auth_recovery(code_hash TEXT PRIMARY KEY,account_id TEXT NOT NULL,
                consumed INTEGER NOT NULL DEFAULT 0);
            INSERT INTO auth_recovery VALUES('fictional-code-hash','fictional-account',0);""")
        enrollment_image = image("""CREATE TABLE channel_keys(pair TEXT PRIMARY KEY,secret TEXT NOT NULL);
            INSERT INTO channel_keys VALUES('fictional-pair','fictional-peer-key');""")
        with self.factory._pool.connection() as conn:
            conn.execute('INSERT INTO public.ledgerloops_node_snapshots(node_id,version,image) VALUES(%s,2,%s)',
                         (accounts, account_image))
            conn.execute('INSERT INTO public.ledgerloops_node_snapshots(node_id,version,image) VALUES(%s,3,%s)',
                         (enrollment, enrollment_image))
        migrate(self.factory, [accounts, enrollment])
        account_db = self.factory.connection(accounts)
        enrollment_db = self.factory.connection(enrollment)
        try:
            self.assertEqual(account_db.execute('SELECT public_key,sign_count FROM auth_credentials').fetchone(),
                             ('fictional-public-key', 9))
            self.assertEqual(account_db.execute('SELECT token_hash,csrf,expires FROM auth_sessions').fetchone(),
                             ('fictional-session-hash', 'fictional-csrf', 9999999999))
            self.assertEqual(account_db.execute('SELECT challenge,consumed FROM auth_challenges').fetchone(),
                             ('fictional-challenge-value', 0))
            self.assertEqual(account_db.execute('SELECT code_hash FROM auth_recovery').fetchone()[0],
                             'fictional-code-hash')
            self.assertEqual(enrollment_db.execute('SELECT secret FROM channel_keys').fetchone()[0],
                             'fictional-peer-key')
        finally:
            account_db.close()
            enrollment_db.close()

    def test_incompatible_native_constraint_rolls_back_copied_rows(self):
        bad = image("""CREATE TABLE balances(peer TEXT PRIMARY KEY,balance INTEGER NOT NULL);
            INSERT INTO balances VALUES('fictional-peer',17);
            CREATE TABLE outbox(id TEXT PRIMARY KEY,peer TEXT,data TEXT);
            INSERT INTO outbox VALUES('missing-required-payload',NULL,'{}');""")
        with self.factory._pool.connection() as conn:
            conn.execute('UPDATE public.ledgerloops_node_snapshots SET image=%s WHERE node_id=%s',
                         (bad, self.scope))
        from psycopg.errors import NotNullViolation
        with self.assertRaises(NotNullViolation):
            migrate(self.factory, [self.scope])
        with self.factory._pool.connection() as conn:
            self.assertIsNone(conn.execute('SELECT node_id FROM public.ledgerloops_nodes '
                                          'WHERE node_id=%s', (self.scope,)).fetchone())
            with conn.transaction():
                conn.execute("SELECT set_config('ledgerloops.owner_node_id',%s,true)", (self.scope,))
                self.assertEqual(conn.execute('SELECT count(*) FROM ledgerloops_data.balances').fetchone()[0], 0)

    def test_mismatched_completed_source_is_rejected(self):
        migrate(self.factory, [self.scope])
        with self.factory._pool.connection() as conn:
            conn.execute('UPDATE public.ledgerloops_nodes SET legacy_snapshot_sha256=%s WHERE node_id=%s',
                         ('0' * 64, self.scope))
        with self.assertRaisesRegex(ValueError, 'differs'):
            migrate(self.factory, [self.scope])

    def test_simultaneous_imports_serialize_the_same_destination(self):
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: migrate(self.factory, [self.scope]), range(2)))
        self.assertEqual(sorted(result[0]['status'] for result in results),
                         ['already_migrated', 'migrated'])
        db = self.factory.connection(self.scope)
        try:
            self.assertEqual(db.execute('SELECT count(*) FROM balances').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM outbox').fetchone()[0], 1)
        finally:
            db.close()

    def test_unknown_legacy_data_rolls_back_all_native_changes(self):
        with self.factory._pool.connection() as conn:
            conn.execute('UPDATE public.ledgerloops_node_snapshots SET image=%s WHERE node_id=%s',
                         (image('CREATE TABLE unrecognized(value TEXT)'), self.scope))
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            migrate(self.factory, [self.scope])
        with self.factory._pool.connection() as conn:
            self.assertIsNone(conn.execute('SELECT node_id FROM public.ledgerloops_nodes '
                                          'WHERE node_id=%s', (self.scope,)).fetchone())


if __name__ == '__main__':
    unittest.main()
