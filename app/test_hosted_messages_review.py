"""Independent hosted chat review against disposable PostgreSQL node stores.

Covers an acknowledged receiver commit whose sender ACK is lost, peer-bound
identity, private aliases, reserved/zero relationships and protocol queue priority.
No running demo or user browser is read or modified.
"""
import copy
import json
import os
import secrets
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import urlsplit

import test_hosted_gateway as gateway
from test_hosted_auth import ORIGIN


@unittest.skipUnless(os.environ.get('LEDGERLOOPS_TEST_POSTGRES_DSN'),
                     'Set LEDGERLOOPS_TEST_POSTGRES_DSN for real PostgreSQL review tests')
class HostedMessagesIndependentReview(unittest.TestCase):
    setUp = gateway.HostedGatewayTests.setUp
    tearDown = gateway.HostedGatewayTests.tearDown
    enroll = gateway.HostedGatewayTests.enroll
    get = gateway.HostedGatewayTests.get
    post = gateway.HostedGatewayTests.post
    connect = gateway.HostedGatewayTests.connect
    deliver = gateway.HostedGatewayTests.deliver
    pump = gateway.HostedGatewayTests.pump

    @staticmethod
    def route(peer, suffix='messages'):
        return '/api/contacts/'+peer['account']['node_id']+'/'+suffix

    def financial_snapshot(self, user):
        with self.runtime.node(user['account']['node_id']) as node:
            return {table: [dict(row) for row in node.db.execute('SELECT * FROM '+table+' ORDER BY rowid')]
                    for table in ('balances', 'contacts', 'reservations', 'obligations', 'proposals', 'receipts')}

    def test_ack_loss_retries_once_without_affecting_reserved_paused_relationship(self):
        alice, bob = self.enroll('Alice'), self.enroll('Bob')
        self.connect(alice, bob)
        self.pump()
        proposal = self.post(alice, '/api/obligations', dict(id=secrets.token_hex(32),
            peer=bob['account']['node_id'], amount=2, direction='i_owe', description='Pending TEST delivery'))
        self.pump()
        for user in (alice, bob):
            self.post(user, '/api/pause', {'paused': True})
        before = [self.financial_snapshot(user) for user in (alice, bob)]
        self.assertTrue(before[0]['reservations'], 'The fixture must hold an actual pending delivery reservation')
        identity = secrets.token_hex(32)
        sent = self.post(alice, self.route(bob), {'id': identity, 'text': 'Can we check this delivery?\nThanks.'})['message']
        self.assertEqual(sent['status'], 'queued')

        # Receiver commits, but the sender never observes its successful reply.
        def lose_ack(request, timeout):
            self.deliver(request, timeout)
            raise URLError('Isolated TEST: lost acknowledgement after receiver commit')
        with patch('hosted_runtime.urlopen', lose_ack):
            self.runtime.tick(alice['account']['node_id'])
        incoming_before = self.get(bob, self.route(alice))
        self.assertEqual(len(incoming_before), 1)
        self.assertEqual(incoming_before[0]['text'], sent['text'])
        self.assertEqual(incoming_before[0]['status'], 'received')
        self.assertEqual(self.get(alice, self.route(bob))[0]['status'], 'queued')

        # A worker restart constructs fresh nodes, then retries the durable row.
        self.runtime = type(self.runtime)(self.stores, ORIGIN)
        with patch('hosted_runtime.urlopen', self.deliver):
            self.runtime.tick(alice['account']['node_id'])
        self.assertEqual(self.get(bob, self.route(alice)), incoming_before,
                         'Duplicate delivery must preserve the original receiver timestamps and text')
        outgoing = self.get(alice, self.route(bob))
        self.assertEqual(len(outgoing), 1)
        self.assertEqual(outgoing[0]['status'], 'delivered')
        delivered = copy.deepcopy(outgoing[0])
        repeated = self.post(alice, self.route(bob), {'id': identity, 'text': sent['text']})['message']
        self.assertEqual(repeated, delivered, 'Explicit browser retries must return the original message')
        self.assertEqual([self.financial_snapshot(user) for user in (alice, bob)], before,
                         'Chat must not alter balances, reservations, preferences, deliveries or clearing')

    def test_incoming_identity_is_peer_bound_alias_is_private_and_metadata_is_rejected(self):
        alice, bob, carol = (self.enroll(name) for name in ('Alice', 'Duplicate', 'Duplicate'))
        self.connect(alice, bob)
        self.connect(alice, carol)
        self.pump()
        for user in (alice, bob, carol):
            self.post(user, '/api/pause', {'paused': True})
        before_bob = self.get(bob, '/api/state')
        alias = '<img src=x onerror=alert(1)>'
        renamed = self.post(alice, self.route(bob, 'rename'), {'name': alias})
        self.assertEqual(renamed['name'], alias)
        self.assertEqual(self.get(bob, '/api/state'), before_bob, 'A private alias must not change the peer node')
        self.assertEqual(next(contact for contact in self.get(alice, '/api/state')['contacts']
                              if contact['peer'] == bob['account']['node_id'])['name'], alias)
        self.assertEqual(self.get(alice, '/api/state')['outbox_pending'], 0,
                         'Renaming must not announce a private alias on the neighbour channel')
        same_id = secrets.token_hex(32)
        self.post(bob, self.route(alice), {'id': same_id, 'text': '<script>TEST literal message</script>'})
        self.post(carol, self.route(alice), {'id': same_id, 'text': 'Different authenticated neighbour'})
        self.pump()
        self.assertEqual(self.get(alice, self.route(bob))[0]['text'], '<script>TEST literal message</script>')
        self.assertEqual(self.get(alice, self.route(carol))[0]['text'], 'Different authenticated neighbour')
        self.assertEqual(len(self.get(alice, self.route(bob))), 1)
        self.assertEqual(len(self.get(alice, self.route(carol))), 1)
        # Asking with another owner id cannot select that owner's private store.
        self.assertEqual(self.get(carol, self.route(alice)+'?node_id='+alice['account']['node_id'])[0]['text'],
                         'Different authenticated neighbour')
        with self.runtime.node(alice['account']['node_id']) as node:
            bob_key = node.peers[bob['account']['node_id']]['key']
        envelope = dict(kind='hosted_message', protocol='hosted-message-v1', id=secrets.token_hex(32),
                        text='Forged metadata', message_id=secrets.token_hex(16))
        endpoint = '/nodes/'+alice['account']['node_id']+'/peer/message'
        headers = {'X-Peer-ID': bob['account']['node_id'], 'Authorization': 'Bearer '+bob_key}
        for extra in ({'created_at': 10**30}, {'peer': carol['account']['node_id']}, {'direction': 'outgoing'}):
            response = self.transport_client.post(endpoint, base_url=ORIGIN, headers=headers,
                                                 json=dict(envelope, **extra))
            self.assertEqual(response.status_code, 400, 'Peer metadata cannot override local identity or timestamps')
        spoofed = self.transport_client.post(endpoint, base_url=ORIGIN,
            headers=dict(headers, **{'X-Peer-ID': carol['account']['node_id']}), json=envelope)
        self.assertEqual(spoofed.status_code, 403, 'Sender id must match its own authenticated neighbour secret')
        self.assertEqual(len(self.get(alice, self.route(bob))), 1)

    def test_offline_chat_backlog_does_not_starve_online_protocol_envelopes(self):
        alice, bob, carol = (self.enroll(name) for name in ('Alice', 'Bob', 'Carol'))
        self.connect(alice, bob)
        self.connect(alice, carol)
        self.pump()
        for user in (alice, bob, carol):
            self.post(user, '/api/pause', {'paused': True})
        for index in range(5):
            self.post(alice, self.route(bob), {'id': secrets.token_hex(32), 'text': 'Offline queue '+str(index)})
        contact = next(c for c in self.get(alice, '/api/state')['contacts'] if c['peer'] == carol['account']['node_id'])
        self.post(alice, self.route(carol, 'preferences'), dict(contact['own'], expected_revision=contact['own']['revision']))
        attempted = []
        def offline_bob(request, timeout):
            attempted.append(json.loads(request.data)['kind'])
            if '/nodes/'+bob['account']['node_id']+'/' in urlsplit(request.full_url).path:
                raise URLError('Isolated TEST neighbour offline')
            return self.deliver(request, timeout)
        with patch('hosted_runtime.urlopen', offline_bob):
            self.runtime.tick(alice['account']['node_id'])
        self.assertEqual(attempted[0], 'preferences', 'Protocol envelopes must precede queued chats in the limited batch')
        received = next(c for c in self.get(carol, '/api/state')['contacts'] if c['peer'] == alice['account']['node_id'])
        self.assertEqual(received['peer_preferences']['revision'], contact['own']['revision']+1)
        self.assertTrue(all(message['status'] == 'queued' for message in self.get(alice, self.route(bob))))


if __name__ == '__main__':
    unittest.main()
