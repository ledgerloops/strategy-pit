"""Independent admission, consent, and crash-boundary comfort protocol checks."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from private_node import Node, hash_condition, hash_comfort_condition
from run_demo import create_configs
from verify_private_receipt import verify


class ComfortSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.configs = create_configs(self.tmp.name, {'alice': 19101, 'bob': 19102, 'doris': 19103})
        balances = {'alice': {'bob': -2, 'doris': 0}, 'bob': {'alice': 2, 'doris': 0}, 'doris': {'alice': 0, 'bob': 0}}
        for name, config in self.configs.items():
            for peer in config['peers']:
                config['peers'][peer]['balance'] = balances[name][peer]
        self.nodes = {name: Node(config, str(Path(self.tmp.name) / (name + '.sqlite')))
                      for name, config in self.configs.items()}
        for node in self.nodes.values():
            self.addCleanup(node.db.close)
        self.drain()
        for name, node in self.nodes.items():
            for peer in node.peers:
                width = 0 if {name, peer} == {'alice', 'bob'} else 2
                self.preferences(name, peer, comfort_min=-width, comfort_max=width)
        self.drain()
        self.initial = {name: self.balances(node) for name, node in self.nodes.items()}

    @staticmethod
    def balances(node):
        return {r['peer']: r['balance'] for r in node.db.execute('SELECT * FROM balances')}

    def preferences(self, owner, peer, **updates):
        node = self.nodes[owner]
        current = next(c['own'] for c in node.contacts() if c['peer'] == peer)
        values = dict(credit_limit=10, comfort_min=-2, comfort_max=2, auto_adjust=True)
        values.update(updates)
        return node.set_preferences(peer, dict(values, expected_revision=current['revision']))

    def queue(self):
        return [(name, dict(row)) for name, node in self.nodes.items()
                for row in node.db.execute('SELECT * FROM outbox')]

    def deliver(self, entry, duplicate=False):
        sender, row = entry
        message = json.loads(row['data'])
        self.nodes[row['peer']].receive(sender, message)
        if duplicate:
            self.nodes[row['peer']].receive(sender, message)
        with self.nodes[sender].db:
            self.nodes[sender].db.execute('DELETE FROM outbox WHERE id=?', (row['id'],))
        return message

    def drain(self):
        for _ in range(100):
            entries = self.queue()
            if not entries:
                return
            progressed = False
            for entry in entries:
                try:
                    self.deliver(entry, duplicate=True)
                    progressed = True
                except ValueError as error:
                    if 'deferred until reservation finishes' not in str(error):
                        raise
            if not progressed:
                self.fail('No progress: only deferred messages remain')
        self.fail('Message loop did not terminate')

    def prepare(self):
        ident = self.nodes['alice'].discover(2, mode='comfort')['id']
        self.drain()
        for node in self.nodes.values():
            self.assertEqual(node.proposal(ident)['status'], 'pending')
        return ident

    def approve(self, name, ident):
        node = self.nodes[name]
        node.approve(ident, json.loads(node.proposal(ident)['data'])['digest'])

    def assert_unspent(self):
        for name, node in self.nodes.items():
            self.assertEqual(self.balances(node), self.initial[name])
            self.assertEqual(node.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 0)

    def test_opted_in_zero_links_assist_with_manual_consent_and_net_conservation(self):
        ident = self.prepare()
        self.approve('alice', ident); self.approve('bob', ident)
        self.drain()
        for node in self.nodes.values():
            self.assertEqual(node.proposal(ident)['status'], 'pending')
            self.assertEqual(node.receipts(), [])
        self.approve('doris', ident); self.drain()
        for name, node in self.nodes.items():
            self.assertEqual(sum(self.balances(node).values()), sum(self.initial[name].values()))
            self.assertEqual(node.proposal(ident)['status'], 'committed')
            for peer, value in self.balances(node).items():
                self.assertEqual(value, -self.nodes[peer].balance(name))
        self.assertEqual(self.nodes['alice'].balance('bob'), 0)
        self.assertEqual(self.nodes['bob'].balance('doris'), 2)
        self.assertEqual(self.nodes['doris'].balance('alice'), 2)

    def test_either_helper_opt_out_blocks_assistance(self):
        for owner, peer in [('bob', 'doris'), ('doris', 'bob')]:
            with self.subTest(owner=owner):
                self.preferences(owner, peer, auto_adjust=False)
                self.drain()
                ident = self.nodes['alice'].discover(2, mode='comfort')['id']
                self.drain()
                self.assertEqual(self.nodes['alice'].proposal(ident)['status'], 'aborted')
                self.assert_unspent()
                self.preferences(owner, peer, auto_adjust=True)
                self.drain()

    def test_empty_shared_zone_and_no_strict_origin_improvement_are_not_admitted(self):
        self.preferences('alice', 'bob', comfort_min=-2, comfort_max=2)
        self.preferences('bob', 'alice', comfort_min=-2, comfort_max=2)
        self.drain()
        with self.assertRaises(ValueError):
            self.nodes['alice'].discover(1, mode='comfort')
        self.assert_unspent()
        self.preferences('alice', 'bob', comfort_min=1, comfort_max=2)
        self.preferences('bob', 'alice', comfort_min=1, comfort_max=2)
        self.drain()
        with self.assertRaises(ValueError):
            self.nodes['alice'].discover(1, mode='comfort')
        self.assert_unspent()

    def test_stale_probe_revision_rejects_and_quiesces(self):
        ident = self.nodes['alice'].discover(2, mode='comfort')['id']
        self.preferences('bob', 'alice', comfort_min=0, comfort_max=0, credit_limit=0)
        self.drain()
        self.assertEqual(self.nodes['alice'].proposal(ident)['status'], 'aborted')
        self.assert_unspent()

    def test_stale_prepare_revision_unwinds_reserved_origin_and_deferred_update(self):
        ident = self.nodes['alice'].discover(2, mode='comfort')['id']
        while not self.nodes['alice'].proposal(ident)['prepared']:
            self.deliver(self.queue()[0])
        self.preferences('bob', 'alice', comfort_min=0, comfort_max=0, credit_limit=0)
        self.drain()
        self.assertEqual(self.nodes['alice'].proposal(ident)['status'], 'aborted')
        self.assert_unspent()
        contact = next(c for c in self.nodes['alice'].contacts() if c['peer'] == 'bob')
        self.assertEqual(contact['peer_preferences']['credit_limit'], 0)

    def test_reservations_freeze_both_local_preference_snapshots(self):
        ident = self.prepare()
        for peer in ('bob', 'doris'):
            with self.assertRaises(ValueError):
                self.preferences('alice', peer, auto_adjust=False)
        for node in self.nodes.values():
            data = json.loads(node.proposal(ident)['data'])
            self.assertEqual(sum(c['after']-c['before'] for c in data['changes']), 0)
            for change in data['changes']:
                self.assertEqual(change['own_revision'], change['own_preferences']['revision'])
                self.assertEqual(change['peer_revision'], change['peer_preferences']['revision'])

    def test_hash_binds_comfort_policy_and_direction_separately_from_cancellation(self):
        ident, secret = '01'*32, '02'*32
        plus = hash_comfort_condition(ident, 2, secret, 1)
        self.assertNotEqual(plus, hash_comfort_condition(ident, 2, secret, -1))
        self.assertNotEqual(plus, hash_condition(ident, 2, secret))
        self.assertNotEqual(plus, hash_comfort_condition(ident, 1, secret, 1))
        with self.assertRaises(ValueError):
            hash_comfort_condition(ident, 2, secret, True)

    def test_wrong_direction_or_cancellation_preimage_cannot_spend(self):
        ident = self.prepare()
        self.approve('bob', ident)
        origin = self.nodes['alice']
        data = json.loads(origin.proposal(ident)['data'])
        secret = origin.db.execute('SELECT preimage FROM private_secrets WHERE id=?', (ident,)).fetchone()[0]
        message = origin.envelope(data, 'fulfill', preimage=secret, message_id=uuid.uuid4().hex)
        for changes in ({'direction': -data['direction']}, {'condition': hash_condition(ident,2,secret)}, {'policy': 'other'}):
            with self.assertRaises(ValueError):
                self.nodes['bob'].receive('alice', dict(message, **changes))
        self.assertEqual(self.balances(self.nodes['bob']), self.initial['bob'])

    def test_release_restart_is_irrevocable_and_exactly_once(self):
        ident = self.prepare()
        for name in self.nodes:
            self.approve(name, ident)
        origin = self.nodes['alice']
        while origin.proposal(ident)['status'] != 'committed':
            self.deliver(self.queue()[0])
        data = json.loads(origin.proposal(ident)['data'])
        with self.assertRaises(ValueError):
            origin.receive('doris', origin.envelope(data, 'abort', message_id=uuid.uuid4().hex))
        replacement = Node(self.configs['alice'], str(Path(self.tmp.name) / 'alice.sqlite'))
        self.addCleanup(replacement.db.close)
        self.nodes['alice'] = replacement
        self.drain()
        for node in self.nodes.values():
            self.assertEqual(node.proposal(ident)['status'], 'committed')
            self.assertEqual(len(node.receipts()), 1)
            self.assertEqual(node.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 0)

    def test_receipt_rejects_reversed_signed_helpers_and_invalid_revisions(self):
        ident = self.prepare()
        for name in self.nodes:
            self.approve(name, ident)
        self.drain()
        receipt = self.nodes['doris'].receipts()[0]
        self.assertTrue(verify(receipt)['valid'])
        reversed_receipt = copy.deepcopy(receipt)
        for change in reversed_receipt['changes']:
            change['after'] = -change['after']
        reversed_receipt['incoming_quote'] = copy.deepcopy(reversed_receipt['changes'][0])
        reversed_receipt['outgoing_quote'] = copy.deepcopy(reversed_receipt['changes'][1])
        with self.assertRaises(ValueError):
            verify(reversed_receipt)
        for invalid in (None, True, 0, -1):
            malformed = copy.deepcopy(receipt)
            for change in malformed['changes']:
                change['own_revision'] = invalid
                change['own_preferences']['revision'] = invalid
            malformed['incoming_quote'] = copy.deepcopy(malformed['changes'][0])
            malformed['outgoing_quote'] = copy.deepcopy(malformed['changes'][1])
            with self.subTest(revision=invalid):
                with self.assertRaises(ValueError):
                    verify(malformed)

    def test_negative_direction_clears_positive_origin_edge(self):
        # Alternate mutually consistent fixture; no running-node transfer API is implied.
        for name, node in self.nodes.items():
            with node.db:
                node.db.execute('UPDATE balances SET balance=-balance')
        ident = self.prepare()
        self.assertEqual(json.loads(self.nodes['alice'].proposal(ident)['data'])['direction'], -1)
        for name in self.nodes:
            self.approve(name, ident)
        self.drain()
        self.assertEqual(self.nodes['alice'].balance('bob'), 0)
        self.assertEqual(self.nodes['bob'].balance('doris'), -2)
        self.assertEqual(self.nodes['doris'].balance('alice'), -2)
        for node in self.nodes.values():
            self.assertTrue(verify(node.receipts()[0])['valid'])

    def test_decline_before_disclosure_restores_capacity_without_balance_changes(self):
        ident = self.prepare()
        self.approve('alice', ident)
        bob = self.nodes['bob']
        bob.decline(ident, json.loads(bob.proposal(ident)['data'])['digest'])
        self.drain()
        self.assert_unspent()
        for node in self.nodes.values():
            self.assertEqual(node.proposal(ident)['status'], 'aborted')
            self.assertNotIn('preimage', json.dumps(node.receipts()))


if __name__ == '__main__':
    unittest.main()
