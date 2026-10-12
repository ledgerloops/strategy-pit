"""Independent comfort preferences tests using three real HTTP node processes."""
import copy
import time
import unittest
import uuid
from urllib.parse import quote
from private_node import PROTOCOL
from test_private_network import PrivateNetwork


class ComfortNetworkTests(unittest.TestCase):
    def make_network(self):
        net = PrivateNetwork(3)
        self.addCleanup(net.close)
        for node in net.nodes:
            for peer in net.nodes:
                if node != peer:
                    net.wait(lambda node=node, peer=peer: self.contact(net, node, peer)['peer_preferences'] is not None,
                             'initial neighbour preferences')
        return net

    @staticmethod
    def contact(net, node, peer):
        return next(c for c in net.state(node)['contacts'] if c['peer'] == peer)

    def save(self, net, node, peer, credit_limit=10, comfort_min=-10, comfort_max=10,
             auto_adjust=False, expected_revision=None):
        current = self.contact(net, node, peer)['own']['revision']
        return net.request(node, '/api/contacts/' + quote(peer, safe='') + '/preferences',
                           dict(expected_revision=current if expected_revision is None else expected_revision,
                                credit_limit=credit_limit, comfort_min=comfort_min,
                                comfort_max=comfort_max, auto_adjust=auto_adjust))

    def synced(self, net, owner, peer):
        revision = self.contact(net, owner, peer)['own']['revision']
        net.wait(lambda: self.contact(net, peer, owner)['peer_preferences']['revision'] == revision,
                 'preference revision delivery')

    def test_signed_intersection_and_no_automatic_settlement(self):
        net = self.make_network()
        a, b, _ = net.nodes
        original = {node: net.balances(node) for node in net.nodes}
        self.assertEqual(self.save(net, a, b, 10, -8, 7, True)[0], 200)
        self.assertEqual(self.save(net, b, a, 6, -4, 5, True)[0], 200)
        self.synced(net, a, b); self.synced(net, b, a)
        left, right = self.contact(net, a, b), self.contact(net, b, a)
        self.assertEqual(left['shared_comfort'], dict(hard_min=-6, hard_max=10, min=-5, max=4, empty=False))
        self.assertEqual(right['shared_comfort'], dict(hard_min=-10, hard_max=6, min=-4, max=5, empty=False))
        self.assertFalse(left['auto_adjust_active'])
        self.assertTrue(left['own']['auto_adjust'])
        for node in net.nodes:
            self.assertEqual(net.balances(node), original[node])
            self.assertEqual(net.state(node)['receipts'], [])

    def test_empty_overlap_remains_empty_and_does_not_create_a_balance(self):
        net = self.make_network()
        a, b, _ = net.nodes
        before = net.balances(a)
        self.assertEqual(self.save(net, a, b, 10, 2, 4)[0], 200)
        self.assertEqual(self.save(net, b, a, 10, 2, 4)[0], 200)
        self.synced(net, a, b); self.synced(net, b, a)
        overlap = self.contact(net, a, b)['shared_comfort']
        self.assertTrue(overlap['empty'])
        self.assertEqual((overlap['min'], overlap['max']), (2, -2))
        self.assertEqual(net.balances(a), before)

    def test_lower_credit_keeps_existing_debt_and_allows_reduction(self):
        net = self.make_network()
        a, b, _ = net.nodes
        before = {node: net.balances(node) for node in net.nodes}
        self.assertEqual(self.save(net, b, a, 0, 0, 0)[0], 200)
        self.synced(net, b, a)
        self.assertEqual(self.contact(net, a, b)['hard_min'], 0)
        self.assertEqual(net.balances(a)[b], -7)
        ident = net.prepared_cycle()
        net.approve_all(ident)
        net.wait(lambda: net.completed(ident), 'manual cancellation after lower cap')
        self.assertEqual(net.balances(a)[b], -4)
        for node in net.nodes:
            self.assertEqual(sum(net.balances(node).values()), sum(before[node].values()))
        net.stop(a, crash=True); net.start(a)
        self.assertEqual(self.contact(net, a, b)['peer_preferences']['credit_limit'], 0)
        self.assertEqual(net.balances(a)[b], -4)

    def test_revision_and_peer_authority_checks(self):
        net = self.make_network()
        a, b, c = net.nodes
        original = copy.deepcopy(self.contact(net, a, b))
        self.assertEqual(self.save(net, a, b, 11, -2, 2)[0], 200)
        current = self.contact(net, a, b)['own']
        self.assertEqual(self.save(net, a, b, 99, -2, 2, expected_revision=original['own']['revision'])[0], 400)
        self.assertEqual(self.contact(net, a, b)['own'], current)
        self.assertEqual(self.save(net, b, a, 12, -3, 3)[0], 200)
        self.synced(net, b, a)
        peer_value = self.contact(net, a, b)['peer_preferences']
        headers = {'Authorization': 'Bearer ' + net.configs[a]['peers'][b]['key'], 'X-Peer-ID': b}
        def deliver(value, override=None):
            return net.request(a, '/peer/message', dict(kind='preferences', protocol=PROTOCOL,
                               preferences=value, message_id=uuid.uuid4().hex), token=False, headers=override or headers)
        self.assertEqual(deliver(peer_value)[0], 200)
        stale = dict(peer_value, revision=1, credit_limit=999)
        self.assertEqual(deliver(stale)[0], 200)
        conflict = dict(peer_value, credit_limit=999)
        self.assertEqual(deliver(conflict)[0], 400)
        impostor = dict(headers, **{'X-Peer-ID': c})
        self.assertEqual(deliver(dict(peer_value, revision=peer_value['revision']+1), impostor)[0], 401)
        self.assertEqual(self.contact(net, a, b)['peer_preferences'], peer_value)
        self.assertEqual(self.contact(net, a, b)['own'], current)

    def test_reservation_blocks_local_edits_and_defers_peer_update_until_settlement(self):
        net = self.make_network()
        a, b, _ = net.nodes
        old_revision = self.contact(net, a, b)['peer_preferences']['revision']
        net.proxies[b].block_kind = 'prepare'
        ident = net.discover()['id']
        net.wait(lambda: net.proposal(a, ident) is not None, 'origin reservation')
        self.assertEqual(self.save(net, a, b, 100, -20, 20)[0], 400)
        self.assertEqual(self.save(net, b, a, 100, -20, 20)[0], 200)
        time.sleep(.7)
        self.assertEqual(self.contact(net, a, b)['peer_preferences']['revision'], old_revision)
        self.assertEqual(self.contact(net, a, b)['reserved_by'], ident)
        net.proxies[b].block_kind = None
        net.wait(lambda: all(net.proposal(node, ident) is not None for node in net.nodes), 'all prepared')
        net.approve_all(ident)
        net.wait(lambda: net.completed(ident), 'settlement despite deferred update')
        self.synced(net, b, a)
        self.assertEqual(self.contact(net, a, b)['peer_preferences']['credit_limit'], 100)
        self.assertIsNone(self.contact(net, a, b)['reserved_by'])


if __name__ == '__main__':
    unittest.main()
