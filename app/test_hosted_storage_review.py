"""Independent snapshot write-amplification regressions on isolated TEST rows.

Never connects to production; these tests use the explicit test PostgreSQL DSN
and remove only their randomly named fixture keys. Header/row-count shortcuts
must not discard genuine schema or PRAGMA migrations.
"""
import os
import secrets
import unittest

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
