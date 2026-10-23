"""Independent snapshot write-amplification regressions on isolated TEST rows.

Never connects to production; these tests use the explicit test PostgreSQL DSN
and remove only their randomly named fixture keys. Header/row-count shortcuts
must not discard genuine schema or PRAGMA migrations.
"""
import os
import secrets
import time
import unittest

from psycopg.errors import LockNotAvailable

from hosted_runtime import HostedRuntime
from hosted_storage import TABLE
import test_hosted_gateway as gateway
import test_hosted_storage as storage


@unittest.skipUnless(os.environ.get('LEDGERLOOPS_TEST_POSTGRES_DSN'),
                     'Set LEDGERLOOPS_TEST_POSTGRES_DSN for real PostgreSQL review tests')
class SnapshotWriteAmplificationReview(unittest.TestCase):
    setUp = storage.PostgresSnapshotTests.setUp
    tearDown = storage.PostgresSnapshotTests.tearDown
    node = storage.PostgresSnapshotTests.node

    def snapshot(self, key):
        with self.factory._pool.connection() as connection:
            row = connection.execute(f'SELECT version,image,updated_at FROM {TABLE} WHERE node_id=%s', (key,)).fetchone()
        return row[0], bytes(row[1]), row[2]

    def test_selects_ignored_inserts_and_semantic_noop_updates_do_not_publish(self):
        key, db = self.node()
        db.execute("INSERT INTO outbox VALUES('existing-fixture')")
        before = self.snapshot(key)
        for _ in range(12):
            with db:
                self.assertEqual(db.execute('SELECT n FROM counter').fetchone()[0], 0)
                db.execute("INSERT OR IGNORE INTO outbox VALUES('existing-fixture')")
                db.execute('UPDATE counter SET n=n')
        self.assertEqual(self.snapshot(key), before,
                         'No logical or SQLite image change must create new PostgreSQL/TOAST versions')

    def test_repeated_hosted_state_reads_keep_exact_image_version_and_timestamp(self):
        prefix = 'storage-review-'+secrets.token_hex(16)+':'
        stores = gateway.ScopedStores(self.factory, prefix)
        runtime = HostedRuntime(stores, 'https://app.ledgerloops.com')
        account = dict(node_id='n_'+secrets.token_hex(16), name='Isolated TEST identity')
        runtime.provision(account)
        key = prefix+'node:'+account['node_id']
        self.keys.append(key)
        initial = runtime.state(account['node_id'])
        before = self.snapshot(key)
        for _ in range(12):
            runtime.provision(account)
            self.assertEqual(runtime.state(account['node_id']), initial)
        self.assertEqual(self.snapshot(key), before,
                         'Read-only Node initialization and hosted schema checks must not republish snapshots')

    def test_row_lock_timeout_rolls_back_and_same_contender_recovers(self):
        key, holder = self.node()
        holder.execute('UPDATE counter SET n=17')
        before = self.snapshot(key)
        contender = self.factory.connection(key)
        self.connections.append(contender)
        entered = False
        with self.assertRaisesRegex(ValueError, 'rollback uncommitted holder'):
            with holder:
                holder.execute('UPDATE counter SET n=999')
                began = time.monotonic()
                with self.assertRaises(LockNotAvailable):
                    with contender:
                        entered = True
                        contender.execute('UPDATE counter SET n=1234')
                elapsed = time.monotonic()-began
                self.assertGreaterEqual(elapsed, 3.5, 'An independent connection must actually wait for the held row')
                self.assertLess(elapsed, 12, 'The configured lock timeout must bound the blocked transaction')
                self.assertFalse(entered, 'A failed snapshot lock must not expose a stale local image')
                raise ValueError('rollback uncommitted holder')
        self.assertEqual(self.snapshot(key), before,
                         'Neither a timed-out contender nor a rolled-back holder may publish partial state')
        self.assertEqual(contender.execute('SELECT n FROM counter').fetchone()[0], 17)
        with contender:
            contender.execute('UPDATE counter SET n=n+1')
            contender.execute("INSERT INTO outbox VALUES('after-timeout')")
        self.assertEqual(holder.execute('SELECT n FROM counter').fetchone()[0], 18)
        self.assertEqual(holder.execute('SELECT id FROM outbox').fetchall(), [('after-timeout',)])
        self.assertEqual(self.snapshot(key)[0], before[0]+1,
                         'The same adapter must commit exactly one later counter/outbox transaction')

    def test_zero_row_change_schema_and_pragma_migrations_remain_durable(self):
        key, db = self.node()
        before_version = self.snapshot(key)[0]
        with db:
            db.execute('CREATE TABLE migration_fixture(value TEXT NOT NULL)')
        self.assertEqual(self.snapshot(key)[0], before_version+1,
                         'A schema migration must publish even without inserted/updated rows')
        with db:
            db.execute('PRAGMA user_version=37')
        self.assertEqual(self.snapshot(key)[0], before_version+2,
                         'A PRAGMA metadata change must publish even without row changes')
        restarted = self.factory.connection(key)
        try:
            self.assertEqual(restarted.execute('PRAGMA user_version').fetchone()[0], 37)
            self.assertEqual(restarted.execute('SELECT count(*) FROM migration_fixture').fetchone()[0], 0)
        finally:
            restarted.close()


if __name__ == '__main__':
    unittest.main()
