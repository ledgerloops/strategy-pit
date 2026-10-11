"""Independent state-machine admission and recovery regression checks."""
import copy
import json
import random
import tempfile
import unittest
from pathlib import Path
from node import Node, MAX_AMOUNT, MAX_PATH
from run_demo import create_configs


class AdversarialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.configs = create_configs(self.tmp.name, {'alice': 19001, 'bob': 19002, 'doris': 19003})
        self.nodes = {name: Node(config, str(Path(self.tmp.name) / (name + '.sqlite')))
                      for name, config in self.configs.items()}
        for node in self.nodes.values():
            self.addCleanup(node.db.close)

    def message(self, kind='prepare', **changes):
        return dict(dict(kind=kind, id='review-proposal', message_id='review-message',
                         path=['alice', 'bob', 'doris'], amount=3), **changes)

    def counts(self, node):
        return tuple(node.db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                     for table in ('proposals', 'reservations', 'inbox', 'outbox', 'receipts'))

    def test_invalid_amounts_and_paths_are_atomic(self):
        node = self.nodes['bob']
        for amount in (True, False, 0, -1, 1.5, '3', MAX_AMOUNT + 1):
            with self.subTest(amount=amount):
                with self.assertRaises((ValueError, TypeError)):
                    node.receive('alice', self.message(amount=amount))
                self.assertEqual(self.counts(node), (0, 0, 0, 0, 0))
        for path in ([], ['alice', 'bob', 'bob'], ['alice', 'bob'], ['alice', 'doris', 'bob'], list(map(str, range(MAX_PATH+1)))):
            with self.subTest(path=path):
                with self.assertRaises((ValueError, TypeError)):
                    node.receive('alice', self.message(path=path))
                self.assertEqual(self.counts(node), (0, 0, 0, 0, 0))

    def test_wrong_sender_rejected_before_any_state(self):
        node = self.nodes['bob']
        for sender in ('outsider', 'doris'):
            with self.assertRaises(ValueError):
                node.receive(sender, self.message())
            self.assertEqual(self.counts(node), (0, 0, 0, 0, 0))

    def test_live_mode_refused(self):
        config = copy.deepcopy(self.configs['alice'])
        config['mode'] = 'live'
        with self.assertRaises(ValueError):
            Node(config, ':memory:')

    def test_changed_proposal_payload_cannot_commit(self):
        node = self.nodes['bob']
        node.receive('alice', self.message())
        for change in ({'amount': 2}, {'path': ['alice', 'doris', 'bob']}):
            with self.assertRaises(ValueError):
                node.receive('alice', self.message('commit', message_id='different', **change))
        self.assertEqual(node.balance('alice'), 7)
        self.assertEqual(node.balance('doris'), -3)
        self.assertEqual(node.proposal('review-proposal')['status'], 'pending')

    def test_duplicate_delivery_and_semantic_prepare_are_idempotent(self):
        node = self.nodes['bob']
        node.receive('alice', self.message())
        before = self.counts(node)
        node.receive('alice', self.message())
        self.assertEqual(self.counts(node), before)
        node.receive('alice', self.message(message_id='new-delivery'))
        self.assertEqual(node.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 2)
        self.assertEqual(node.db.execute('SELECT count(*) FROM proposals').fetchone()[0], 1)

    def test_unapproved_commit_does_not_release_reservations(self):
        node = self.nodes['bob']
        node.receive('alice', self.message())
        with self.assertRaises(ValueError):
            node.receive('alice', self.message('commit', message_id='decision'))
        self.assertEqual(node.balance('alice'), 7)
        self.assertEqual(node.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 2)
        self.assertEqual(node.proposal('review-proposal')['status'], 'pending')

    def test_unknown_abort_prevents_late_prepare(self):
        node = self.nodes['bob']
        node.receive('alice', self.message('abort'))
        node.receive('alice', self.message(message_id='late-prepare'))
        self.assertEqual(node.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 0)
        self.assertEqual(node.proposal('review-proposal')['status'], 'aborted')

    def approve_bob(self):
        node = self.nodes['bob']
        node.receive('alice', self.message())
        digest = json.loads(node.proposal('review-proposal')['data'])['digest']
        node.approve('review-proposal', digest)
        return node, digest

    def test_wrong_approval_digest_rejected(self):
        node = self.nodes['bob']
        node.receive('alice', self.message())
        for digest in (None, 'wrong'):
            with self.assertRaises(ValueError):
                node.approve('review-proposal', digest)
        self.assertFalse(node.proposal('review-proposal')['approved'])

    def test_partial_local_apply_rolls_back_if_second_edge_invalid(self):
        node, _ = self.approve_bob()
        with node.db:
            node.db.execute("UPDATE balances SET balance=-2 WHERE peer='doris'")
        with self.assertRaises(ValueError):
            node.receive('alice', self.message('commit', message_id='decision'))
        self.assertEqual(node.balance('alice'), 7)
        self.assertEqual(node.proposal('review-proposal')['status'], 'pending')
        self.assertEqual(node.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 2)
        self.assertEqual(node.receipts(), [])

    def test_local_commit_replay_and_conflicting_abort(self):
        node, _ = self.approve_bob()
        node.receive('alice', self.message('commit', message_id='decision'))
        node.receive('alice', self.message('commit', message_id='decision-replay'))
        self.assertEqual((node.balance('alice'), node.balance('doris')), (4, 0))
        self.assertFalse(node.receipts()[0]['cycle_complete'])
        with self.assertRaises(ValueError):
            node.receive('alice', self.message('abort', message_id='conflict'))
        self.assertEqual((node.balance('alice'), node.balance('doris')), (4, 0))
        self.assertEqual(len(node.receipts()), 1)

    def test_reordered_duplicate_delivery_converges(self):
        rng = random.Random(7421)
        ident = self.nodes['alice'].discover(3)['id']
        for step in range(150):
            # Manual consent is independent of transport and may precede prepare ACK.
            for node in rng.sample(list(self.nodes.values()), 3):
                rows = list(node.db.execute("SELECT * FROM proposals WHERE status='pending' AND approved=0"))
                for row in rows:
                    node.approve(row['id'], json.loads(row['data'])['digest'])
            queued = [(name, dict(row)) for name, node in self.nodes.items()
                      for row in node.db.execute('SELECT * FROM outbox')]
            if not queued:
                break
            sender, row = rng.choice(queued)
            receiver = self.nodes[row['peer']]
            message = json.loads(row['data'])
            receiver.receive(sender, message)
            # Simulate delivered message with lost ACK: resend exact durable payload.
            if rng.random() < .6:
                receiver.receive(sender, message)
            with self.nodes[sender].db:
                self.nodes[sender].db.execute('DELETE FROM outbox WHERE id=?', (row['id'],))
        else:
            self.fail('Bounded ring failed to drain')
        expected = {'alice': {'bob': -4, 'doris': 2},
                    'bob': {'alice': 4, 'doris': 0},
                    'doris': {'alice': -2, 'bob': 0}}
        for name, node in self.nodes.items():
            self.assertEqual({r['peer']: r['balance'] for r in node.db.execute('SELECT * FROM balances')}, expected[name])
            self.assertEqual(node.proposal(ident)['status'], 'committed')
            self.assertEqual(node.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 0)
            self.assertEqual(len(node.receipts()), 1)
            self.assertTrue(node.receipts()[0]['cycle_complete'])

    def test_decline_cannot_be_followed_by_approval(self):
        node = self.nodes['bob']
        node.receive('alice', self.message())
        digest = json.loads(node.proposal('review-proposal')['data'])['digest']
        node.decline('review-proposal', digest)
        node.decline('review-proposal', digest)
        with self.assertRaises(ValueError):
            node.approve('review-proposal', digest)
        self.assertEqual(node.proposal('review-proposal')['status'], 'declining')
        self.assertEqual(node.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 2)
        node.receive('alice', self.message('abort', message_id='decision'))
        self.assertEqual(node.proposal('review-proposal')['status'], 'aborted')
        self.assertEqual(node.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 0)

    def test_approval_response_loss_retry_after_commit(self):
        node, digest = self.approve_bob()
        node.receive('alice', self.message('commit', message_id='decision'))
        self.assertTrue(node.approve('review-proposal', digest)['ok'])
        self.assertEqual((node.balance('alice'), node.balance('doris')), (4, 0))
        with self.assertRaises(ValueError):
            node.decline('review-proposal', digest)

    def test_conflicting_completion_cannot_publish_receipt(self):
        node, _ = self.approve_bob()
        node.receive('alice', self.message('commit', message_id='decision'))
        with self.assertRaises(ValueError):
            node.receive('alice', self.message('complete', message_id='bad-complete', decision='abort'))
        self.assertFalse(node.receipts()[0]['cycle_complete'])
        node.receive('alice', self.message('complete', message_id='good-complete', decision='commit'))
        self.assertTrue(node.receipts()[0]['cycle_complete'])

    def test_prepared_restart_keeps_capacity_locked(self):
        node = self.nodes['bob']
        node.receive('alice', self.message())
        restored = Node(self.configs['bob'], str(Path(self.tmp.name) / 'bob.sqlite'))
        self.addCleanup(restored.db.close)
        self.assertEqual(restored.proposal('review-proposal')['status'], 'pending')
        self.assertEqual(restored.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 2)
        self.assertEqual(restored.balance('alice'), 7)
        self.assertEqual(restored.receipts(), [])


if __name__ == '__main__':
    unittest.main()
