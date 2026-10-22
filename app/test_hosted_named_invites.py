"""Named invitations use display metadata and preserve existing local ledgers."""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from hosted_runtime import HostedRuntime


class LocalStores:
    """Isolated durable SQLite stores; no production credentials or graph access."""
    def __init__(self, root):
        self.root = Path(root)

    def path(self, key):
        return self.root / (hashlib.sha256(key.encode()).hexdigest()+'.sqlite')

    def create(self, key):
        self.path(key).touch(exist_ok=True)

    def connection(self, key):
        return sqlite3.connect(self.path(key))


class HostedNamedInviteTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.stores = LocalStores(directory.name)
        self.runtime = HostedRuntime(self.stores, 'https://app.ledgerloops.com')
        self.alice, self.bob, self.carol = ('n_'+c*32 for c in 'abc')
        for node_id, name in ((self.alice, 'Alice'), (self.bob, 'Bob'), (self.carol, 'Carol')):
            self.runtime.provision(dict(node_id=node_id, name=name))

    def contact(self, node_id):
        return self.runtime.state(node_id)['contacts'][0]

    def test_share_link_and_preview_only_include_public_invite_metadata(self):
        invite = self.runtime.invite(self.alice, ' Robert ')
        self.assertEqual(invite['inviter_name'], 'Alice')
        self.assertEqual(invite['peer_name'], 'Robert')
        url = urlsplit(invite['invite_url'])
        self.assertEqual(url.scheme+'://'+url.netloc+url.path, 'https://app.ledgerloops.com/')
        self.assertEqual(url.query, '')
        self.assertEqual(parse_qs(url.fragment), {'invite': [invite['invite_token']]})
        preview = self.runtime.preview_invite(invite['invite_token'])
        self.assertEqual(preview, dict(inviter_name='Alice', peer_name='Robert', expires_at=invite['expires_at']))
        with self.runtime.node(self.alice) as node:
            self.assertNotIn(node.token, json.dumps(preview))
        self.assertEqual(self.runtime.state(self.alice)['contacts'], [])

    def test_accept_records_each_side_name_without_changing_routing_identity(self):
        invitation = self.runtime.invite(self.alice, 'Robert')['invite_token']
        self.runtime.accept_invite(self.bob, invitation)
        self.assertEqual((self.contact(self.alice)['peer'], self.contact(self.alice)['name']), (self.bob, 'Robert'))
        self.assertEqual((self.contact(self.bob)['peer'], self.contact(self.bob)['name']), (self.alice, 'Alice'))
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            self.runtime.preview_invite(invitation)
        with self.assertRaisesRegex(ValueError, 'already accepted'):
            self.runtime.accept_invite(self.carol, invitation)

    def test_new_defaults_apply_only_to_new_relationships(self):
        invitation = self.runtime.invite(self.alice, 'Bob')['invite_token']
        self.runtime.accept_invite(self.bob, invitation)
        expected = dict(revision=1, credit_limit=10, comfort_min=-10, comfort_max=10, auto_adjust=True)
        self.assertEqual(self.contact(self.alice)['own'], expected)
        self.assertEqual(self.contact(self.bob)['own'], expected)
        with self.runtime.node(self.alice) as node:
            # Represent a retained legacy relationship whose limits were zero.
            previous = dict(revision=1, credit_limit=0, comfort_min=0, comfort_max=0, auto_adjust=False)
            node.db.execute('UPDATE contacts SET own=? WHERE peer=?', (json.dumps(previous), self.bob))
        restarted = HostedRuntime(self.stores, self.runtime.origin)
        restarted.provision(dict(node_id=self.alice, name='Alice'))
        restarted.accept_invite(self.bob, invitation)
        restarted.accept_invite(self.bob, restarted.invite(self.alice)['invite_token'])
        self.assertEqual(self.contact(self.alice)['own'], previous)
        self.assertEqual(self.contact(self.bob)['own'], expected)

    def legacy_defaults(self, node_id, own, *, reserved=False):
        with self.runtime.node(node_id) as node:
            node.db.execute("DELETE FROM meta WHERE k='hosted_automatic_clearing_v1'")
            node.db.execute("UPDATE meta SET v='false' WHERE k='hosted_automation'")
            node.db.execute("UPDATE meta SET v='true' WHERE k='paused'")
            node.db.execute('UPDATE contacts SET own=?', (json.dumps(own),))
            node.db.execute('DELETE FROM outbox')
            if reserved:
                node.db.execute('INSERT INTO reservations VALUES(?,?)', (self.bob, 'retained-proposal'))

    def test_policy_migrates_only_untouched_defaults_once_without_resetting_state(self):
        self.runtime.accept_invite(self.bob, self.runtime.invite(self.alice)['invite_token'])
        previous = dict(revision=1, credit_limit=10, comfort_min=-10, comfort_max=10, auto_adjust=False)
        with self.runtime.node(self.alice) as node:
            token, peer_key = node.token, node.peers[self.bob]['key']
            node.db.execute('UPDATE balances SET balance=-7')
        self.legacy_defaults(self.alice, previous)
        state = self.runtime.state(self.alice)
        self.assertTrue(state['automation']['enabled'])
        self.assertTrue(state['paused'])
        self.assertEqual(state['balances'][0]['balance'], -7)
        self.assertEqual(state['contacts'][0]['own'], dict(previous, revision=2, auto_adjust=True))
        with self.runtime.node(self.alice) as node:
            self.assertEqual((node.token, node.peers[self.bob]['key']), (token, peer_key))
            messages = [json.loads(row['data']) for row in node.db.execute('SELECT * FROM outbox')]
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0]['preferences'], dict(previous, revision=2, auto_adjust=True))
        self.runtime.automation(self.alice, False)
        restarted = HostedRuntime(self.stores, self.runtime.origin)
        restarted.provision(dict(node_id=self.alice, name='Preserve original'))
        self.assertFalse(restarted.state(self.alice)['automation']['enabled'])
        with restarted.node(self.alice) as node:
            self.assertEqual(node.db.execute('SELECT count(*) FROM outbox').fetchone()[0], 1)

    def test_migration_preserves_custom_bounds_and_explicit_assistance_opt_out(self):
        self.runtime.accept_invite(self.bob, self.runtime.invite(self.alice)['invite_token'])
        for own in (dict(revision=2, credit_limit=10, comfort_min=-10, comfort_max=10, auto_adjust=False),
                    dict(revision=1, credit_limit=3, comfort_min=-2, comfort_max=1, auto_adjust=False)):
            with self.subTest(own=own):
                self.legacy_defaults(self.alice, own)
                self.assertEqual(self.runtime.state(self.alice)['contacts'][0]['own'], own)
                with self.runtime.node(self.alice) as node:
                    self.assertEqual(node.db.execute('SELECT count(*) FROM outbox').fetchone()[0], 0)

    def test_migration_defers_reserved_revision_and_retries_after_restart(self):
        self.runtime.accept_invite(self.bob, self.runtime.invite(self.alice)['invite_token'])
        previous = dict(revision=1, credit_limit=0, comfort_min=0, comfort_max=0, auto_adjust=False)
        self.legacy_defaults(self.alice, previous, reserved=True)
        state = self.runtime.state(self.alice)
        self.assertEqual(state['contacts'][0]['own'], previous)
        self.assertEqual(state['contacts'][0]['reserved_by'], 'retained-proposal')
        with self.runtime.node(self.alice) as node:
            self.assertEqual(json.loads(node.db.execute("SELECT v FROM meta WHERE k='hosted_automatic_clearing_v1'").fetchone()[0]), [self.bob])
            node.db.execute('DELETE FROM reservations')
        restarted = HostedRuntime(self.stores, self.runtime.origin)
        self.assertEqual(restarted.state(self.alice)['contacts'][0]['own'], dict(previous, revision=2, auto_adjust=True))
        with restarted.node(self.alice) as node:
            self.assertEqual(node.db.execute("SELECT v FROM meta WHERE k='hosted_automatic_clearing_v1'").fetchone()[0], '[]')

    def test_retries_new_and_crossed_invites_preserve_names_keys_and_balances(self):
        first = self.runtime.invite(self.alice, 'Robert')['invite_token']
        crossed = self.runtime.invite(self.bob, 'Alicia')['invite_token']
        self.runtime.accept_invite(self.bob, first)
        with self.runtime.node(self.alice) as node:
            original_key, original_token = node.peers[self.bob]['key'], node.token
            node.db.execute('UPDATE balances SET balance=-7 WHERE peer=?', (self.bob,))
        self.runtime.accept_invite(self.bob, first)
        self.runtime.accept_invite(self.alice, crossed)
        other = self.runtime.invite(self.alice, 'Replace label')['invite_token']
        self.runtime.accept_invite(self.bob, other)
        self.assertEqual(self.contact(self.alice)['name'], 'Robert')
        self.assertEqual(self.contact(self.bob)['name'], 'Alice')
        self.assertEqual(self.contact(self.alice)['balance'], -7)
        with self.runtime.node(self.alice) as node:
            self.assertEqual(node.peers[self.bob]['key'], original_key)
            self.assertEqual(node.token, original_token)
        with self.runtime.node(self.bob) as node:
            self.assertEqual(node.peers[self.alice]['key'], original_key)

    def test_old_invites_migrate_on_node_access_and_reprovision_without_reset(self):
        invitation = self.runtime.invite(self.alice)['invite_token']
        db = self.stores.connection(self.runtime.key(self.alice))
        with db:
            db.execute('ALTER TABLE hosted_invites RENAME TO named_invites')
            db.execute('CREATE TABLE hosted_invites(token_hash TEXT PRIMARY KEY,expires REAL NOT NULL,accepted_by TEXT,peer_key TEXT)')
            db.execute('INSERT INTO hosted_invites SELECT token_hash,expires,accepted_by,peer_key FROM named_invites')
            db.execute('DROP TABLE named_invites')
        db.close()
        self.runtime.provision(dict(node_id=self.alice, name='Replacement'))
        self.assertEqual(self.runtime.preview_invite(invitation)['inviter_name'], 'Alice')
        self.assertEqual(self.runtime.preview_invite(invitation)['peer_name'], '')
        self.runtime.accept_invite(self.bob, invitation)
        self.assertEqual(self.contact(self.alice)['name'], '')
        self.assertEqual(self.contact(self.bob)['name'], 'Alice')

    def test_name_validation_expiry_and_invalid_bearers(self):
        for value in (None, 12, 'x'*81, 'Bob\nSmith', 'Bob\x00', 'Bob\x7f', 'Bob\u202e'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Peer name'):
                self.runtime.invite(self.alice, value)
        invite = self.runtime.invite(self.alice, 'Élodie')
        for token in ('', None, 'bad.token', self.alice+'.'+('x'*43), invite['invite_token']+'!'):
            with self.subTest(token=token), self.assertRaises(ValueError):
                self.runtime.preview_invite(token)
        with patch('hosted_runtime.time.time', return_value=invite['expires_at']+1):
            with self.assertRaisesRegex(ValueError, 'expired'):
                self.runtime.preview_invite(invite['invite_token'])
            with self.assertRaisesRegex(ValueError, 'expired'):
                self.runtime.accept_invite(self.bob, invite['invite_token'])

    def test_interrupted_connection_retry_preserves_intended_names(self):
        invitation = self.runtime.invite(self.alice, 'Robert')['invite_token']
        connect = self.runtime._connect_local

        def interrupted(node_id, peer, key):
            if node_id == self.alice:
                raise RuntimeError('Interrupted between endpoints')
            connect(node_id, peer, key)

        with patch.object(self.runtime, '_connect_local', interrupted):
            with self.assertRaises(RuntimeError):
                self.runtime.accept_invite(self.bob, invitation)
        restarted = HostedRuntime(self.stores, self.runtime.origin)
        restarted.accept_invite(self.bob, invitation)
        self.assertEqual(self.contact(self.alice)['name'], 'Robert')
        self.assertEqual(self.contact(self.bob)['name'], 'Alice')


if __name__ == '__main__':
    unittest.main()
