"""Hosted HTTP/account isolation against real PostgreSQL and real WebAuthn.

Set LEDGERLOOPS_TEST_POSTGRES_DSN to an isolated TEST PostgreSQL database.
Each test uses its own record prefix and removes only those records. The message
transport fixture delivers serialized HTTP envelopes through the Flask gateway;
it does not provide routes or aggregate clearing decisions to participants.
"""
import json
from http.cookiejar import CookieJar
import os
import secrets
import sqlite3
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from flask import request
from werkzeug.serving import WSGIRequestHandler, make_server

from hosted_auth import COOKIE_NAME, DEMO_SESSION_SECONDS
from hosted_server import create_app
from hosted_storage import PgStoreFactory, TABLE
from test_hosted_auth import Authenticator, ORIGIN
from verify_private_receipt import verify


class ScopedStores:
    def __init__(self, factory, prefix):
        self.factory, self.prefix = factory, prefix

    def create(self, key):
        return self.factory.create(self.prefix+key)

    def connection(self, key):
        return self.factory.connection(self.prefix+key)

    def list_nodes(self):
        return [key[len(self.prefix):] for key in self.factory.list_nodes() if key.startswith(self.prefix)]


class HostedDemoGatewayTests(unittest.TestCase):
    """Real HTTP/auth with an isolated auth database; no node provisioning needed."""
    def setUp(self):
        self.env = patch.dict(os.environ)
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop('LEDGERLOOPS_RECOVERY_CODES_ENABLED', None)
        self.db = sqlite3.connect(':memory:', check_same_thread=False)
        self.addCleanup(self.db.close)
        stores = Mock()
        stores.connection.return_value = self.db
        self.app = create_app(stores=stores)
        self.app.testing = True
        self.auth = self.app.extensions['hosted_auth']
        self.client = self.app.test_client()

    def start(self, client=None, name='Alice'):
        return (client or self.client).post('/auth/demo/start', base_url=ORIGIN,
                  headers={'Origin': ORIGIN}, json={'display_name': name})

    def test_demo_sets_year_cookie_and_reuses_browser_identity(self):
        response = self.start()
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertNotIn('session_token', result)
        self.assertNotIn('recovery_codes', result)
        cookie = response.headers['Set-Cookie']
        for attribute in (COOKIE_NAME+'=', 'Secure', 'HttpOnly', 'Path=/', 'SameSite=Lax',
                          'Max-Age='+str(DEMO_SESSION_SECONDS)):
            self.assertIn(attribute, cookie)
        self.assertNotIn('Domain=', cookie)
        repeated = self.start(name='Different').get_json()
        self.assertEqual(repeated['account'], result['account'])
        another = self.start(self.app.test_client()).get_json()
        self.assertNotEqual(another['account']['id'], result['account']['id'])
        bad_csrf = self.client.post('/auth/logout', base_url=ORIGIN,
                   headers={'Origin': ORIGIN, 'X-CSRF-Token': 'wrong'}, json={})
        self.assertEqual(bad_csrf.status_code, 401)
        self.assertEqual(self.start().get_json()['account'], result['account'])

    def test_demo_requires_exact_browser_origin(self):
        for headers in ({}, {'Origin': 'https://evil.example'}):
            response = self.client.post('/auth/demo/start', base_url=ORIGIN,
                                        headers=headers, json={'display_name': 'Alice'})
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.db.execute('SELECT count(*) FROM auth_accounts').fetchone()[0], 0)

    def test_disabled_recovery_routes_do_not_issue_or_consume_codes(self):
        self.auth.recovery_codes_enabled = True
        options = self.auth.begin_registration('Alice', ORIGIN)
        enrolled = self.auth.finish_registration(options['challenge_id'],
                      Authenticator().register(options['public_key']), ORIGIN)
        self.auth.recovery_codes_enabled = False
        before = self.db.execute('SELECT * FROM auth_recovery ORDER BY code_hash').fetchall()
        for route in ('recover', 'recovery/replace'):
            response = self.client.post('/auth/'+route, base_url=ORIGIN,
                       headers={'Origin': ORIGIN}, json={'account_id': enrolled['account']['id'],
                       'recovery_code': enrolled['recovery_codes'][0]})
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.get_json()['error'], 'Recovery codes are disabled')
        self.assertEqual(before, self.db.execute('SELECT * FROM auth_recovery ORDER BY code_hash').fetchall())
        self.assertEqual(self.auth.session(enrolled['session_token'])['account'], enrolled['account'])

    def test_recovery_opt_in_requires_explicit_one(self):
        self.assertFalse(self.auth.recovery_codes_enabled)
        for value in ('0', 'false', 'true', '', '1'):
            with self.subTest(value=value), patch.dict(os.environ, {'LEDGERLOOPS_RECOVERY_CODES_ENABLED': value}):
                stores = Mock()
                stores.connection.return_value = self.db
                app = create_app(stores=stores)
                self.assertEqual(app.extensions['hosted_auth'].recovery_codes_enabled, value == '1')

    def test_invitation_preview_is_public_but_requires_exact_origin(self):
        runtime = self.app.extensions['hosted_runtime']
        with patch.object(runtime, 'preview_invite', create=True, return_value={'inviter_name': 'Alice'}) as preview:
            for headers in ({}, {'Origin': 'https://evil.example'}):
                response = self.client.post('/api/invitations/preview', base_url=ORIGIN,
                                            headers=headers, json={'invite_token': 'opaque-token'})
                self.assertEqual(response.status_code, 403)
            preview.assert_not_called()
            response = self.client.post('/api/invitations/preview', base_url=ORIGIN,
                       headers={'Origin': ORIGIN}, json={'invite_token': 'opaque-token'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {'inviter_name': 'Alice'})
            preview.assert_called_once_with('opaque-token')

    def test_named_invitation_uses_current_cookie_account_and_csrf(self):
        enrolled = self.start().get_json()
        runtime = self.app.extensions['hosted_runtime']
        with patch.object(runtime, 'provision'), patch.object(runtime, 'invite', return_value={'invite_token': 'opaque-token'}) as invite:
            bad = self.client.post('/api/contacts/invite', base_url=ORIGIN,
                  headers={'Origin': ORIGIN, 'X-CSRF-Token': 'wrong'}, json={'peer_name': 'Bob'})
            self.assertEqual(bad.status_code, 401)
            invite.assert_not_called()
            response = self.client.post('/api/contacts/invite', base_url=ORIGIN,
                       headers={'Origin': ORIGIN, 'X-CSRF-Token': enrolled['csrf_token']}, json={'peer_name': 'Bob'})
            self.assertEqual(response.status_code, 200)
            invite.assert_called_once_with(enrolled['account']['node_id'], peer_name='Bob', max_trust=10)

    def test_trust_choices_reach_invite_and_accept_from_current_cookie_account(self):
        enrolled = self.start().get_json()
        runtime = self.app.extensions['hosted_runtime']
        headers = {'Origin': ORIGIN, 'X-CSRF-Token': enrolled['csrf_token']}
        with patch.object(runtime, 'provision'), patch.object(runtime, 'invite', return_value={}) as invite, \
                patch.object(runtime, 'accept_invite', return_value={}) as accept:
            response = self.client.post('/api/contacts/invite', base_url=ORIGIN, headers=headers,
                                       json={'peer_name': 'Bob', 'max_trust': 31})
            self.assertEqual(response.status_code, 200)
            invite.assert_called_once_with(enrolled['account']['node_id'], peer_name='Bob', max_trust=31)
            response = self.client.post('/api/contacts/accept', base_url=ORIGIN, headers=headers,
                                       json={'invite_token': 'opaque-token', 'max_trust': 13})
            self.assertEqual(response.status_code, 200)
            accept.assert_called_once_with(enrolled['account']['node_id'], 'opaque-token', max_trust=13)
            accept.reset_mock()
            response = self.client.post('/api/contacts/accept', base_url=ORIGIN, headers=headers,
                                       json={'invite_token': 'legacy-token'})
            self.assertEqual(response.status_code, 200)
            accept.assert_called_once_with(enrolled['account']['node_id'], 'legacy-token', max_trust=10)


@unittest.skipUnless(os.environ.get('LEDGERLOOPS_TEST_POSTGRES_DSN'),
                     'Set LEDGERLOOPS_TEST_POSTGRES_DSN for real PostgreSQL gateway tests')
class HostedGatewayTests(unittest.TestCase):
    def setUp(self):
        self.factory = PgStoreFactory(os.environ['LEDGERLOOPS_TEST_POSTGRES_DSN'])
        self.factory.initialize()
        self.prefix = 'gateway-test-'+secrets.token_hex(16)+':'
        self.stores = ScopedStores(self.factory, self.prefix)
        self.app = create_app(stores=self.stores)
        self.app.testing = True
        self.runtime = self.app.extensions['hosted_runtime']
        self.auth = self.app.extensions['hosted_auth']
        self.clients = []
        self.transport_client = self.app.test_client(use_cookies=False)
        self.deliveries = []

    def tearDown(self):
        self.auth.db.close()
        with self.factory._pool.connection() as connection:
            connection.execute(f'DELETE FROM {TABLE} WHERE node_id LIKE %s', (self.prefix+'%',))
        self.factory.close()

    def enroll(self, name):
        client = self.app.test_client()
        authn = Authenticator()
        response = client.post('/auth/register/begin', base_url=ORIGIN,
                               headers={'Origin': ORIGIN}, json={'display_name': name})
        self.assertEqual(response.status_code, 200)
        options = response.get_json()
        response = client.post('/auth/register/finish', base_url=ORIGIN, headers={'Origin': ORIGIN},
                               json={'challenge_id': options['challenge_id'],
                                     'credential': authn.register(options['public_key'])})
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertNotIn('session_token', result)
        cookie = response.headers.get('Set-Cookie', '')
        for attribute in (COOKIE_NAME+'=', 'Secure', 'HttpOnly', 'Path=/', 'SameSite=Lax'):
            self.assertIn(attribute, cookie)
        self.assertNotIn('Domain=', cookie)
        user = dict(client=client, authenticator=authn, **result)
        self.clients.append(user)
        response = client.get('/api/session', base_url=ORIGIN)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['account'], result['account'])
        return user

    def get(self, user, path):
        response = user['client'].get(path, base_url=ORIGIN)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()

    def post(self, user, path, body):
        response = user['client'].post(path, base_url=ORIGIN,
                                       headers={'Origin': ORIGIN, 'X-CSRF-Token': user['csrf_token']}, json=body)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()

    def connect(self, first, second):
        invitation = self.post(first, '/api/contacts/invite', {})['invite_token']
        self.post(second, '/api/contacts/accept', {'invite_token': invitation})
        return invitation

    def test_invitation_trust_is_independent_and_invalid_accept_does_not_consume_link(self):
        alice, bob = self.enroll('Alice'), self.enroll('Bob')
        invitation = self.post(alice, '/api/contacts/invite', {'peer_name': 'Bob', 'max_trust': 25})
        for path, body in (('/api/contacts/invite', {'peer_name': 'Bob', 'max_trust': 10**9+1}),
                           ('/api/contacts/accept', {'invite_token': invitation['invite_token'], 'max_trust': True})):
            response = bob['client'].post(path, base_url=ORIGIN,
                headers={'Origin': ORIGIN, 'X-CSRF-Token': bob['csrf_token']}, json=body)
            self.assertEqual(response.status_code, 400)
            self.assertIn('Maximum trust', response.get_json()['error'])
        response = self.app.test_client().post('/api/invitations/preview', base_url=ORIGIN,
                   headers={'Origin': ORIGIN}, json={'invite_token': invitation['invite_token']})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['max_trust'], 25)
        self.post(bob, '/api/contacts/accept', {'invite_token': invitation['invite_token'], 'max_trust': 9})
        self.pump()
        own_alice, own_bob = (self.get(user, '/api/state')['contacts'][0]['own'] for user in (alice, bob))
        self.assertEqual((own_alice['credit_limit'], own_alice['comfort_min'], own_alice['comfort_max']), (25, -25, 12))
        self.assertEqual((own_bob['credit_limit'], own_bob['comfort_min'], own_bob['comfort_max']), (9, -9, 4))
        self.post(bob, '/api/contacts/accept', {'invite_token': invitation['invite_token'], 'max_trust': 100})
        self.assertEqual(self.get(bob, '/api/state')['contacts'][0]['own'], own_bob)

    def deliver(self, request, timeout):
        self.deliveries.append((request.full_url, dict(request.header_items()), json.loads(request.data)))
        response = self.transport_client.post(urlsplit(request.full_url).path,
                                             base_url=ORIGIN, headers=dict(request.header_items()),
                                             data=request.data)
        if response.status_code != 200:
            raise HTTPError(request.full_url, response.status_code, 'Peer rejected envelope', {}, None)

        class Reply:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, limit):
                return response.get_data()[:limit]
        return Reply()

    def pump(self):
        with patch('hosted_runtime.urlopen', self.deliver):
            for _ in range(50):
                for ident in self.runtime.scheduled_nodes():
                    self.runtime.tick(ident)
                pending = sum(self.runtime.state(ident)['outbox_pending'] for ident in self.runtime.scheduled_nodes())
                if pending == 0:
                    return
        self.fail('Peer HTTP envelopes did not quiesce')

    def preferences(self, owner, peer):
        contact = next(c for c in self.get(owner, '/api/state')['contacts'] if c['peer'] == peer['account']['node_id'])
        self.post(owner, '/api/contacts/'+peer['account']['node_id']+'/preferences',
                  dict(credit_limit=10, comfort_min=-10, comfort_max=10, auto_adjust=True,
                       expected_revision=contact['own']['revision']))

    def post_obligation(self, first, second, amount=3):
        proposal = self.post(first, '/api/obligations', dict(
            id=secrets.token_hex(32), peer=second['account']['node_id'], amount=amount,
            direction='i_owe', description='Gateway TEST obligation'))['obligation']
        self.pump()
        pending = next(o for o in self.get(second, '/api/obligations') if o['id'] == proposal['id'])
        self.assertEqual(pending['status'], 'pending')
        self.post(second, '/api/obligations/'+proposal['id']+'/approve', {'digest': pending['digest']})
        self.pump()
        return proposal

    def test_cookie_csrf_canonical_host_and_account_bound_node(self):
        alice, bob = self.enroll('Alice'), self.enroll('Bob')
        for user in (alice, bob):
            state = self.get(user, '/api/state')
            self.assertEqual(state['node'], user['account']['node_id'])
            self.assertTrue(state['operator_access'])
            self.assertEqual(state['balances'], [])
        response = self.app.test_client().get('/api/state', base_url=ORIGIN)
        self.assertEqual(response.status_code, 401)
        response = alice['client'].post('/api/pause', base_url=ORIGIN,
                                         headers={'Origin': ORIGIN}, json={'paused': True})
        self.assertEqual(response.status_code, 401)
        response = alice['client'].post('/api/pause', base_url=ORIGIN,
                                         headers={'Origin': 'https://evil.example', 'X-CSRF-Token': alice['csrf_token']},
                                         json={'paused': True})
        self.assertEqual(response.status_code, 401)
        self.post(alice, '/api/pause', {'paused': True, 'node_id': bob['account']['node_id']})
        self.assertTrue(self.get(alice, '/api/state?node_id='+bob['account']['node_id'])['paused'])
        self.assertFalse(self.get(bob, '/api/state')['paused'])
        response = alice['client'].get('/api/state', base_url='https://evil.example')
        self.assertEqual(response.status_code, 421)

    def test_new_relationship_can_record_event_without_setup_but_needs_peer_approval(self):
        alice, bob = self.enroll('Alice'), self.enroll('Bob')
        self.connect(alice, bob)
        self.pump()
        expected = dict(revision=1, credit_limit=10, comfort_min=-10, comfort_max=5, auto_adjust=True)
        for user in (alice, bob):
            state = self.get(user, '/api/state')
            self.assertTrue(state['automation']['enabled'])
            self.assertEqual(state['contacts'][0]['own'], expected)
            self.assertEqual(state['contacts'][0]['peer_preferences'], expected)
        proposal = self.post(alice, '/api/obligations', dict(
            id=secrets.token_hex(32), peer=bob['account']['node_id'], amount=3,
            direction='i_owe', description='Shared lunch'))['obligation']
        self.pump()
        pending = next(o for o in self.get(bob, '/api/obligations') if o['id'] == proposal['id'])
        self.assertEqual(pending['status'], 'pending')
        for user in (alice, bob):
            self.assertEqual(self.get(user, '/api/state')['balances'][0]['balance'], 0)
        self.post(bob, '/api/obligations/'+proposal['id']+'/approve', {'digest': pending['digest']})
        self.pump()
        self.assertEqual(self.get(alice, '/api/state')['balances'][0]['balance'], -3)
        self.assertEqual(self.get(bob, '/api/state')['balances'][0]['balance'], 3)

    def test_invitation_retry_and_new_invite_preserve_keys_balances_and_local_stores(self):
        alice, bob, carol = self.enroll('Alice'), self.enroll('Bob'), self.enroll('Carol')
        invitation = self.connect(alice, bob)
        self.pump()
        self.preferences(alice, bob)
        self.preferences(bob, alice)
        self.pump()
        self.post_obligation(alice, bob)
        before = self.get(alice, '/api/state')
        with self.runtime.node(alice['account']['node_id']) as node:
            client_token = node.token
            peer_key = node.peers[bob['account']['node_id']]['key']
        self.post(bob, '/api/contacts/accept', {'invite_token': invitation})
        self.connect(alice, bob)
        after = self.get(alice, '/api/state')
        self.assertEqual(before['balances'], after['balances'])
        self.assertEqual(before['contacts'], after['contacts'])
        self.assertEqual(before['obligations'], after['obligations'])
        with self.runtime.node(alice['account']['node_id']) as node:
            self.assertEqual(node.token, client_token)
            self.assertEqual(node.peers[bob['account']['node_id']]['key'], peer_key)
        self.assertNotIn(client_token, json.dumps(after))
        self.assertNotIn(peer_key, json.dumps(after))
        self.assertEqual(self.get(carol, '/api/obligations'), [])
        self.assertEqual(self.get(carol, '/api/state')['balances'], [])
        response = carol['client'].post('/api/contacts/accept', base_url=ORIGIN,
                                        headers={'Origin': ORIGIN, 'X-CSRF-Token': carol['csrf_token']},
                                        json={'invite_token': invitation})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len([key for key in self.stores.list_nodes() if key.startswith('node:')]), 3)

    def test_peer_transport_rejects_browser_identity_and_fake_credentials(self):
        alice, bob = self.enroll('Alice'), self.enroll('Bob')
        self.connect(alice, bob)
        target = '/nodes/'+bob['account']['node_id']+'/peer/message'
        response = alice['client'].post(target, base_url=ORIGIN, headers={
            'Origin': ORIGIN, 'X-Peer-ID': alice['account']['node_id'],
            'Authorization': 'Bearer invalid'}, json={})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.get(bob, '/api/state')['balances'][0]['balance'], 0)
        self.pump()
        self.assertGreater(len(self.deliveries), 0)
        for url, headers, body in self.deliveries:
            self.assertTrue(url.endswith('/peer/message'))
            self.assertNotIn('path', body)
            self.assertNotIn('participants', body)

    def test_simultaneous_crossed_invitations_establish_one_stable_pair_key(self):
        alice, bob = self.enroll('Alice'), self.enroll('Bob')
        first = self.post(alice, '/api/contacts/invite', {})['invite_token']
        second = self.post(bob, '/api/contacts/invite', {})['invite_token']
        barrier = threading.Barrier(2)
        local = threading.local()
        connect = self.runtime._connect_local

        def synchronized_connect(*args):
            initial = not getattr(local, 'connected', False)
            if initial:
                local.connected = True
                barrier.wait(timeout=5)
            connect(*args)
            if initial:
                barrier.wait(timeout=5)

        with patch.object(self.runtime, '_connect_local', synchronized_connect):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(self.runtime.accept_invite, alice['account']['node_id'], second),
                           pool.submit(self.runtime.accept_invite, bob['account']['node_id'], first)]
                for future in futures:
                    self.assertTrue(future.result(timeout=10)['ok'])
        with self.runtime.node(alice['account']['node_id']) as node:
            first_key = node.peers[bob['account']['node_id']]['key']
        with self.runtime.node(bob['account']['node_id']) as node:
            self.assertEqual(node.peers[alice['account']['node_id']]['key'], first_key)
        self.pump()
        self.assertEqual(len(self.get(alice, '/api/state')['contacts']), 1)
        self.assertEqual(len(self.get(bob, '/api/state')['contacts']), 1)

    def test_durable_obligation_and_recovery_keep_same_node(self):
        self.auth.recovery_codes_enabled = True
        alice, bob = self.enroll('Alice'), self.enroll('Bob')
        self.connect(alice, bob)
        self.pump()
        self.preferences(alice, bob)
        self.preferences(bob, alice)
        self.pump()
        proposal = self.post_obligation(alice, bob, 2)
        alice_state, bob_state = self.get(alice, '/api/state'), self.get(bob, '/api/state')
        self.assertEqual(alice_state['balances'][0]['balance'], -2)
        self.assertEqual(bob_state['balances'][0]['balance'], 2)
        for state in (alice_state, bob_state):
            self.assertEqual(state['obligations'][0]['status'], 'committed')
            self.assertIsNotNone(state['obligations'][0]['applied_at'])
        old_client = alice['client']
        recovered_client = self.app.test_client()
        response = recovered_client.post('/auth/recover', base_url=ORIGIN, headers={'Origin': ORIGIN},
                                          json={'account_id': alice['account']['id'],
                                                'recovery_code': alice['recovery_codes'][0]})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('session_token', response.get_json())
        self.assertEqual(response.get_json()['account'], alice['account'])
        self.assertEqual(old_client.get('/api/state', base_url=ORIGIN).status_code, 401)
        state = recovered_client.get('/api/state', base_url=ORIGIN).get_json()
        self.assertEqual(state['balances'], alice_state['balances'])
        self.assertEqual(state['obligations'][0]['id'], proposal['id'])

    def test_three_accounts_real_hashlock_clearing_over_durable_envelopes(self):
        users = [self.enroll(name) for name in ('Alice', 'Bob', 'Carol')]
        # Preserve a separate explicit/manual clearing regression alongside the
        # default background-clearing test below.
        for user in users:
            self.post(user, '/api/automation', {'enabled': False})
        for i, user in enumerate(users):
            self.connect(user, users[(i+1) % 3])
        self.pump()
        for user in users:
            for peer in users:
                if peer is not user:
                    self.preferences(user, peer)
        self.pump()
        for i, user in enumerate(users):
            self.post_obligation(user, users[(i+1) % 3], 1)
        self.post(users[0], '/api/discover', {'mode': 'cancellation', 'amount': 1})
        self.pump()
        for user in users:
            state = self.get(user, '/api/state')
            pending = [proposal for proposal in state['proposals'] if proposal['status'] == 'pending']
            self.assertEqual(len(pending), 1)
            self.post(user, '/api/proposals/'+pending[0]['id']+'/approve', {'digest': pending[0]['digest']})
        self.pump()
        for user in users:
            state = self.get(user, '/api/state')
            self.assertTrue(all(balance['balance'] == 0 for balance in state['balances']))
            self.assertTrue(all(balance['reserved_by'] is None for balance in state['balances']))
            self.assertEqual(len(state['receipts']), 1)
            self.assertEqual(state['outbox_pending'], 0)
            self.assertTrue(all(obligation['status'] == 'committed' for obligation in state['obligations']))

    def test_default_background_headroom_over_real_http_survives_restart_and_duplicates(self):
        """Only invitations/events/confirmations are submitted by the users.

        Genuine HTTP carries every neighbour packet. Independent worker ticks
        find, approve and settle a two-edge chain through its zero-balance link;
        the fixture never calls discover or clearing approval functions/routes.
        """
        class QuietHandler(WSGIRequestHandler):
            def log_request(self, *args, **kwargs):
                pass

        server = make_server('127.0.0.1', 0, None, threaded=True, request_handler=QuietHandler)
        origin = 'http://localhost:'+str(server.server_port)
        wire = []
        apps = []

        def restart():
            app = create_app(stores=self.stores, origin=origin, development=True)

            @app.before_request
            def record_transport():
                if request.path.endswith('/peer/message'):
                    wire.append((request.path, dict(request.headers), request.get_data()))

            apps.append(app)
            server.app = app
            return app.extensions['hosted_runtime']

        runtime = restart()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def stop():
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            for app in apps:
                app.extensions['hosted_auth'].db.close()

        self.addCleanup(stop)

        def call(user, path, body=None):
            headers = {} if body is None else {'Origin': origin, 'Content-Type': 'application/json'}
            if body is not None and user.get('csrf_token'):
                headers['X-CSRF-Token'] = user['csrf_token']
            req = Request(origin+path, headers=headers,
                          data=None if body is None else json.dumps(body).encode())
            with user['http'].open(req, timeout=5) as response:
                return json.load(response)

        users = []
        for name in ('HTTP Alice', 'HTTP Bob', 'HTTP Carol'):
            jar = CookieJar()
            user = dict(http=build_opener(HTTPCookieProcessor(jar)))
            user.update(call(user, '/auth/demo/start', {'display_name': name}))
            # Browsers treat localhost as a secure context; urllib's cookie jar
            # does not. Allow this isolated loopback fixture to return its cookie.
            for cookie in jar:
                cookie.secure = False
            users.append(user)
        alice, bob, carol = users
        for first, second in ((alice, bob), (bob, carol), (carol, alice)):
            invitation = call(first, '/api/contacts/invite', {'peer_name': second['account']['name']})
            call(second, '/api/contacts/accept', {'invite_token': invitation['invite_token']})

        def states():
            return [call(user, '/api/state') for user in users]

        def wake_until(predicate, description):
            deadline = time.monotonic()+30
            while time.monotonic() < deadline:
                for node_id in runtime.scheduled_nodes():
                    runtime.tick(node_id)
                current = states()
                if predicate(current):
                    return current
                time.sleep(.02)
            self.fail(description)

        wake_until(lambda rows: all(all(c['peer_preferences'] for c in row['contacts']) for row in rows),
                   'Default preferences did not synchronize')
        for row in states():
            self.assertTrue(row['automation']['enabled'])
            self.assertTrue(all(c['own']['auto_adjust'] and c['peer_preferences']['auto_adjust'] for c in row['contacts']))

        def event(first, second):
            proposed = call(first, '/api/obligations', dict(id=secrets.token_hex(32),
                peer=second['account']['node_id'], amount=1, direction='i_owe', description='HTTP TEST event'))['obligation']
            current = wake_until(lambda rows: any(any(e['id'] == proposed['id'] and e['status'] == 'pending'
                                    for e in row['obligations']) for row in rows), 'Event did not arrive')
            # Background clearing consent must never confirm a new economic event.
            for _ in range(4):
                for node_id in runtime.scheduled_nodes():
                    runtime.tick(node_id)
            pending = next(e for e in call(second, '/api/obligations') if e['id'] == proposed['id'])
            self.assertEqual(pending['status'], 'pending')
            call(second, '/api/obligations/'+proposed['id']+'/approve', {'digest': pending['digest']})
            return wake_until(lambda rows: all(all(e['status'] == 'committed' for e in row['obligations']) for row in rows),
                              'Confirmed economic event did not commit')

        event(alice, bob)
        # Reload node/auth gateways against the same PostgreSQL stores before
        # the second event. Browser cookies, channel keys and first event persist.
        baseline = states()
        runtime = restart()
        self.assertEqual([row['balances'] for row in states()], [row['balances'] for row in baseline])
        event(bob, carol)
        result = wake_until(lambda rows: all(any(r['status'] == 'committed' for r in row['receipts']) and row['outbox_pending'] == 0 and
                        all(c['reserved_by'] is None for c in row['contacts']) for row in rows),
                            'Background headroom clearing did not settle')
        self.assertEqual(sum(abs(b['balance']) for row in result for b in row['balances'])//2, 1)
        self.assertTrue(all(b['balance'] == 0 for b in result[1]['balances']))
        self.assertEqual({row['node']: sum(b['balance'] for b in row['balances']) for row in result},
                         {alice['account']['node_id']: -1, bob['account']['node_id']: 0, carol['account']['node_id']: 1})
        for row in result:
            self.assertTrue(any(receipt['status'] == 'committed' for receipt in row['receipts']))
            self.assertTrue(all(verify(receipt)['valid'] for receipt in row['receipts'] if receipt['status'] == 'committed'))
        # Repeated deliveries of already applied envelopes cannot post twice.
        for path, headers, body in list(wire):
            with urlopen(Request(origin+path, headers=headers, data=body), timeout=5) as response:
                self.assertEqual(response.status, 200)
        runtime = restart()
        after = states()
        self.assertEqual([row['balances'] for row in after], [row['balances'] for row in result])
        self.assertEqual([row['receipts'] for row in after], [row['receipts'] for row in result])
        self.assertTrue(all(row['automation']['enabled'] for row in after))


if __name__ == '__main__':
    unittest.main()
