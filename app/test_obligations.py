"""Obligation consent, concurrency, replay and crash-recovery checks."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

from node import MAX_AMOUNT
from private_node import Node
from run_demo import create_configs
from obligations import digest_terms


class ObligationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.configs = create_configs(self.tmp.name, {'alice': 19101, 'bob': 19102, 'doris': 19103})
        self.nodes = {}
        for name, config in self.configs.items():
            for peer in config['peers'].values():
                peer['balance'] = 0
            self.nodes[name] = self.open(name)
        self.drain()
        for name, node in self.nodes.items():
            for peer in node.peers:
                self.preferences(name, peer)
        self.drain()

    def open(self, name):
        node = Node(self.configs[name], str(Path(self.tmp.name)/(name + '.sqlite')))
        self.addCleanup(node.db.close)
        return node

    def preferences(self, name, peer, limit=10):
        node = self.nodes[name]
        own = next(c['own'] for c in node.contacts() if c['peer'] == peer)
        node.set_preferences(peer, dict(credit_limit=limit, comfort_min=0, comfort_max=0,
                                        auto_adjust=True, expected_revision=own['revision']))

    def queue(self):
        return [(name, dict(row)) for name, node in self.nodes.items()
                for row in node.db.execute('SELECT * FROM outbox')]

    def deliver(self, entry, ack=True):
        sender, row = entry
        data = json.loads(row['data'])
        self.nodes[row['peer']].receive(sender, data)
        if ack:
            with self.nodes[sender].db:
                self.nodes[sender].db.execute('DELETE FROM outbox WHERE id=?', (row['id'],))
        return data

    def drain(self):
        for _ in range(100):
            entries = self.queue()
            if not entries:
                return
            progressed = False
            for entry in entries:
                try:
                    self.deliver(entry)
                    progressed = True
                except ValueError as error:
                    if 'deferred until reservation finishes' not in str(error):
                        raise
            if not progressed:
                self.fail('Only blocked messages remain')
        self.fail('Outbox did not quiesce')

    def propose(self, name='alice', peer='bob', amount=2, direction='i_owe', ident=None, description='Lunch'):
        body = dict(id=ident or uuid.uuid4().hex*2, peer=peer, amount=amount,
                    direction=direction, description=description)
        return self.nodes[name].propose_obligation(body)['obligation']

    def view(self, name, ident):
        return self.nodes[name].obligation_view(self.nodes[name].obligation_row(ident))

    def approve(self, name, ident):
        return self.nodes[name].approve_obligation(ident, self.view(name, ident)['digest'])

    def assert_no_reservations(self):
        for node in self.nodes.values():
            self.assertEqual(node.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 0)

    def test_exact_consent_mirrored_direction_and_persistent_history(self):
        proposal = self.propose(description='<script>untrusted</script>')
        ident = proposal['id']
        self.assertEqual((proposal['status'], proposal['approved']), ('proposed', True))
        self.assertEqual(self.nodes['alice'].balance('bob'), 0)
        self.drain()
        receiver = self.view('bob', ident)
        self.assertEqual((receiver['before'], receiver['after'], receiver['direction']), (0, 2, 'peer_owes'))
        self.assertEqual(receiver['digest'], proposal['digest'])
        with self.assertRaises(ValueError):
            self.nodes['bob'].approve_obligation(ident, '00'*32)
        self.assertEqual(self.nodes['bob'].balance('alice'), 0)
        self.approve('bob', ident)
        self.assertEqual(self.nodes['bob'].balance('alice'), 0)
        with self.assertRaises(ValueError):
            self.nodes['bob'].decline_obligation(ident, receiver['digest'])
        self.drain()
        self.assertEqual(self.nodes['alice'].balance('bob'), -2)
        self.assertEqual(self.nodes['bob'].balance('alice'), 2)
        self.assertEqual(self.nodes['doris'].obligations(), [])
        self.assert_no_reservations()
        self.nodes['bob'] = self.open('bob')
        self.assertEqual(self.view('bob', ident)['status'], 'committed')
        self.assertIsNotNone(self.view('bob', ident)['applied_at'])
        self.assertTrue(self.nodes['bob'].state()['obligation_capable'])

    def test_decline_changes_no_balance_and_retains_history(self):
        proposal = self.propose(); self.drain()
        self.nodes['bob'].decline_obligation(proposal['id'], proposal['digest'])
        self.drain()
        for name, peer in [('alice', 'bob'), ('bob', 'alice')]:
            self.assertEqual(self.nodes[name].balance(peer), 0)
            self.assertEqual(self.view(name, proposal['id'])['status'], 'aborted')
        self.assert_no_reservations()

    def test_limits_types_and_dedup_client_id(self):
        for amount in (True, 0, -1, 1.5, MAX_AMOUNT+1, 11):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                self.propose(amount=amount)
        for kwargs in [dict(direction='invalid'), dict(peer='stranger'), dict(description='x'*201), dict(ident='bad')]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.propose(**kwargs)
        proposal = self.propose(direction='peer_owes')
        self.assertEqual(proposal, self.propose(direction='peer_owes', ident=proposal['id']))
        with self.assertRaises(ValueError):
            self.propose(ident=proposal['id'], direction='peer_owes', amount=1)
        self.drain(); self.approve('bob', proposal['id']); self.drain()
        self.assertEqual(self.nodes['alice'].balance('bob'), 2)
        self.assertEqual(self.propose(direction='peer_owes', ident=proposal['id'])['status'], 'committed')

    def test_stale_preferences_offer_aborts_and_acks_without_endless_retry(self):
        proposal = self.propose()
        self.preferences('bob', 'alice', limit=1)
        self.drain()
        self.assertEqual(self.view('alice', proposal['id'])['status'], 'aborted')
        self.assertIn('stale', self.view('bob', proposal['id'])['reason'])
        self.assert_no_reservations()
        self.assertEqual(self.nodes['alice'].balance('bob'), 0)
        self.assertEqual(self.nodes['alice'].contacts()[0]['peer_preferences']['credit_limit'], 1)

    def test_simultaneous_proposals_abort_without_deadlock(self):
        first = self.propose()
        second = self.propose('bob', 'alice')
        self.drain()
        for ident in (first['id'], second['id']):
            for name in ('alice', 'bob'):
                self.assertEqual(self.view(name, ident)['status'], 'aborted')
        self.assert_no_reservations()

    def test_reservations_freeze_preferences_and_block_clearing(self):
        proposal = self.propose(); self.drain()
        for name, peer in [('alice', 'bob'), ('bob', 'alice')]:
            with self.assertRaises(ValueError):
                self.preferences(name, peer)
            node = self.nodes[name]
            self.assertIsNone(node.candidate(1))
            with self.assertRaises(ValueError):
                node.discover(1)
        self.nodes['bob'].decline_obligation(proposal['id'], proposal['digest']); self.drain()
        # The converse also applies: an existing clearing reservation rejects submission.
        with self.nodes['alice'].db:
            self.nodes['alice'].db.execute('INSERT INTO reservations VALUES(?,?)', ('bob', 'clearing-id'))
        with self.assertRaises(ValueError):
            self.propose()

    def test_wrong_sender_digest_direction_and_early_commit_rejected(self):
        proposal = self.propose()
        entry = self.queue()[0]
        wire = json.loads(entry[1]['data'])
        with self.assertRaises(ValueError):
            self.nodes['bob'].receive('doris', wire)
        altered = copy.deepcopy(wire)
        altered['terms']['description'] = 'Different'
        with self.assertRaises(ValueError):
            self.nodes['bob'].receive('alice', altered)
        self.deliver(entry)
        commit = dict(kind='obligation_commit', protocol=wire['protocol'], id=wire['id'],
                      digest=wire['digest'], message_id=uuid.uuid4().hex)
        with self.assertRaises(ValueError):
            self.nodes['bob'].receive('alice', commit)
        for sender in ('doris', 'stranger'):
            with self.assertRaises(ValueError):
                self.nodes['bob'].receive(sender, wire)
        # Immutable validation precedes duplicate transport ID handling.
        altered = copy.deepcopy(wire)
        altered['terms']['amount'] = 1
        altered['terms']['after'] = -1
        altered['digest'] = digest_terms(altered['terms'])
        with self.assertRaises(ValueError):
            self.nodes['bob'].receive('alice', altered)
        self.assertEqual(self.nodes['bob'].balance('alice'), 0)

    def test_restart_each_irreversible_boundary_and_lost_ack_apply_once(self):
        proposal = self.propose(); self.drain()
        ident = proposal['id']
        self.approve('bob', ident)
        self.nodes['bob'] = self.open('bob')
        acceptance = self.queue()[0]
        self.deliver(acceptance, ack=False)
        self.assertEqual(self.view('alice', ident)['status'], 'committing')
        self.assertEqual(self.nodes['alice'].balance('bob'), -2)
        self.assertIsNotNone(self.nodes['alice'].contacts()[0]['reserved_by'])
        self.nodes['alice'] = self.open('alice')
        self.deliver(acceptance)  # lost ACK replay
        commit = self.queue()[0]
        self.deliver(commit, ack=False)
        self.assertEqual(self.view('bob', ident)['status'], 'committed')
        self.nodes['bob'] = self.open('bob')
        self.deliver(commit)
        self.drain()
        self.assertEqual(self.nodes['alice'].balance('bob'), -2)
        self.assertEqual(self.nodes['bob'].balance('alice'), 2)
        self.assert_no_reservations()
        self.assertEqual(self.view('alice', ident)['status'], 'committed')

    def test_late_terminal_replays_do_not_release_a_new_operation(self):
        proposal = self.propose(); self.drain()
        ident = proposal['id']
        self.approve('bob', ident)
        acceptance = self.deliver(self.queue()[0])
        commit = self.deliver(self.queue()[0])
        settled = self.deliver(self.queue()[0])
        newer = self.propose(amount=1); self.drain()
        for sender, receiver, wire in [('bob', 'alice', acceptance), ('alice', 'bob', commit),
                                       ('bob', 'alice', settled)]:
            self.nodes[receiver].receive(sender, dict(wire, message_id=uuid.uuid4().hex))
        for owner, peer in [('alice', 'bob'), ('bob', 'alice')]:
            self.assertEqual(self.nodes[owner].balance(peer), -2 if owner == 'alice' else 2)
            reserved = next(c['reserved_by'] for c in self.nodes[owner].contacts() if c['peer'] == peer)
            self.assertEqual(reserved, 'obligation:' + newer['id'])
        self.nodes['bob'].decline_obligation(newer['id'], newer['digest']); self.drain()
        self.assert_no_reservations()

    def test_pending_obligation_remains_visible_after_many_newer_terminal_rows(self):
        proposal = self.propose(); self.drain()
        node = self.nodes['bob']
        row = node.obligation_row(proposal['id'])
        with node.db:
            for index in range(105):
                ident = format(index, '064x')
                terms = json.loads(row['data'])
                terms['id'] = ident
                node.db.execute('INSERT INTO obligations(id,peer,data,digest,status,origin,approved) VALUES(?,?,?,?,?,0,0)',
                                (ident, 'alice', json.dumps(terms), digest_terms(terms), 'aborted'))
        visible = node.state()['obligations']
        self.assertEqual(len(visible), 101)
        self.assertIn(proposal['id'], [r['id'] for r in visible])
        self.approve('bob', proposal['id']); self.drain()
        self.assert_no_reservations()

    def test_outbox_failure_rolls_back_submission_and_durable_commit(self):
        node = self.nodes['alice']
        with patch.object(node, 'send_obligation', side_effect=ValueError('Injected outbox failure')):
            with self.assertRaises(ValueError):
                self.propose()
        self.assertEqual(node.obligations(), [])
        self.assert_no_reservations()
        proposal = self.propose(); self.drain(); self.approve('bob', proposal['id'])
        entry = self.queue()[0]
        with patch.object(node, 'send_obligation', side_effect=ValueError('Injected outbox failure')):
            with self.assertRaises(ValueError):
                self.deliver(entry)
        self.assertEqual(node.balance('bob'), 0)
        self.assertEqual(self.view('alice', proposal['id'])['status'], 'proposed')
        self.assertIsNone(self.view('alice', proposal['id'])['applied_at'])
        self.drain()
        self.assertEqual(node.balance('bob'), -2)
        self.assert_no_reservations()

    def test_approve_decline_race_has_one_durable_outcome(self):
        proposal = self.propose(); self.drain()
        node = self.nodes['bob']
        gate = threading.Barrier(2)
        outcomes = []
        def decide(action):
            gate.wait()
            try:
                action(proposal['id'], proposal['digest'])
                outcomes.append('ok')
            except ValueError:
                outcomes.append('refused')
        threads = [threading.Thread(target=decide, args=(action,))
                   for action in (node.approve_obligation, node.decline_obligation)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        self.assertCountEqual(outcomes, ['ok', 'refused'])
        self.drain()
        left, right = self.view('alice', proposal['id']), self.view('bob', proposal['id'])
        self.assertEqual(left['status'], right['status'])
        self.assertIn(left['status'], ('aborted', 'committed'))
        self.assertEqual(node.balance('alice'), 2 if left['status'] == 'committed' else 0)
        self.assert_no_reservations()

    def test_entered_obligations_can_form_and_clear_a_cycle(self):
        for owner, peer in [('alice', 'bob'), ('bob', 'doris'), ('doris', 'alice')]:
            proposal = self.propose(owner, peer, 2)
            self.drain(); self.approve(peer, proposal['id']); self.drain()
        initial = {name: sum(r['balance'] for r in node.state()['balances']) for name, node in self.nodes.items()}
        ident = self.nodes['alice'].discover(2)['id']; self.drain()
        for node in self.nodes.values():
            data = json.loads(node.proposal(ident)['data'])
            node.approve(ident, data['digest'])
        self.drain()
        for name, node in self.nodes.items():
            self.assertTrue(all(r['balance'] == 0 for r in node.state()['balances']))
            self.assertEqual(sum(r['balance'] for r in node.state()['balances']), initial[name])
            self.assertEqual(len(node.obligations()), 2)
            self.assertEqual(len(node.receipts()), 1)
        self.assert_no_reservations()


if __name__ == '__main__':
    unittest.main()
