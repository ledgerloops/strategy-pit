"""Real local databases and neighbour envelopes for surplus-bit hashlocks.

The harness delivers addressed messages and inspects outcomes. It never supplies
an actor with a path, aggregate cost, remote balance or global clearing decision.
"""
from copy import deepcopy
import json
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch

from private_node import Node, HEADROOM_POLICY, HEADROOM_SCHEME, hash_headroom_condition
from verify_private_receipt import verify


class HeadroomSettlementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.nodes = {}
        self.addCleanup(lambda: [n.db.close() for n in self.nodes.values()])
        self.transcript = []

    def start(self, edges):
        self.configs = {}
        for a, b, balance in edges:
            key = secrets.token_urlsafe(24)
            for name, peer, value in ((a, b, balance), (b, a, -balance)):
                config = self.configs.setdefault(name, dict(node=name, mode='testnet', token=secrets.token_urlsafe(24), peers={}))
                config['peers'][peer] = dict(key=key, url='http://127.0.0.1:1', balance=value)
        for name, config in self.configs.items():
            self.nodes[name] = Node(config, str(Path(self.tmp.name)/(name+'.sqlite')))
        self.drain()
        for node in self.nodes.values():
            for peer in node.peers:
                node.set_preferences(peer, dict(expected_revision=1, credit_limit=20,
                    comfort_min=-20, comfort_max=20, auto_adjust=True))
        self.drain()

    def entries(self):
        return [(name, dict(row)) for name, node in self.nodes.items()
                for row in node.db.execute('SELECT * FROM outbox')]

    def deliver(self, entry, mutate=None):
        sender, row = entry
        data = json.loads(row['data'])
        if mutate:
            mutate(data)
        self.transcript.append((sender, row['peer'], deepcopy(data)))
        self.nodes[row['peer']].receive(sender, data)
        with self.nodes[sender].db:
            self.nodes[sender].db.execute('DELETE FROM outbox WHERE id=?', (row['id'],))

    def drain(self):
        for _ in range(1000):
            entries = self.entries()
            if not entries:
                return
            self.deliver(entries[0])
        self.fail('Messages did not drain')

    def balances(self):
        return {name: {p: n.balance(p) for p in n.peers} for name, n in self.nodes.items()}

    def gross(self):
        return sum(abs(v) for peers in self.balances().values() for v in peers.values())//2

    def prepared(self, origin, amount=1):
        ident = self.nodes[origin].discover(amount, mode='headroom')['id']
        self.drain()
        active = [n for n in self.nodes.values() if n.db.execute('SELECT 1 FROM proposals WHERE id=? AND status=?', (ident, 'pending')).fetchone()]
        self.assertGreaterEqual(len(active), 3)
        return ident, active

    def approve_all(self, ident, active):
        for node in active:
            data = json.loads(node.proposal(ident)['data'])
            node.approve(ident, data['digest'])
        self.drain()
        for node in active:
            self.assertEqual(node.proposal(ident)['status'], 'committed')
            receipt = next(r for r in node.receipts() if r['id'] == ident)
            self.assertEqual(receipt['policy'], HEADROOM_POLICY)
            self.assertEqual(receipt['hashlock_scheme'], HEADROOM_SCHEME)
            self.assertTrue(verify(receipt)['valid'])

    def test_zero_link_shortens_three_hops_to_one_with_real_hashlock(self):
        self.start([('C','E',-1), ('E','F',-1), ('F','A',-1), ('C','A',0)])
        before = self.balances()
        ident, active = self.prepared('E')
        self.assertEqual(self.balances(), before)  # discovery is not settlement
        self.approve_all(ident, active)
        self.assertEqual(self.gross(), 1)
        self.assertEqual(self.nodes['C'].balance('A'), -1)
        self.assertEqual({k: sum(v.values()) for k,v in before.items()},
                         {k: sum(v.values()) for k,v in self.balances().items()})
        for sender, target, packet in self.transcript:
            self.assertIn(target, self.nodes[sender].peers)
            self.assertFalse({'path','route','participants','length','hops','total','cost'} & packet.keys())
            if packet.get('clearing_mode') == 'headroom':
                self.assertEqual('surplus' in packet, packet['kind'] in ('probe','prepare'))

    def test_zero_link_shortens_two_hops_to_one(self):
        self.start([('C','D',-1), ('D','A',-1), ('C','A',0)])
        ident, active = self.prepared('D')
        self.approve_all(ident, active)
        self.assertEqual(self.gross(), 1)
        self.assertEqual(self.nodes['C'].balance('A'), -1)

    def test_prior_three_unit_trap_repairs_to_two_and_helper_increases(self):
        self.start([('A','B',0), ('B','C',0), ('C','D',0), ('D','A',0),
                    ('C','E',-1), ('E','F',-1), ('F','A',-1)])
        # Local randomness chooses D at A; no actor receives a prescribed route.
        with patch('private_node.secrets.choice', side_effect=lambda items: items[-1]):
            ident, active = self.prepared('E')
        self.approve_all(ident, active)
        self.assertEqual(self.gross(), 2)
        receipt = self.nodes['D'].receipts()[0]
        self.assertTrue(receipt['surplus_in'])
        self.assertFalse(receipt['surplus_out'])
        self.assertEqual(sum(abs(c['after'])-abs(c['before']) for c in receipt['changes']), 2)

    def test_restart_pending_and_duplicate_fulfillment(self):
        self.start([('C','D',-1), ('D','A',-1), ('C','A',0)])
        ident, active = self.prepared('D')
        for name, node in list(self.nodes.items()):
            node.db.close()
            self.nodes[name] = Node(self.configs[name], str(Path(self.tmp.name)/(name+'.sqlite')))
        self.approve_all(ident, list(self.nodes.values()))
        after = self.balances()
        for sender, target, packet in list(self.transcript):
            if packet.get('kind') == 'fulfill':
                self.nodes[target].receive(sender, packet)
        self.assertEqual(self.balances(), after)

    def test_changed_surplus_on_prepare_aborts_without_settlement(self):
        self.start([('C','E',-1), ('E','F',-1), ('F','A',-1), ('C','A',0)])
        before = self.balances()
        ident = self.nodes['E'].discover(1, mode='headroom')['id']
        for _ in range(30):
            entry = self.entries()[0]
            if json.loads(entry[1]['data'])['kind'] == 'prepare':
                self.deliver(entry, lambda data: data.update(surplus=not data['surplus']))
                break
            self.deliver(entry)
        else:
            self.fail('No prepare message')
        self.drain()
        self.assertEqual(self.balances(), before)
        self.assertEqual(self.nodes['E'].proposal(ident)['status'], 'aborted')
        self.assertTrue(all(not n.db.execute('SELECT 1 FROM reservations').fetchone() for n in self.nodes.values()))

    def preference_race(self, probes, name, peer):
        self.start([('C','E',-1), ('E','F',-1), ('F','A',-1), ('C','A',0)])
        before = self.balances()
        ident = self.nodes['E'].discover(1, mode='headroom')['id']
        for _ in range(probes):
            entry = self.entries()[0]
            self.assertEqual(json.loads(entry[1]['data'])['kind'], 'probe')
            self.deliver(entry)
        self.nodes[name].set_preferences(peer, dict(expected_revision=2, credit_limit=19,
            comfort_min=-19, comfort_max=19, auto_adjust=True))
        self.drain()
        self.assertEqual(self.nodes['E'].proposal(ident)['status'], 'aborted')
        self.assertEqual(self.balances(), before)
        self.assertTrue(all(not n.db.execute('SELECT 1 FROM reservations').fetchone() for n in self.nodes.values()))

    def test_origin_preference_race_before_closure_aborts(self):
        self.preference_race(3, 'E', 'F')

    def test_transit_preference_race_before_prepare_aborts(self):
        self.preference_race(4, 'F', 'A')

    def test_receipt_tampering_and_context_separation(self):
        self.start([('C','D',-1), ('D','A',-1), ('C','A',0)])
        ident, active = self.prepared('D')
        self.approve_all(ident, active)
        receipt = self.nodes['D'].receipts()[0]
        for field in ('surplus_out','surplus_origin'):
            altered = deepcopy(receipt)
            altered[field] = not altered[field]
            with self.assertRaises(ValueError):
                verify(altered)
        self.assertNotEqual(receipt['condition'], hash_headroom_condition(ident, 1, receipt['preimage'], -receipt['direction']))
        altered = deepcopy(receipt)
        altered.update(clearing_mode='comfort', policy='bilateral-comfort-v1', hashlock_scheme='sha256-comfort-v1')
        with self.assertRaises(ValueError):
            verify(altered)

    def test_no_automatic_permission_and_no_zero_crossing(self):
        self.start([('C','D',-1), ('D','A',-1), ('C','A',0)])
        with self.assertRaises(ValueError):
            self.nodes['D'].discover(2, mode='headroom')
        self.nodes['C'].set_preferences('A', dict(expected_revision=2, credit_limit=20,
            comfort_min=-20, comfort_max=20, auto_adjust=False))
        self.drain()
        before = self.balances()
        ident = self.nodes['D'].discover(1, mode='headroom')['id']
        self.drain()
        self.assertEqual(self.nodes['D'].proposal(ident)['status'], 'aborted')
        self.assertEqual(self.balances(), before)

    def test_fresh_account_with_no_neighbours(self):
        n = Node(dict(mode='testnet', node='new', token='local-test-token', peers={}), ':memory:')
        self.addCleanup(n.db.close)
        self.assertEqual(n.state()['balances'], [])
        with self.assertRaises(ValueError):
            n.discover(1, mode='headroom')


if __name__ == '__main__':
    unittest.main()
