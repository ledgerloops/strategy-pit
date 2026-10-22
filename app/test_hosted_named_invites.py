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
