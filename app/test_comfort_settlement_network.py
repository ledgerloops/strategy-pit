"""Comfort-assisted settlement over real HTTP processes and durable SQLite stores.

The test harness constructs and audits graphs; participants receive only their
own neighbour configurations. Faults are deterministic, reproducible barriers.
"""
import time
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import unittest
from urllib.parse import quote

from test_private_network import PrivateNetwork


class ComfortSettlementNetworkTests(unittest.TestCase):
    @staticmethod
    def contact(net, node, peer):
        return next(c for c in net.state(node)['contacts'] if c['peer'] == peer)

    def save(self, net, node, peer, width=4, auto=True):
        revision = self.contact(net, node, peer)['own']['revision']
        status, value = net.request(node, '/api/contacts/' + quote(peer, safe='') + '/preferences',
                                   dict(expected_revision=revision, credit_limit=10,
                                        comfort_min=-width, comfort_max=width, auto_adjust=auto))
        self.assertEqual(status, 200, value)
        return value

    def make_network(self, size=3, reverse=False):
        names = tuple(f'participant_{i:03d}' for i in range(size))
        graph = {node: {names[i-1]: 0, names[(i+1) % size]: 0} for i, node in enumerate(names)}
        a, b = names[:2]
        graph[a][b], graph[b][a] = (2, -2) if reverse else (-2, 2)
        net = PrivateNetwork(size, graph=graph)
        self.addCleanup(net.close)
        for node in names:
            for peer in graph[node]:
                self.save(net, node, peer, width=0 if {node, peer} == {a, b} else 4)
        for node in names:
            for peer in graph[node]:
                revision = self.contact(net, peer, node)['own']['revision']
                net.wait(lambda node=node, peer=peer, revision=revision:
                         (self.contact(net, node, peer)['peer_preferences'] or {}).get('revision') == revision,
                         'bilateral comfort preferences delivered')
        return net

    def discover(self, net, node=None):
        status, value = net.request(node or net.nodes[0], '/api/discover', {'amount': 2, 'mode': 'comfort'})
        self.assertEqual(status, 200, value)
        return value['id']

    def prepare(self, net):
        ident = self.discover(net)
        net.wait(lambda: all((net.proposal(n, ident) or {}).get('status') == 'pending' for n in net.nodes),
                 'comfort proposals prepared')
        return ident

    def assert_final(self, net, ident, reverse=False):
        sign = -1 if reverse else 1
        for i, node in enumerate(net.nodes):
            expected = dict(net.initial[node])
            expected[net.nodes[i-1]] -= 2 * sign
            expected[net.nodes[(i+1) % len(net.nodes)]] += 2 * sign
            self.assertEqual(net.balances(node), expected)
            self.assertEqual(sum(expected.values()), sum(net.initial[node].values()))
            for peer in net.nodes:
                if peer in expected:
                    self.assertEqual(expected[peer], -net.balances(peer)[node])
            receipts = [r for r in net.state(node)['receipts'] if r['id'] == ident]
            self.assertEqual(len(receipts), 1)
            self.assertEqual(receipts[0]['status'], 'committed')
            self.assertEqual(receipts[0]['clearing_mode'], 'comfort')
            self.assertTrue(all(b['reserved_by'] is None for b in net.state(node)['balances']))
        net.audit_local_views()

    def test_zero_balance_helpers_and_both_directions_preserve_local_knowledge(self):
        # Five participants make remote-identity checks non-vacuous.
        for size, reverse in ((3, False), (5, True)):
            with self.subTest(size=size, reverse=reverse):
                net = self.make_network(size, reverse)
                ident = self.prepare(net)
                for node in net.nodes[:-1]:
                    self.assertEqual(net.approve(node, ident)[0], 200)
                time.sleep(.25)
                for node in net.nodes:
                    self.assertEqual(net.balances(node), net.initial[node])
                self.assertEqual(net.approve(net.nodes[-1], ident)[0], 200)
                net.wait(lambda: net.completed(ident), 'comfort fulfillment')
                self.assert_final(net, ident, reverse)
                # Assistance deliberately raises gross debt: two becomes 2*(N-1).
                total = sum(max(0, value) for node in net.nodes for peer, value in net.balances(node).items()
                            if peer in net.nodes)
                self.assertEqual(total, 2 * (size - 1))

    def test_lost_fulfillment_ack_does_not_apply_assistance_twice(self):
        net = self.make_network()
        ident = self.prepare(net)
        proxy = net.proxies[net.nodes[1]]
        proxy.drop_kind = 'fulfill'
        net.approve_all(ident)
        net.wait(lambda: net.completed(ident), 'comfort fulfillment')
        net.wait(lambda: proxy.dropped_id and sum(m['body']['message_id'] == proxy.dropped_id
                 for m in proxy.messages) >= 2, 'comfort replay after lost ACK')
        self.assert_final(net, ident)

    def test_sleep_restart_retains_pinned_approval_and_reservation(self):
        net = self.make_network()
        ident = self.prepare(net)
        sleeper = net.nodes[1]
        self.assertEqual(net.approve(sleeper, ident)[0], 200)
        proposal = net.proposal(sleeper, ident)
        net.stop(sleeper, crash=True)
        for node in (net.nodes[0], net.nodes[2]):
            self.assertEqual(net.approve(node, ident)[0], 200)
        time.sleep(.3)
        net.start(sleeper)
        restored = net.proposal(sleeper, ident)
        self.assertEqual(restored['digest'], proposal['digest'])
        self.assertEqual(restored['changes'], proposal['changes'])
        self.assertTrue(restored['approved'])
        net.wait(lambda: net.completed(ident), 'sleeping approved helper recovery')
        self.assert_final(net, ident)

    def test_preimage_release_survives_crashed_origin_and_sleeping_helper(self):
        net = self.make_network()
        ident = self.prepare(net)
        for proxy in net.proxies.values():
            proxy.block_kind = 'fulfill'
        net.approve_all(ident)
        origin = net.nodes[0]
        net.wait(lambda: net.proposal(origin, ident)['status'] == 'committed', 'durable comfort release')
        target = net.wait(lambda: next((node for node, proxy in net.proxies.items()
                            if any(m['body']['kind'] == 'fulfill' for m in proxy.messages)), None),
                         'blocked comfort fulfillment')
        net.stop(target, crash=True)
        net.stop(origin, crash=True)
        net.start(origin)
        self.assertEqual(net.proposal(origin, ident)['status'], 'committed')
        for proxy in net.proxies.values():
            proxy.block_kind = None
        net.start(target)
        net.wait(lambda: net.completed(ident), 'released comfort settlement recovery')
        self.assert_final(net, ident)

    def test_reservation_prevents_overlapping_search_and_preference_edits(self):
        net = self.make_network()
        ident = self.prepare(net)
        a, b, _ = net.nodes
        status, value = net.request(a, '/api/discover', {'amount': 2, 'mode': 'comfort'})
        self.assertEqual(status, 400, value)
        current = self.contact(net, a, b)['own']
        status, value = net.request(a, '/api/contacts/' + b + '/preferences',
                                   dict(current, expected_revision=current['revision'], auto_adjust=False))
        self.assertEqual(status, 400, value)
        for node in net.nodes:
            self.assertEqual(net.balances(node), net.initial[node])
        net.approve_all(ident)
        net.wait(lambda: net.completed(ident), 'reserved proposal fulfillment')
        self.assert_final(net, ident)

    def test_simultaneous_overlapping_discovery_drains_without_partial_changes(self):
        net = self.make_network()
        # Hold discovery traffic so both origins create a search before either
        # can reserve its edges. This is a concurrent race, not a second request
        # submitted after the first proposal already owns its reservations.
        for proxy in net.proxies.values():
            proxy.block_kind = 'probe'
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(self.discover, net, node) for node in net.nodes[:2]]
            identifiers = [future.result() for future in futures]
        for proxy in net.proxies.values():
            proxy.block_kind = None

        def settlement_outboxes_drained():
            for node in net.nodes:
                with sqlite3.connect(net.directory / f'{node}.sqlite') as db:
                    if any(json.loads(row[0])['kind'] != 'preferences'
                           for row in db.execute('SELECT data FROM outbox')):
                        return False
            return True

        net.wait(settlement_outboxes_drained, 'concurrent discovery traffic drained')
        for node in net.nodes:
            self.assertEqual(net.balances(node), net.initial[node])
        completed = []
        for ident in identifiers:
            proposals = [net.proposal(node, ident) for node in net.nodes]
            pending = [p for p in proposals if p and p['status'] == 'pending']
            if pending:
                self.assertEqual(len(pending), len(net.nodes), proposals)
                net.approve_all(ident)
                net.wait(lambda ident=ident: net.completed(ident), 'winning concurrent proposal')
                completed.append(ident)
            else:
                self.assertTrue(all(p is None or p['status'] == 'aborted' for p in proposals), proposals)
        self.assertLessEqual(len(completed), 1)
        net.wait(settlement_outboxes_drained, 'concurrent settlement traffic drained')
        for node in net.nodes:
            self.assertTrue(all(b['reserved_by'] is None for b in net.state(node)['balances']))
            self.assertEqual(sum(net.balances(node).values()), sum(net.initial[node].values()))
            if not completed:
                self.assertEqual(net.balances(node), net.initial[node])
        net.audit_local_views()

    def test_stale_bilateral_quote_aborts_without_balance_changes(self):
        net = self.make_network()
        a, b, _ = net.nodes
        net.proxies[b].block_kind = 'prepare'
        ident = self.discover(net)
        net.wait(lambda: (net.proposal(a, ident) or {}).get('status') == 'pending', 'origin reservation')
        self.save(net, b, a, width=0, auto=False)
        net.proxies[b].block_kind = None
        net.wait(lambda: all((net.proposal(node, ident) or {}).get('status') == 'aborted' for node in net.nodes),
                 'stale preference snapshot abort')
        for node in net.nodes:
            self.assertEqual(net.balances(node), net.initial[node])
            self.assertTrue(all(b['reserved_by'] is None for b in net.state(node)['balances']))
        net.audit_local_views()

    def test_neutral_helper_cannot_originate_useless_fluctuation(self):
        net = self.make_network()
        status, value = net.request(net.nodes[2], '/api/discover', {'amount': 2, 'mode': 'comfort'})
        self.assertEqual(status, 400, value)
        for node in net.nodes:
            self.assertEqual(net.balances(node), net.initial[node])
            self.assertEqual(net.state(node)['receipts'], [])


if __name__ == '__main__':
    unittest.main()
