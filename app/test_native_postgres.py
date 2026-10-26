"""Database-enforced owner isolation, including deliberately unscoped queries."""
import os
import unittest
import uuid
from unittest.mock import MagicMock, patch

from psycopg.errors import InsufficientPrivilege, NotNullViolation, UndefinedTable

from hosted_storage import PgStoreFactory, PostgresConnection
from hosted_runtime import HostedRuntime
import test_hosted_storage as storage


@unittest.skipUnless(os.environ.get('LEDGERLOOPS_TEST_POSTGRES_DSN'),
                     'Set LEDGERLOOPS_TEST_POSTGRES_DSN for native RLS tests')
class NativeOwnerIsolation(unittest.TestCase):
    setUp = storage.NativePostgresTests.setUp
    tearDown = storage.NativePostgresTests.tearDown
    node = storage.NativePostgresTests.node
    balance = staticmethod(storage.NativePostgresTests.balance)

    def assert_rls_role(self):
        with self.factory._pool.connection() as connection:
            role = connection.execute(
                'SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
        self.assertEqual(role, (False, False),
                         'Isolation tests require a non-superuser, non-BYPASSRLS test role')

    def test_queries_and_updates_without_owner_predicate_stay_local(self):
        self.assert_rls_role()
        _, left = self.node()
        _, right = self.node()
        left.execute("UPDATE balances SET balance=17")
        right.execute("UPDATE balances SET balance=29")
        self.assertEqual(left.execute('SELECT count(*) FROM balances').fetchone()[0], 1)
        self.assertEqual(right.execute('SELECT count(*) FROM balances').fetchone()[0], 1)
        left.execute('UPDATE balances SET balance=balance+2')
        self.assertEqual(self.balance(left), 19)
        self.assertEqual(self.balance(right), 29)
        left.execute('DELETE FROM balances')
        self.assertEqual(left.execute('SELECT count(*) FROM balances').fetchone()[0], 0)
        self.assertEqual(self.balance(right), 29)

    def test_joins_and_subqueries_cannot_observe_other_owners(self):
        self.assert_rls_role()
        _, left = self.node()
        _, right = self.node()
        left.execute('UPDATE balances SET balance=17')
        right.execute('UPDATE balances SET balance=29')
        left.execute("INSERT INTO contacts(peer,own,peer_preferences) VALUES('fixture','left',NULL)")
        right.execute("INSERT INTO contacts(peer,own,peer_preferences) VALUES('fixture','right',NULL)")
        row = left.execute('SELECT b.balance,c.own FROM balances b JOIN contacts c USING(peer)').fetchone()
        self.assertEqual(tuple(row), (17, 'left'))
        self.assertEqual(left.execute('SELECT count(*) FROM balances WHERE peer IN (SELECT peer FROM contacts)').fetchone()[0], 1)
        self.assertEqual(right.execute('SELECT own FROM contacts').fetchone()[0], 'right')

    def test_owner_cannot_be_forged_on_insert_or_update(self):
        self.assert_rls_role()
        _, left = self.node()
        right_key, right = self.node()
        with self.assertRaises(InsufficientPrivilege):
            left.execute('INSERT INTO balances(peer,balance,owner_node_id) VALUES(?,?,?)',
                         ('forged', 100, right_key))
        with self.assertRaises(InsufficientPrivilege):
            left.execute('UPDATE balances SET owner_node_id=?', (right_key,))
        self.assertEqual(self.balance(left), 0)
        self.assertEqual(right.execute('SELECT count(*) FROM balances').fetchone()[0], 1)

    def test_missing_scope_denies_reads_and_writes(self):
        self.assert_rls_role()
        key, _ = self.node()
        with self.factory._pool.connection() as connection:
            with connection.transaction():
                connection.execute("SELECT set_config('ledgerloops.owner_node_id','',true)")
                self.assertEqual(connection.execute('SELECT count(*) FROM ledgerloops_data.balances').fetchone()[0], 0)
            with self.assertRaises((InsufficientPrivilege, NotNullViolation)):
                with connection.transaction():
                    connection.execute("SELECT set_config('ledgerloops.owner_node_id','',true)")
                    connection.execute('INSERT INTO ledgerloops_data.balances(peer,balance,owner_node_id) VALUES(%s,%s,%s)',
                                       ('forged', 100, key))

    def test_local_scope_does_not_leak_when_pool_reuses_connection(self):
        self.assert_rls_role()
        key, db = self.node()
        # A one-connection pool ensures all operations below reuse the same session.
        pool = PgStoreFactory(self.dsn, max_connections=1)
        actor = pool.connection(key)
        try:
            self.assertEqual(self.balance(actor), 0)
            with self.assertRaisesRegex(ValueError, 'rollback'):
                with actor:
                    actor.execute('UPDATE balances SET balance=12')
                    raise ValueError('rollback')
            with pool._pool.connection() as raw:
                setting = raw.execute("SELECT current_setting('ledgerloops.owner_node_id',true)").fetchone()[0]
                self.assertIn(setting, (None, ''))
                self.assertEqual(raw.execute('SELECT count(*) FROM ledgerloops_data.balances').fetchone()[0], 0)
            self.assertEqual(self.balance(db), 0)
        finally:
            actor.close()
            pool.close()

    def test_actor_scope_cannot_access_account_or_enrollment_rows(self):
        self.assert_rls_role()
        _, actor = self.node()
        self.assertEqual(actor.execute('SELECT count(*) FROM auth_accounts').fetchone()[0], 0)
        self.assertEqual(actor.execute('SELECT count(*) FROM channel_keys').fetchone()[0], 0)
        with self.assertRaises(InsufficientPrivilege):
            actor.execute("INSERT INTO auth_accounts(id,node_id,name,created) VALUES('bad','bad','bad',0)")
        with self.assertRaises(InsufficientPrivilege):
            actor.execute("INSERT INTO channel_keys(pair,secret) VALUES('bad','bad')")

    def test_fixed_actor_cannot_query_infrastructure_relations(self):
        _, actor = self.node()
        # Table-name qualification must not escape the fixed actor capability.
        for relation in ('public.ledgerloops_nodes', 'ledgerloops_nodes',
                         'public.ledgerloops_node_snapshots', '"public"."ledgerloops_nodes"'):
            with self.subTest(relation=relation):
                with self.assertRaises((ValueError, PermissionError, InsufficientPrivilege, UndefinedTable)):
                    actor.execute(f'SELECT * FROM {relation}')

    def test_bind_markers_preserve_literal_question_and_percent_characters(self):
        _, actor = self.node()
        row = actor.execute("SELECT '?' AS question, '100%' AS percent, ? AS bound", ('literal %s ?',)).fetchone()
        self.assertEqual(tuple(row), ('?', '100%', 'literal %s ?'))

    def test_native_hosted_actor_does_not_construct_sqlite_database(self):
        runtime = HostedRuntime(self.factory, 'https://example.test')
        ident = 'n_' + uuid.uuid4().hex
        self.keys.append(runtime.key(ident))
        with patch('sqlite3.connect', side_effect=AssertionError('Native hosted path must not create SQLite')):
            runtime.provision(dict(node_id=ident, name='Native TEST identity'))
            state = runtime.state(ident)
        self.assertEqual(state['node'], ident)
        self.assertEqual(state['balances'], [])


class RuntimeRolePreflight(unittest.TestCase):
    def test_superuser_and_bypassrls_fail_before_actor_scope_is_used(self):
        for flags in ((True, False), (False, True)):
            with self.subTest(flags=flags):
                pool = MagicMock()
                connection = pool.connection.return_value.__enter__.return_value
                connection.execute.return_value.fetchone.return_value = flags
                actor = PostgresConnection(pool, 'node:n_forbidden_role')
                with self.assertRaisesRegex(RuntimeError, 'non-superuser, non-BYPASSRLS'):
                    actor.execute('SELECT 1')
                self.assertEqual(connection.execute.call_count, 1,
                                 'Reject bypass roles before setting scope or reading ledger rows')
                pool.connection.return_value.__exit__.assert_called_once()
                self.assertFalse(actor.in_transaction)


if __name__ == '__main__':
    unittest.main()
