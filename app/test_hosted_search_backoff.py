"""Idle wakeups cannot create timers/journals; changed local terms wake search.

Isolated local node databases and real serialized neighbour messages. Fixtures
initialize balances directly, then automatic ticks own all search and approval.
"""
from contextlib import contextmanager
import json
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from hosted_runtime import HostedRuntime, SEARCH_RETRY_MAX
from test_hosted_named_invites import LocalStores


class Reply:
    status = 200
    def __enter__(self):
        return self
    def __exit__(self, *_):
        pass
    def read(self, *_):
        return b'{}'


class HostedSearchBackoffTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.stores = LocalStores(directory.name)
        self.runtime = HostedRuntime(self.stores, 'https://example.test')
        self.ids = ['n_'+char*32 for char in 'abc']
        for index, ident in enumerate(self.ids):
            self.runtime.provision(dict(node_id=ident, name='Backoff TEST '+str(index)))

    def connect(self, first, second):
        self.runtime.accept_invite(second, self.runtime.invite(first)['invite_token'])

    def balance(self, first, second, amount):
        for own, peer, value in ((first, second, amount), (second, first, -amount)):
            with self.runtime.node(own) as node:
                node.db.execute('UPDATE balances SET balance=? WHERE peer=?', (value, peer))

    def deliver(self, request, **_):
        destination = urlsplit(request.full_url).path.split('/')[2]
        self.runtime.receive(destination, request.get_header('X-peer-id'),
                             request.get_header('Authorization'), json.loads(request.data))
        return Reply()

    def tick(self, at, nodes=None):
        with patch('hosted_runtime.time.time', return_value=at), \
                patch('hosted_runtime.secrets.randbelow', return_value=0), \
                patch('hosted_runtime.urlopen', self.deliver):
            for ident in nodes or self.ids:
                self.runtime.tick(ident)

    def drain(self, at):
        for _ in range(100):
            self.tick(at)
            if not any(self.runtime.state(ident)['outbox_pending'] for ident in self.ids):
                return
        self.fail('Neighbour envelopes did not quiesce')

    def record(self, ident):
        with self.runtime.node(ident) as node:
            timer = node.db.execute("SELECT v FROM meta WHERE k='hosted_next_search'").fetchone()
            backoff = node.db.execute("SELECT v FROM meta WHERE k='hosted_search_backoff'").fetchone()
            return dict(timer=float(timer[0]) if timer else None,
                        backoff=json.loads(backoff[0]) if backoff else None,
                        searches=[dict(row) for row in node.db.execute('SELECT * FROM searches')],
                        receipts=[dict(row) for row in node.db.execute('SELECT * FROM receipts')])

    def dead_end(self):
        first, middle, last = self.ids
        self.connect(first, middle)
        self.connect(middle, last)
        self.drain(1000)
        self.balance(first, middle, -1)
        self.balance(middle, last, -1)
        return first, middle, last

    def test_zero_degree_one_and_one_sided_nodes_never_start_or_write_idle_timers(self):
        first, middle, last = self.ids
        self.connect(first, middle)
        self.connect(first, last)
        self.drain(1000)
        for amounts in ((0, 0), (-1, -1), (1, 1)):
            with self.subTest(amounts=amounts):
                self.balance(first, middle, amounts[0])
                self.balance(first, last, amounts[1])
                before = [self.record(ident) for ident in self.ids]
                deltas = []
                original = self.runtime.node

                @contextmanager
                def tracked(ident):
                    with original(ident) as node:
                        prior = node.db.total_changes
                        yield node
                        deltas.append(node.db.total_changes-prior)

                with patch.object(self.runtime, 'node', tracked):
                    for at in (1001, 1002, 2000, 100000):
                        self.tick(at)
                self.assertEqual(deltas, [0]*len(deltas), 'Idle ticks must perform no SQLite data writes')
                self.assertEqual([self.record(ident) for ident in self.ids], before)
                self.assertTrue(all(not item['searches'] and item['timer'] is None for item in before))

    def test_failed_unchanged_searches_back_off_and_survive_restart(self):
        _, middle, _ = self.dead_end()
        now = 1001
        delays = []
        for attempt in range(1, 11):
            self.drain(now)
            record = self.record(middle)
            delays.append(record['timer']-now)
            self.assertEqual(len(record['searches']), attempt)
            self.assertTrue(all(json.loads(row['data'])['status'] == 'aborted' for row in record['receipts']))
            self.assertEqual(record['backoff']['attempts'], min(attempt, 8))
            self.runtime = HostedRuntime(self.stores, 'https://example.test')
            for at in (now+.1, record['timer']-.1):
                self.drain(at)
                self.assertEqual(self.record(middle), record, 'Waiting does not rewrite scheduling metadata or create journals')
            now = record['timer']
        self.assertEqual(delays, [4, 8, 16, 32, 64, 128, 256, 300, 300, 300])
        self.assertEqual(delays[-1], SEARCH_RETRY_MAX)

    def test_local_balance_or_exchanged_preferences_reset_backoff_immediately(self):
        first, middle, last = self.dead_end()
        self.drain(1001)
        self.drain(1005)
        self.assertEqual(self.record(middle)['backoff']['attempts'], 2)
        self.balance(first, middle, -2)
        self.drain(1006)
        self.assertEqual(self.record(middle)['backoff']['attempts'], 1)
        self.drain(1010)
        self.assertEqual(self.record(middle)['backoff']['attempts'], 2)
        # A neighbour's accepted preference update is fresh local eligibility
        # evidence even though no balance changed.
        with self.runtime.node(last) as node:
            own = node.contacts()[0]['own']
            node.set_preferences(middle, dict(own, expected_revision=own['revision'], credit_limit=11))
        self.tick(1011, nodes=[last])
        self.drain(1011)
        self.assertEqual(self.record(middle)['backoff']['attempts'], 1)
        self.assertEqual(len(self.record(middle)['searches']), 5)
        self.drain(1015)
        self.assertEqual(self.record(middle)['backoff']['attempts'], 2)
        with self.runtime.node(middle) as node:
            own = next(contact['own'] for contact in node.contacts() if contact['peer'] == first)
            node.set_preferences(first, dict(own, expected_revision=own['revision'], credit_limit=11))
        self.drain(1016)
        self.assertEqual(self.record(middle)['backoff']['attempts'], 1)
        self.assertEqual(len(self.record(middle)['searches']), 7)

    def test_two_unresolved_operations_do_not_rewrite_an_expired_timer(self):
        _, middle, _ = self.dead_end()
        self.drain(1001)
        with self.runtime.node(middle) as node:
            for ident in ('retained-first-search', 'retained-second-search'):
                node.db.execute("INSERT INTO proposals(id,data,status) VALUES(?,'{}','searching')", (ident,))
        before = self.record(middle)
        self.drain(2000)
        self.assertEqual(self.record(middle), before)

    def test_one_sided_zero_edge_helpers_still_forward_approve_and_clear_automatically(self):
        first, middle, last = self.ids
        for own, peer in ((first, middle), (middle, last), (first, last)):
            self.connect(own, peer)
        self.drain(1000)
        self.balance(first, middle, -1)
        self.balance(middle, last, -1)
        before = {ident: sum(row['balance'] for row in self.runtime.state(ident)['balances']) for ident in self.ids}
        self.drain(1001)
        states = [self.runtime.state(ident) for ident in self.ids]
        self.assertEqual(sum(abs(row['balance']) for state in states for row in state['balances'])//2, 1)
        self.assertEqual({state['node']: sum(row['balance'] for row in state['balances']) for state in states}, before)
        self.assertTrue(all(any(row['status'] == 'committed' for row in state['receipts']) for state in states))
        self.assertEqual(len(self.record(first)['searches']), 0)
        self.assertEqual(len(self.record(last)['searches']), 0)
        self.assertEqual(len(self.record(middle)['searches']), 1)
        self.assertTrue(all(not state['outbox_pending'] for state in states))


if __name__ == '__main__':
    unittest.main()
