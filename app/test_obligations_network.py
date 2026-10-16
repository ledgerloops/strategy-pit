"""Obligations over authenticated HTTP and isolated node processes."""
import secrets
import unittest

from test_private_network import PrivateNetwork


class ObligationNetworkTests(unittest.TestCase):
    def network(self):
        names = [f'participant_{i:03d}' for i in range(3)]
        graph = {a: {b: 0 for b in names if a != b} for a in names}
        net = PrivateNetwork(3, graph=graph)
        self.addCleanup(net.close)
        for owner in net.nodes:
            for peer in net.nodes:
                if owner == peer:
                    continue
                net.wait(lambda owner=owner, peer=peer: self.contact(net, owner, peer)['peer_preferences'] is not None,
                         'initial preferences')
                own = self.contact(net, owner, peer)['own']
                status, result = net.request(owner, '/api/contacts/' + peer + '/preferences',
                      dict(expected_revision=own['revision'], credit_limit=10,
                           comfort_min=0, comfort_max=0, auto_adjust=False))
                self.assertEqual(status, 200, result)
        for owner in net.nodes:
            for peer in net.nodes:
                if owner != peer:
                    revision = self.contact(net, owner, peer)['own']['revision']
                    net.wait(lambda owner=owner, peer=peer, revision=revision:
                             self.contact(net, peer, owner)['peer_preferences']['revision'] == revision,
                             'credit limit sync')
        return net

    @staticmethod
    def contact(net, owner, peer):
        return next(c for c in net.state(owner)['contacts'] if c['peer'] == peer)

    @staticmethod
    def obligation(net, owner, ident):
        return next((o for o in net.state(owner)['obligations'] if o['id'] == ident), None)

    def propose(self, net, owner, peer, amount=2):
        body = dict(id=secrets.token_hex(32), peer=peer, amount=amount, direction='i_owe', description='Shared lunch')
        status, result = net.request(owner, '/api/obligations', body)
        self.assertEqual(status, 200, result)
        return body, result['obligation']

    def approve(self, net, owner, obligation):
        status, result = net.request(owner, '/api/obligations/' + obligation['id'] + '/approve',
                                     dict(digest=obligation['digest']))
        self.assertEqual(status, 200, result)

    def completed(self, net, ident, owners):
        return all(self.obligation(net, owner, ident)['status'] == 'committed' for owner in owners)

    def test_http_auth_limits_decline_list_and_no_early_economic_effect(self):
        net = self.network(); a, b, c = net.nodes
        body = dict(id=secrets.token_hex(32), peer=b, amount=1, direction='i_owe', description='Lunch')
        self.assertEqual(net.request(a, '/api/obligations', body, token=False)[0], 401)
        self.assertEqual(net.request(a, '/api/obligations', dict(body, amount=11))[0], 400)
        body, proposal = self.propose(net, a, b)
        self.assertEqual(net.balances(a)[b], 0)
        net.wait(lambda: self.obligation(net, b, proposal['id']) is not None, 'proposal delivery')
        self.assertEqual(net.balances(b)[a], 0)
        self.assertEqual(net.request(b, '/api/obligations')[1][0]['direction'], 'peer_owes')
        self.assertEqual(net.request(a, '/api/obligations', body)[1]['obligation']['id'], proposal['id'])
        wire = next(m['body'] for m in net.proxies[b].messages if m['body'].get('kind') == 'obligation_offer')
        headers = {'Authorization': 'Bearer ' + net.configs[b]['peers'][a]['key'], 'X-Peer-ID': c}
        self.assertEqual(net.request(b, '/peer/message', wire, token=False, headers=headers)[0], 401)
        headers['Authorization'] = 'Bearer ' + net.configs[b]['peers'][c]['key']
        self.assertEqual(net.request(b, '/peer/message', wire, token=False, headers=headers)[0], 400)
        self.assertEqual(net.request(b, '/api/obligations/'+proposal['id']+'/approve', dict(digest='00'*32))[0], 400)
        self.assertEqual(net.request(b, '/api/obligations/'+proposal['id']+'/decline', dict(digest=proposal['digest']))[0], 200)
        net.wait(lambda: self.obligation(net, a, proposal['id'])['status'] == 'aborted', 'decline delivery')
        self.assertEqual(net.balances(a)[b], 0)
        self.assertEqual(net.balances(b)[a], 0)

    def test_committing_restart_and_lost_commit_ack_apply_once_even_when_paused(self):
        net = self.network(); a, b, _ = net.nodes
        body, proposal = self.propose(net, a, b)
        ident = proposal['id']
        net.wait(lambda: self.obligation(net, b, ident) is not None, 'offer delivery')
        net.proxies[b].block_kind = 'obligation_commit'
        self.approve(net, b, proposal)
        net.request(b, '/api/pause', dict(paused=True))
        net.wait(lambda: self.obligation(net, a, ident)['status'] == 'committing', 'origin durable commit')
        self.assertEqual(net.balances(a)[b], -2)
        self.assertEqual(net.balances(b)[a], 0)
        self.assertIsNotNone(self.contact(net, a, b)['reserved_by'])
        net.stop(a, crash=True); net.start(a)
        net.proxies[b].drop_kind = 'obligation_commit'
        net.proxies[b].block_kind = None
        net.wait(lambda: net.proxies[b].dropped_id is not None, 'commit delivered with lost ACK')
        dropped_id = net.proxies[b].dropped_id
        attempts = sum(m['body'].get('message_id') == dropped_id for m in net.proxies[b].messages)
        net.stop(b, crash=True); net.start(b)
        net.wait(lambda: self.completed(net, ident, (a, b)), 'post-restart agreement')
        net.wait(lambda: sum(m['body'].get('message_id') == dropped_id for m in net.proxies[b].messages) > attempts,
                 'same commit redelivery after recipient restart')
        self.assertEqual(net.balances(a)[b], -2)
        self.assertEqual(net.balances(b)[a], 2)
        for owner, peer in ((a, b), (b, a)):
            self.assertIsNone(self.contact(net, owner, peer)['reserved_by'])
            self.assertEqual(self.obligation(net, owner, ident)['status'], 'committed')
        self.assertEqual(net.request(a, '/api/obligations', body)[1]['obligation']['status'], 'committed')

    def test_stale_offer_rejects_and_recovers_deferred_preferences(self):
        net = self.network(); a, b, _ = net.nodes
        net.proxies[b].block_kind = 'obligation_offer'
        _, proposal = self.propose(net, a, b)
        own = self.contact(net, b, a)['own']
        self.assertEqual(net.request(b, '/api/contacts/'+a+'/preferences', dict(expected_revision=own['revision'],
            credit_limit=0, comfort_min=0, comfort_max=0, auto_adjust=False))[0], 200)
        net.proxies[b].block_kind = None
        net.wait(lambda: self.obligation(net, a, proposal['id'])['status'] == 'aborted', 'stale proposal abort')
        net.wait(lambda: self.contact(net, a, b)['peer_preferences']['credit_limit'] == 0, 'deferred preferences')
        for owner, peer in ((a, b), (b, a)):
            self.assertEqual(net.balances(owner)[peer], 0)
            self.assertIsNone(self.contact(net, owner, peer)['reserved_by'])

    def test_three_new_obligations_clear_through_existing_http_protocol(self):
        net = self.network(); a, b, c = net.nodes
        for owner, peer in ((a, b), (b, c), (c, a)):
            _, proposal = self.propose(net, owner, peer)
            net.wait(lambda peer=peer, ident=proposal['id']: self.obligation(net, peer, ident) is not None,
                     'recipient review')
            self.approve(net, peer, proposal)
            net.wait(lambda ident=proposal['id'], owner=owner, peer=peer: self.completed(net, ident, (owner, peer)),
                     'bilateral obligation agreement')
        status, result = net.request(a, '/api/discover', dict(amount=2))
        self.assertEqual(status, 200, result)
        ident = result['id']
        net.wait(lambda: all(net.proposal(owner, ident) is not None for owner in net.nodes), 'new obligations clearing')
        net.approve_all(ident)
        net.wait(lambda: net.completed(ident), 'new obligations settled')
        for owner in net.nodes:
            self.assertTrue(all(net.balances(owner)[peer] == 0 for peer in net.nodes if peer != owner))
            self.assertEqual(len(net.state(owner)['obligations']), 2)
            self.assertEqual(len(net.state(owner)['receipts']), 1)


if __name__ == '__main__':
    unittest.main()
