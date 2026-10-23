"""One sender snapshot per ACK batch, preserving retry and crash semantics."""
from contextlib import contextmanager
import json
import os
import secrets
import unittest
from unittest.mock import patch
from urllib.error import URLError

import test_hosted_gateway as gateway
from hosted_storage import TABLE


@unittest.skipUnless(os.environ.get('LEDGERLOOPS_TEST_POSTGRES_DSN'),
                     'Set LEDGERLOOPS_TEST_POSTGRES_DSN for real PostgreSQL batch tests')
class HostedAckBatchTests(unittest.TestCase):
    setUp = gateway.HostedGatewayTests.setUp
    tearDown = gateway.HostedGatewayTests.tearDown
    enroll = gateway.HostedGatewayTests.enroll
    get = gateway.HostedGatewayTests.get
    post = gateway.HostedGatewayTests.post
    connect = gateway.HostedGatewayTests.connect
    deliver = gateway.HostedGatewayTests.deliver
    pump = gateway.HostedGatewayTests.pump

    def version(self, user):
        key = self.prefix+self.runtime.key(user['account']['node_id'])
        with self.factory._pool.connection() as connection:
            return connection.execute(f'SELECT version FROM {TABLE} WHERE node_id=%s', (key,)).fetchone()[0]

    def fixture(self, count):
        alice, bob = self.enroll('ACK Alice'), self.enroll('ACK Bob')
        self.connect(alice, bob)
        self.pump()
        route = '/api/contacts/'+bob['account']['node_id']+'/messages'
        messages = [self.post(alice, route, {'id':secrets.token_hex(32), 'text':'Batch TEST '+str(index)})['message']
                    for index in range(count)]
        return alice, bob, messages

    def test_five_successful_envelopes_replace_sender_snapshot_once(self):
        alice, bob, messages = self.fixture(5)
        before = self.version(alice)
        with patch('hosted_runtime.urlopen', self.deliver):
            hint = self.runtime.tick(alice['account']['node_id'])
        self.assertEqual(self.version(alice)-before, 1)
        self.assertEqual(hint, dict(retry_outbox=False, next_search_at=None))
        sent = self.get(alice, '/api/contacts/'+bob['account']['node_id']+'/messages')
        received = self.get(bob, '/api/contacts/'+alice['account']['node_id']+'/messages')
        self.assertEqual({item['id'] for item in sent}, {item['id'] for item in messages})
        self.assertEqual(len(received), 5)
        self.assertTrue(all(item['status'] == 'delivered' and item['delivered_at'] is not None for item in sent))
        idle_before = self.version(alice)
        self.assertEqual(self.runtime.tick(alice['account']['node_id']), hint)
        self.assertEqual(self.version(alice), idle_before)

    def test_partial_failure_keeps_only_failed_rows_and_preserves_protocol_priority(self):
        alice, bob, messages = self.fixture(4)
        peer = bob['account']['node_id']
        own = self.get(alice, '/api/state')['contacts'][0]['own']
        self.post(alice, '/api/contacts/'+peer+'/preferences', dict(own, expected_revision=own['revision']))
        failed = {messages[1]['id'], messages[3]['id']}
        attempted = []

        def partly_unavailable(request, timeout):
            data = json.loads(request.data)
            attempted.append(data['kind'])
            if data.get('id') in failed:
                raise URLError('Isolated TEST partial failure')
            return self.deliver(request, timeout)

        before = self.version(alice)
        with patch('hosted_runtime.urlopen', partly_unavailable):
            hint = self.runtime.tick(alice['account']['node_id'])
        self.assertEqual(attempted[0], 'preferences')
        self.assertEqual(self.version(alice)-before, 1)
        self.assertEqual(hint, dict(retry_outbox=True, next_search_at=None))
        rows = self.get(alice, '/api/contacts/'+peer+'/messages')
        self.assertEqual({row['id'] for row in rows if row['status'] == 'queued'}, failed)
        self.assertEqual(self.get(alice, '/api/state')['outbox_pending'], 2)
        self.assertEqual(self.get(bob, '/api/state')['contacts'][0]['peer_preferences']['revision'], own['revision']+1)
        before_failed = self.version(alice)
        with patch('hosted_runtime.urlopen', side_effect=URLError('Still unavailable')):
            self.assertEqual(self.runtime.tick(alice['account']['node_id']), hint)
        self.assertEqual(self.version(alice), before_failed, 'Failed retries must not write sender snapshots')

    def test_crash_before_batch_ack_replays_durable_rows_without_duplicate_receiver_records(self):
        alice, bob, _ = self.fixture(5)
        sender = alice['account']['node_id']
        original = self.runtime.node
        own_contexts = 0

        @contextmanager
        def fail_ack(ident):
            nonlocal own_contexts
            if ident == sender:
                own_contexts += 1
                if own_contexts == 2:
                    raise RuntimeError('Isolated TEST crash before ACK batch commit')
            with original(ident) as node:
                yield node

        before = self.version(alice)
        with patch.object(self.runtime, 'node', fail_ack), patch('hosted_runtime.urlopen', self.deliver):
            with self.assertRaisesRegex(RuntimeError, 'before ACK batch'):
                self.runtime.tick(sender)
        self.assertEqual(self.version(alice), before)
        received = self.get(bob, '/api/contacts/'+sender+'/messages')
        self.assertEqual(len(received), 5)
        self.assertEqual(self.get(alice, '/api/state')['outbox_pending'], 5)
        restarted = type(self.runtime)(self.stores, self.runtime.origin)
        with patch('hosted_runtime.urlopen', self.deliver):
            hint = restarted.tick(sender)
        self.assertFalse(hint['retry_outbox'])
        self.assertEqual(self.version(alice)-before, 1)
        self.assertEqual(self.get(bob, '/api/contacts/'+sender+'/messages'), received,
                         'Receiver duplicates preserve original local timestamps and text')
        rows = self.get(alice, '/api/contacts/'+bob['account']['node_id']+'/messages')
        self.assertTrue(all(row['status'] == 'delivered' for row in rows))

    def test_search_hint_tracks_local_backoff_and_pause_without_an_extra_snapshot_read(self):
        alice, bob, _ = self.fixture(0)
        carol = self.enroll('ACK Carol')
        self.connect(alice, carol)
        self.pump()
        sender = alice['account']['node_id']
        for peer, value in ((bob, 1), (carol, -1)):
            destination = peer['account']['node_id']
            for owner, other, amount in ((sender, destination, value), (destination, sender, -value)):
                with self.runtime.node(owner) as node:
                    node.db.execute('UPDATE balances SET balance=? WHERE peer=?', (amount, other))
        before = self.version(alice)
        with patch('hosted_runtime.time.time', return_value=2000), \
                patch('hosted_runtime.secrets.randbelow', return_value=0), \
                patch('hosted_runtime.urlopen', side_effect=URLError('Isolated offline peers')):
            hint = self.runtime.tick(sender)
        self.assertEqual(hint, dict(retry_outbox=True, next_search_at=2004))
        self.assertEqual(self.version(alice)-before, 1, 'Search and its hint use the same local transaction')
        before_idle = self.version(alice)
        with patch('hosted_runtime.time.time', return_value=2001), \
                patch('hosted_runtime.urlopen', side_effect=URLError('Still offline')):
            self.assertEqual(self.runtime.tick(sender), hint)
        self.assertEqual(self.version(alice), before_idle)
        self.post(alice, '/api/pause', {'paused':True})
        with patch('hosted_runtime.urlopen', side_effect=URLError('Still offline')):
            self.assertEqual(self.runtime.tick(sender), dict(retry_outbox=True, next_search_at=None))


if __name__ == '__main__':
    unittest.main()
