"""Native actor version stability and bounded-lock review regressions."""
import os
import secrets
import time
import unittest

from psycopg.errors import LockNotAvailable

from hosted_runtime import HostedRuntime
import test_hosted_gateway as gateway
import test_hosted_storage as storage


@unittest.skipUnless(os.environ.get('LEDGERLOOPS_TEST_POSTGRES_DSN'),
                     'Set LEDGERLOOPS_TEST_POSTGRES_DSN for real PostgreSQL review tests')
class NativeStorageReview(unittest.TestCase):
    setUp = storage.NativePostgresTests.setUp
    tearDown = storage.NativePostgresTests.tearDown
    node = storage.NativePostgresTests.node
    balance = staticmethod(storage.NativePostgresTests.balance)
    version = storage.NativePostgresTests.version

    def test_selects_ignored_inserts_and_noop_updates_do_not_publish(self):
        key, db = self.node()
        db.execute("INSERT INTO outbox(id,peer,data) VALUES('existing','fixture','{}')")
        before = self.version(key)
        for _ in range(12):
            with db:
                self.assertEqual(self.balance(db), 0)
                db.execute("INSERT INTO outbox(id,peer,data) VALUES('existing','fixture','{}') ON CONFLICT DO NOTHING")
                db.execute('UPDATE balances SET balance=balance')
        self.assertEqual(self.version(key), before)

    def test_wakeup_registry_observes_commits_without_mutating_itself(self):
        key, db = self.node()
        before = self.version(key)
        for _ in range(3):
            self.assertEqual(self.factory.node_versions()[key], before[0])
        self.assertEqual(self.version(key), before)
        with db:
            db.execute('UPDATE balances SET balance=23')
        self.assertEqual(self.factory.node_versions()[key], before[0] + 1)

    def test_repeated_hosted_state_reads_keep_version_and_timestamp(self):
        prefix = 'storage-review-' + secrets.token_hex(16) + ':'
        stores = gateway.ScopedStores(self.factory, prefix)
        runtime = HostedRuntime(stores, 'https://app.ledgerloops.com')
        account = dict(node_id='n_' + secrets.token_hex(16), name='Isolated TEST identity')
        runtime.provision(account)
        key = prefix + 'node:' + account['node_id']
        self.keys.append(key)
        initial = runtime.state(account['node_id'])
        before = self.version(key)
        for _ in range(12):
            runtime.provision(account)
            self.assertEqual(runtime.state(account['node_id']), initial)
        self.assertEqual(self.version(key), before)

    def test_schema_initialization_can_repeat_without_changing_actor_state(self):
        key, db = self.node()
        db.execute('UPDATE balances SET balance=23')
        before = self.version(key)
        self.factory.initialize()
        self.assertEqual(self.balance(db), 23)
        self.assertEqual(self.version(key), before)
        db.execute('UPDATE balances SET balance=24')
        self.assertEqual(self.version(key)[0], before[0] + 1,
                         'Repeated schema setup must preserve working dirty tracking')

    def test_row_lock_timeout_rolls_back_and_contender_recovers(self):
        key, holder = self.node()
        holder.execute('UPDATE balances SET balance=17')
        before = self.version(key)
        contender = self.factory.connection(key)
        self.connections.append(contender)
        entered = False
        with self.assertRaisesRegex(ValueError, 'rollback holder'):
            with holder:
                holder.execute('UPDATE balances SET balance=999')
                began = time.monotonic()
                with self.assertRaises(LockNotAvailable):
                    with contender:
                        entered = True
                        contender.execute('UPDATE balances SET balance=1234')
                elapsed = time.monotonic() - began
                self.assertGreaterEqual(elapsed, 3.5)
                self.assertLess(elapsed, 12)
                self.assertFalse(entered)
                raise ValueError('rollback holder')
        self.assertEqual(self.version(key), before)
        self.assertEqual(self.balance(contender), 17)
        with contender:
            contender.execute('UPDATE balances SET balance=balance+1')
            contender.execute("INSERT INTO outbox(id,peer,data) VALUES('after-timeout','fixture','{}')")
        self.assertEqual(self.balance(holder), 18)
        self.assertEqual(holder.execute('SELECT id FROM outbox').fetchone()[0], 'after-timeout')
        self.assertEqual(self.version(key)[0], before[0] + 1)


if __name__ == '__main__':
    unittest.main()
