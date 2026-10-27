"""Release must reject partially migrated storage before runtime provisioning."""
import os
import unittest
import uuid
from unittest.mock import call, patch

import hosted_release
from hosted_storage import PgStoreFactory, TABLE, LEGACY_TABLE


class ReleaseGateInvocation(unittest.TestCase):
    def test_release_checks_all_scopes_before_provisioning_accounts(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://test-only/fixture'}), \
                patch.object(hosted_release, 'PgStoreFactory', autospec=True) as constructor:
            hosted_release.main()
        factory = constructor.return_value
        self.assertEqual(factory.mock_calls,
                         [call.initialize(), call.assert_ready(), call.create('accounts'), call.close()])

    def test_failed_gate_does_not_provision_accounts_and_closes_pool(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://test-only/fixture'}), \
                patch.object(hosted_release, 'PgStoreFactory', autospec=True) as constructor:
            factory = constructor.return_value
            factory.assert_ready.side_effect = RuntimeError('Legacy scopes remain unmigrated')
            with self.assertRaisesRegex(RuntimeError, 'unmigrated'):
                hosted_release.main()
        factory.create.assert_not_called()
        factory.close.assert_called_once()


@unittest.skipUnless(os.environ.get('LEDGERLOOPS_TEST_POSTGRES_DSN'),
                     'Set LEDGERLOOPS_TEST_POSTGRES_DSN for native release readiness tests')
class NativeReleaseReadiness(unittest.TestCase):
    def setUp(self):
        self.factory = PgStoreFactory(os.environ['LEDGERLOOPS_TEST_POSTGRES_DSN'])
        self.factory.initialize()
        self.keys = []
        with self.factory._pool.connection() as connection:
            connection.execute(f'''CREATE TABLE IF NOT EXISTS public.{LEGACY_TABLE}(
                node_id TEXT PRIMARY KEY, version BIGINT NOT NULL DEFAULT 0,
                image BYTEA NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)''')

    def tearDown(self):
        with self.factory._pool.connection() as connection, connection.transaction():
            # Remove only this test's random scopes. Deleting the native marker
            # first lets the legacy fence permit explicit fixture cleanup.
            connection.execute(f'DELETE FROM public.{TABLE} WHERE node_id = ANY(%s)', (self.keys,))
            connection.execute(f'DELETE FROM public.{LEGACY_TABLE} WHERE node_id = ANY(%s)', (self.keys,))
        self.factory.close()

    def legacy(self):
        key = 'release-test:' + uuid.uuid4().hex
        self.keys.append(key)
        with self.factory._pool.connection() as connection:
            connection.execute(f'INSERT INTO public.{LEGACY_TABLE}(node_id,version,image) VALUES(%s,7,%s)',
                               (key, b'fixture-image-not-read-by-metadata-preflight'))
        return key

    def mark(self, key, *, source_version=7, fingerprint='a' * 64):
        with self.factory._pool.connection() as connection:
            connection.execute(f'''INSERT INTO public.{TABLE}
                (node_id,legacy_snapshot_version,legacy_snapshot_sha256) VALUES(%s,%s,%s)''',
                (key, source_version, fingerprint))

    def test_unmigrated_peer_blocks_release_until_marked(self):
        key = self.legacy()
        with self.assertRaisesRegex(RuntimeError, 'migrat|Legacy|legacy'):
            self.factory.assert_ready()
        self.mark(key)
        self.factory.assert_ready()

    def test_marker_without_fingerprint_is_not_a_completed_migration(self):
        key = self.legacy()
        self.mark(key, fingerprint=None)
        with self.assertRaisesRegex(RuntimeError, 'migrat|Legacy|legacy'):
            self.factory.assert_ready()

    def test_changed_legacy_version_blocks_release(self):
        key = self.legacy()
        self.mark(key, source_version=6)
        with self.assertRaisesRegex(RuntimeError, 'migrat|Legacy|legacy'):
            self.factory.assert_ready()

    def test_metadata_preflight_does_not_rewrite_native_actor_versions(self):
        key = self.legacy()
        self.mark(key)
        with self.factory._pool.connection() as connection:
            before = connection.execute(f'SELECT version,updated_at FROM public.{TABLE} WHERE node_id=%s', (key,)).fetchone()
        self.factory.assert_ready()
        self.factory.assert_ready()
        with self.factory._pool.connection() as connection:
            after = connection.execute(f'SELECT version,updated_at FROM public.{TABLE} WHERE node_id=%s', (key,)).fetchone()
        self.assertEqual(after, before)


if __name__ == '__main__':
    unittest.main()
