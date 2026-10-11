"""Independent negative and recovery checks for neighbour-private hashlocks."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from private_node import Node, PROTOCOL, hash_condition
from node import Node as RosterNode
from run_demo import create_configs


class PrivateAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.configs = create_configs(self.tmp.name, {'alice': 19001, 'bob': 19002, 'doris': 19003})
        self.nodes = {name: Node(config, str(Path(self.tmp.name) / (name + '.sqlite')))
                      for name, config in self.configs.items()}
        for node in self.nodes.values():
            self.addCleanup(node.db.close)

    def entries(self):
        return [(name, dict(row)) for name, node in self.nodes.items()
                for row in node.db.execute('SELECT * FROM outbox')]

    def deliver(self, entry, duplicate=False):
        sender, row = entry
        payload = json.loads(row['data'])
        self.nodes[row['peer']].receive(sender, payload)
        if duplicate:
            self.nodes[row['peer']].receive(sender, payload)
        with self.nodes[sender].db:
            self.nodes[sender].db.execute('DELETE FROM outbox WHERE id=?', (row['id'],))
        return payload

    def drain(self):
        for _ in range(100):
            entries = self.entries()
            if not entries:
                return
            self.deliver(entries[-1], duplicate=True)
        self.fail('Protocol failed to drain within 100 deliveries')

    def start_prepared(self):
        ident = self.nodes['alice'].discover(3)['id']
        self.drain()
        self.assertTrue(all(node.proposal(ident)['prepared'] for node in self.nodes.values()))
        return ident

    def approve(self, name, ident):
        node = self.nodes[name]
        node.approve(ident, json.loads(node.proposal(ident)['data'])['digest'])

    def wire(self, ident, kind, **changes):
        stored = json.loads(self.nodes['alice'].proposal(ident)['data'])
        return dict(dict(kind=kind, id=ident, condition=stored['condition'], amount=stored['amount'],
                         protocol=PROTOCOL, message_id=uuid.uuid4().hex), **changes)

    def test_context_hash_binds_id_amount_and_protocol(self):
        preimage = 'ab' * 32
        a = hash_condition('01' * 32, 3, preimage)
        self.assertNotEqual(a, hash_condition('02' * 32, 3, preimage))
        self.assertNotEqual(a, hash_condition('01' * 32, 4, preimage))
        for invalid in ('abc', 'AB' * 32, 'zz' * 32):
            with self.assertRaises(ValueError):
                hash_condition('01' * 32, 3, invalid)

    def test_probe_reflection_does_not_establish_two_party_cycle(self):
        origin = self.nodes['alice']
        ident = origin.discover(3)['id']
        payload = self.wire(ident, 'probe')
        origin.receive('bob', payload)
        self.assertIsNone(origin.proposal(ident)['prev'])
        self.assertFalse(origin.proposal(ident)['prepared'])
        self.assertEqual(origin.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 0)
        self.assertEqual(origin.receipts(), [])

    def test_repeated_visit_cannot_rewrite_bound_neighbours(self):
        ident = self.nodes['alice'].discover(3)['id']
        self.deliver(self.entries()[0])
        bob = self.nodes['bob']
        self.assertEqual((bob.proposal(ident)['prev'], bob.proposal(ident)['next']), ('alice', 'doris'))
        bob.receive('doris', self.wire(ident, 'probe'))
        self.assertEqual((bob.proposal(ident)['prev'], bob.proposal(ident)['next']), ('alice', 'doris'))
        rejects = [json.loads(r['data']) for r in bob.db.execute('SELECT * FROM outbox') if r['peer'] == 'doris']
        self.assertIn('probe_rejected', [msg['kind'] for msg in rejects])

    def test_wrong_missing_or_changed_context_fulfillment_rejected(self):
        ident = self.start_prepared()
        self.approve('bob', ident)
        bob = self.nodes['bob']
        secret = self.nodes['alice'].db.execute('SELECT preimage FROM private_secrets WHERE id=?', (ident,)).fetchone()[0]
        bad = [self.wire(ident, 'fulfill'), self.wire(ident, 'fulfill', preimage='00' * 32),
               self.wire(ident, 'fulfill', preimage=secret, amount=2),
               self.wire(ident, 'fulfill', preimage=secret, id='ff' * 32)]
        for message in bad:
            with self.assertRaises(ValueError):
                bob.receive('alice', message)
        self.assertEqual((bob.balance('alice'), bob.balance('doris')), (7, -3))
        self.assertEqual(bob.proposal(ident)['status'], 'pending')
        self.assertEqual(bob.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 2)

    def test_secret_not_released_until_last_participant_approves(self):
        ident = self.start_prepared()
        for name in ('alice', 'bob'):
            self.approve(name, ident)
        self.drain()
        for node in self.nodes.values():
            self.assertEqual(node.proposal(ident)['status'], 'pending')
            self.assertNotIn('preimage', json.dumps(node.state()))
        self.approve('doris', ident)
        self.drain()
        for node in self.nodes.values():
            self.assertEqual(node.proposal(ident)['status'], 'committed')
            self.assertEqual(len(node.receipts()), 1)
            self.assertTrue(node.receipts()[0]['local_fulfilled'])
            self.assertEqual(node.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 0)

    def test_decline_before_reveal_aborts_without_spending(self):
        ident = self.start_prepared()
        self.approve('alice', ident)
        self.approve('bob', ident)
        doris = self.nodes['doris']
        doris.decline(ident, json.loads(doris.proposal(ident)['data'])['digest'])
        self.drain()
        for name, node in self.nodes.items():
            self.assertEqual(node.proposal(ident)['status'], 'aborted')
            self.assertEqual({r['peer']: r['balance'] for r in node.db.execute('SELECT * FROM balances')},
                             {peer: data['balance'] for peer, data in self.configs[name]['peers'].items()})
            self.assertEqual(node.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 0)
            self.assertNotIn('preimage', json.dumps(node.receipts()))

    def test_wrong_phase_sender_and_roster_fields_rejected(self):
        ident = self.start_prepared()
        bob = self.nodes['bob']
        for kind in ('prepare', 'ready', 'abort'):
            with self.assertRaises(ValueError):
                bob.receive('doris', self.wire(ident, kind))
        for fields in ({'path': ['alice', 'bob', 'doris']}, {'participants': 3}, {'origin': 'alice'}, {'hop_count': 3}):
            with self.assertRaises(ValueError):
                bob.receive('alice', self.wire(ident, 'prepare', **fields))
        self.assertEqual(bob.proposal(ident)['status'], 'pending')

    def test_prepared_restart_keeps_locks_and_no_secret(self):
        ident = self.start_prepared()
        restored = Node(self.configs['bob'], str(Path(self.tmp.name) / 'bob.sqlite'))
        self.addCleanup(restored.db.close)
        self.assertEqual(restored.proposal(ident)['status'], 'pending')
        self.assertEqual(restored.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 2)
        self.assertEqual(restored.db.execute('SELECT count(*) FROM private_secrets').fetchone()[0], 0)
        self.assertEqual(restored.receipts(), [])

    def test_nonorigin_subcycle_rejects_and_quiesces(self):
        balances = {'o': {'a': -7}, 'a': {'o': 7, 'b': -7, 'c': 7},
                    'b': {'a': 7, 'c': -7}, 'c': {'b': 7, 'a': -7}}
        self.nodes = {}
        for name, peers in balances.items():
            config = dict(node=name, mode='testnet', token='client-' + name,
                          peers={peer: dict(balance=balance, url='http://127.0.0.1:19001', key='edge-' + ''.join(sorted((name, peer))))
                                 for peer, balance in peers.items()})
            self.nodes[name] = Node(config, str(Path(self.tmp.name) / ('collision-' + name + '.sqlite')))
            self.addCleanup(self.nodes[name].db.close)
        ident = self.nodes['o'].discover(3)['id']
        self.drain()
        for name, node in self.nodes.items():
            self.assertEqual(node.proposal(ident)['status'], 'aborted')
            self.assertEqual({r['peer']: r['balance'] for r in node.db.execute('SELECT * FROM balances')}, balances[name])
            self.assertEqual(node.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 0)
        self.assertEqual(self.entries(), [])

    def test_terminal_fulfillment_semantic_replay_is_quiescent(self):
        ident = self.start_prepared()
        for name in self.nodes:
            self.approve(name, ident)
        self.drain()
        bob = self.nodes['bob']
        secret = bob.receipts()[0]['preimage']
        bob.receive('alice', self.wire(ident, 'fulfill', preimage=secret))
        self.assertEqual(self.entries(), [])
        self.assertEqual((bob.balance('alice'), bob.balance('doris')), (4, 0))
        self.assertEqual(len(bob.receipts()), 1)

    def test_correct_preimage_does_not_replace_local_consent(self):
        ident = self.start_prepared()
        secret = self.nodes['alice'].db.execute('SELECT preimage FROM private_secrets WHERE id=?', (ident,)).fetchone()[0]
        bob = self.nodes['bob']
        with self.assertRaises(ValueError):
            bob.receive('alice', self.wire(ident, 'fulfill', preimage=secret))
        self.assertEqual(bob.proposal(ident)['status'], 'pending')
        self.assertEqual(bob.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 2)

    def test_released_origin_rejects_abort_and_restart_recovers_outbox(self):
        ident = self.start_prepared()
        for name in self.nodes:
            self.approve(name, ident)
        origin = self.nodes['alice']
        for _ in range(30):
            if origin.proposal(ident)['status'] == 'committed':
                break
            self.deliver(self.entries()[0])
        self.assertEqual(origin.proposal(ident)['status'], 'committed')
        with self.assertRaises(ValueError):
            origin.receive('doris', self.wire(ident, 'abort'))
        origin.receive('bob', self.wire(ident, 'reject'))
        origin.receive('doris', self.wire(ident, 'probe'))
        self.assertEqual(origin.proposal(ident)['status'], 'committed')
        kinds = [json.loads(row['data'])['kind'] for row in origin.db.execute('SELECT * FROM outbox')]
        self.assertEqual(kinds, ['fulfill'])
        restored = Node(self.configs['alice'], str(Path(self.tmp.name) / 'alice.sqlite'))
        self.addCleanup(restored.db.close)
        self.nodes['alice'] = restored
        self.drain()
        for node in self.nodes.values():
            self.assertEqual(node.proposal(ident)['status'], 'committed')
            self.assertEqual(len(node.receipts()), 1)

    def test_aborted_origin_never_releases_on_late_ready(self):
        ident = self.start_prepared()
        origin = self.nodes['alice']
        origin.decline(ident, json.loads(origin.proposal(ident)['data'])['digest'])
        origin.receive('doris', self.wire(ident, 'ready'))
        self.drain()
        self.assertEqual(origin.proposal(ident)['status'], 'aborted')
        self.assertNotIn('preimage', json.dumps(origin.state()))
        self.assertEqual(origin.balance('bob'), -7)

    def test_intersecting_probes_fail_fast_and_leave_no_abandoned_locks(self):
        ids = [node.discover(3)['id'] for node in self.nodes.values()]
        self.drain()
        for node in self.nodes.values():
            for row in list(node.db.execute("SELECT * FROM proposals WHERE status='pending'")):
                node.approve(row['id'], json.loads(row['data'])['digest'])
        self.drain()
        for name, node in self.nodes.items():
            self.assertEqual(node.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 0)
            self.assertEqual(sum(r['balance'] for r in node.db.execute('SELECT balance FROM balances')),
                             sum(config['balance'] for config in self.configs[name]['peers'].values()))
            for row in node.db.execute('SELECT status FROM proposals'):
                self.assertIn(row['status'], ('committed', 'aborted'))
        self.assertEqual(self.entries(), [])

    def test_legacy_node_refuses_private_database_without_mutating_it(self):
        ident = self.start_prepared()
        private = self.nodes['alice']
        before = '\n'.join(private.db.iterdump())
        with self.assertRaises(ValueError):
            RosterNode(self.configs['alice'], str(Path(self.tmp.name) / 'alice.sqlite'))
        self.assertEqual('\n'.join(private.db.iterdump()), before)
        self.assertEqual(private.proposal(ident)['status'], 'pending')

    def test_existing_roster_database_is_not_migrated(self):
        path = str(Path(self.tmp.name) / 'old.sqlite')
        old = RosterNode(self.configs['alice'], path)
        old.db.close()
        with self.assertRaises(ValueError):
            Node(self.configs['alice'], path)


if __name__ == '__main__':
    unittest.main()
