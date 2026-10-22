"""Private aliases, browser authorization and peer-filtered durable history."""
import json
import secrets
import tempfile
import unittest
from unittest.mock import patch

from hosted_runtime import HostedRuntime, MESSAGE_KIND, MESSAGE_PROTOCOL
from hosted_server import create_app
from test_hosted_named_invites import LocalStores
from test_hosted_auth import ORIGIN


class HostedMessageTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.stores = LocalStores(directory.name)
        self.runtime = HostedRuntime(self.stores, ORIGIN)
        self.alice, self.bob, self.carol = ('n_'+char*32 for char in 'abc')
        for ident, name in ((self.alice, 'Alice'), (self.bob, 'Bob'), (self.carol, 'Carol')):
            self.runtime.provision(dict(node_id=ident, name=name))
        self.runtime.accept_invite(self.bob, self.runtime.invite(self.alice, 'Bob')['invite_token'])

    def packet(self, ident=None, text='Hello'):
        return dict(kind=MESSAGE_KIND, protocol=MESSAGE_PROTOCOL,
                    id=ident or secrets.token_hex(32), text=text, message_id=secrets.token_hex(16))

    def channel_key(self):
        with self.runtime.node(self.alice) as node:
            return node.peers[self.bob]['key']

    def test_names_and_messages_validate_content_and_direct_peer(self):
        for name in ('', '   ', 'x'*81, None, 7, 'A\nB', 'A\u202eB', '\ud800'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.runtime.rename(self.alice, self.bob, name)
        for text in ('', '   ', 'x'*2001, None, True, 'a\x00b', 'a\r\nb', 'a\u202eb', '\ud800'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.runtime.send_message(self.alice, self.bob, secrets.token_hex(32), text)
        for ident in ('', 'a'*63, 'A'*64, None, 8):
            with self.subTest(id=ident), self.assertRaises(ValueError):
                self.runtime.send_message(self.alice, self.bob, ident, 'Hello')
        for peer in (self.alice, self.carol, 'unknown'):
            with self.subTest(peer=peer):
                for action in (lambda: self.runtime.rename(self.alice, peer, 'Name'),
                               lambda: self.runtime.send_message(self.alice, peer, secrets.token_hex(32), 'Hello'),
                               lambda: self.runtime.messages(self.alice, peer),
                               lambda: self.runtime.history(self.alice, peer)):
                    with self.assertRaises(ValueError):
                        action()
        result = self.runtime.send_message(self.alice, self.bob, secrets.token_hex(32),
                                           '  <b>Hello</b>\n\t👩\u200d💻  ')
        self.assertEqual(result['message']['text'], '<b>Hello</b>\n\t👩\u200d💻')

    def test_outgoing_retry_binds_peer_and_text_without_duplicate_outbox(self):
        self.runtime.accept_invite(self.carol, self.runtime.invite(self.alice, 'Carol')['invite_token'])
        ident = secrets.token_hex(32)
        first = self.runtime.send_message(self.alice, self.bob, ident, '  Hello  ')
        restarted = HostedRuntime(self.stores, ORIGIN)
        self.assertEqual(restarted.send_message(self.alice, self.bob, ident, 'Hello'), first)
        for peer, text in ((self.bob, 'Changed'), (self.carol, 'Hello')):
            with self.subTest(peer=peer), self.assertRaisesRegex(ValueError, 'different terms'):
                restarted.send_message(self.alice, peer, ident, text)
        with restarted.node(self.alice) as node:
            packets = [json.loads(row['data']) for row in node.db.execute('SELECT data FROM outbox')]
            self.assertEqual(sum(packet.get('kind') == MESSAGE_KIND for packet in packets), 1)

    def test_state_limit_keeps_old_queued_message_and_does_not_delete_history(self):
        ident = secrets.token_hex(32)
        with patch('hosted_runtime.time.time', return_value=1):
            self.runtime.send_message(self.alice, self.bob, ident, 'Still queued')
        key = self.channel_key()
        for i in range(105):
            with patch('hosted_runtime.time.time', return_value=100+i):
                self.runtime.receive(self.alice, self.bob, 'Bearer '+key, self.packet(text=str(i)))
        messages = self.runtime.state(self.alice)['messages']
        self.assertEqual(len(messages), 101)
        self.assertIn(ident, [item['id'] for item in messages])
        self.assertEqual(self.runtime.history(self.alice, self.bob)['total'], 106)

    def test_history_filters_peer_and_completed_clearings_before_limit_and_paginates(self):
        key = self.channel_key()
        for i in range(105):
            with patch('hosted_runtime.time.time', return_value=100+i):
                self.runtime.receive(self.alice, self.bob, 'Bearer '+key, self.packet(text='History '+str(i)))
        with self.runtime.node(self.alice) as node:
            for i in range(300):
                receipt = dict(id=secrets.token_hex(32), status='aborted', decided_at=10000+i,
                               changes=[dict(peer=self.bob, before=1, after=1)])
                node.db.execute('INSERT INTO receipts VALUES(?,?)', (receipt['id'], json.dumps(receipt)))
            for peer, when in ((self.bob, 1000), (self.carol, 2000)):
                receipt = dict(id=secrets.token_hex(32), status='committed', decided_at=when,
                               changes=[dict(peer=peer, before=1, after=0)])
                node.db.execute('INSERT INTO receipts VALUES(?,?)', (receipt['id'], json.dumps(receipt)))
            # A delivery older than the global latest-100 display remains in
            # this peer's durable history rather than being silently omitted.
            for row in list(node.db.execute('SELECT * FROM outbox')):
                data = json.loads(row['data'])
                if data.get('kind') == 'preferences':
                    remote_preferences = data['preferences']
            node.db.execute('UPDATE contacts SET peer_preferences=? WHERE peer=?',
                            (json.dumps(remote_preferences), self.bob))
            delivery = node.propose_obligation(dict(id=secrets.token_hex(32), peer=self.bob,
                       amount=1, direction='i_owe', description='History delivery'))['obligation']
        first = self.runtime.history(self.alice, self.bob)
        second = self.runtime.history(self.alice, self.bob, offset=100)
        self.assertEqual((len(first['entries']), first['has_more'], first['total']), (100, True, 107))
        self.assertEqual((len(second['entries']), second['has_more'], second['total']), (7, False, 107))
        all_entries = first['entries']+second['entries']
        self.assertEqual(len({(item['type'], item['id'], str(item.get('direction'))) for item in all_entries}), 107)
        self.assertEqual({item['type'] for item in all_entries}, {'message', 'delivery', 'clearing'})
        self.assertEqual(sum(item['type'] == 'clearing' for item in all_entries), 1)
        self.assertIn(delivery['id'], [item['id'] for item in all_entries])
        timestamps = [item['timestamp'] for item in all_entries]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))
        for offset in (-1, True, 1.5, '0', 10**9+1):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.runtime.history(self.alice, self.bob, offset)


class HostedMessageGatewayTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.stores = LocalStores(directory.name)
        self.app = create_app(stores=self.stores)
        self.app.testing = True
        self.addCleanup(self.app.extensions['hosted_auth'].db.close)
        self.alice, self.bob, self.carol = (self.enroll(name) for name in ('Alice', 'Bob', 'Carol'))
        invitation = self.post(self.alice, '/api/contacts/invite', {'peer_name':'Bob'})['invite_token']
        self.post(self.bob, '/api/contacts/accept', {'invite_token':invitation})

    def enroll(self, name):
        client = self.app.test_client()
        response = client.post('/auth/demo/start', base_url=ORIGIN, headers={'Origin':ORIGIN},
                               json={'display_name':name})
        self.assertEqual(response.status_code, 200)
        return dict(client=client, **response.get_json())

    def post(self, user, path, body):
        response = user['client'].post(path, base_url=ORIGIN,
                   headers={'Origin':ORIGIN, 'X-CSRF-Token':user['csrf_token']}, json=body)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()

    def test_cookie_csrf_private_alias_and_message_routes(self):
        peer = self.bob['account']['node_id']
        rename_path, messages_path = '/api/contacts/'+peer+'/rename', '/api/contacts/'+peer+'/messages'
        for path, body in ((rename_path, {'name':'Private Bob'}),
                           (messages_path, {'id':secrets.token_hex(32),'text':'Hello'})):
            for client, headers in ((self.app.test_client(), {'Origin':ORIGIN}),
                                    (self.alice['client'], {'Origin':ORIGIN,'X-CSRF-Token':'wrong'}),
                                    (self.alice['client'], {'Origin':'https://evil.example','X-CSRF-Token':self.alice['csrf_token']})):
                response = client.post(path, base_url=ORIGIN, headers=headers, json=body)
                self.assertEqual(response.status_code, 401)
        for path in (messages_path, '/api/contacts/'+peer+'/history'):
            self.assertEqual(self.app.test_client().get(path, base_url=ORIGIN).status_code, 401)
        result = self.post(self.alice, rename_path, {'name':' Private Bob '})
        self.assertEqual(result, dict(ok=True, peer=peer, name='Private Bob'))
        message = self.post(self.alice, messages_path, {'id':secrets.token_hex(32),'text':'Hello'})['message']
        response = self.alice['client'].get(messages_path, base_url=ORIGIN)
        self.assertEqual(response.get_json(), [message])
        history = self.alice['client'].get('/api/contacts/'+peer+'/history', base_url=ORIGIN).get_json()
        self.assertEqual(history['entries'][0], dict(message, type='message', timestamp=message['created_at']))
        state = self.alice['client'].get('/api/state', base_url=ORIGIN).get_json()
        self.assertEqual(state['messages'], [message])
        self.assertEqual(state['contacts'][0]['name'], 'Private Bob')
        remote = self.bob['client'].get('/api/state', base_url=ORIGIN).get_json()
        self.assertEqual(remote['contacts'][0]['name'], 'Alice')
        self.assertEqual(remote['messages'], [])
        self.assertEqual(remote['balances'][0]['balance'], 0)

    def test_route_validation_and_unrelated_account_isolation(self):
        peer = self.bob['account']['node_id']
        for suffix, body in (('rename', {'name':''}), ('rename', {'name':'Bob','node_id':peer}),
                             ('messages', {'id':'invalid','text':'Hello'}),
                             ('messages', {'id':secrets.token_hex(32),'text':'Hello','created_at':0})):
            response = self.alice['client'].post('/api/contacts/'+peer+'/'+suffix, base_url=ORIGIN,
                headers={'Origin':ORIGIN,'X-CSRF-Token':self.alice['csrf_token']}, json=body)
            self.assertEqual(response.status_code, 400)
        for offset in ('-1','1.5','x','1000000001','١'):
            response = self.alice['client'].get('/api/contacts/'+peer+'/history?offset='+offset, base_url=ORIGIN)
            self.assertEqual(response.status_code, 400)
        for user in (self.alice, self.carol):
            own = user['account']['node_id']
            target = own if user is self.alice else peer
            response = user['client'].post('/api/contacts/'+target+'/messages', base_url=ORIGIN,
                headers={'Origin':ORIGIN,'X-CSRF-Token':user['csrf_token']},
                json={'id':secrets.token_hex(32),'text':'Invalid recipient'})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.carol['client'].get('/api/state', base_url=ORIGIN).get_json()['messages'], [])


if __name__ == '__main__':
    unittest.main()
