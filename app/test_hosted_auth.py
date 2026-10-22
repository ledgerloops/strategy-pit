"""Real WebAuthn cryptography and session lifecycle tests; isolated TEST accounts."""
from copy import deepcopy
import hashlib
import json
import secrets
import sqlite3
import tempfile
import unittest

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from hosted_auth import HostedAuth, AuthError, b64, unb64, SESSION_SECONDS

ORIGIN = 'https://app.ledgerloops.com'
RP_ID = 'app.ledgerloops.com'


class Authenticator:
    """Minimal P-256 authenticator fixture; server verifier is never mocked."""
    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = secrets.token_bytes(32)
        self.user_id = None
        self.count = 0

    def register(self, options, *, origin=ORIGIN, rp_id=RP_ID, verified=True):
        self.user_id = options['user']['id']
        public = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1,
                            -2: public.x.to_bytes(32, 'big'), -3: public.y.to_bytes(32, 'big')})
        flags = 0x41 | (0x04 if verified else 0)
        auth_data = (hashlib.sha256(rp_id.encode()).digest() + bytes([flags]) + bytes(4)
                     + bytes(16) + len(self.credential_id).to_bytes(2, 'big') + self.credential_id + cose)
        client = json.dumps(dict(type='webauthn.create', challenge=options['challenge'],
                                 origin=origin, crossOrigin=False), separators=(',', ':')).encode()
        return dict(id=b64(self.credential_id), rawId=b64(self.credential_id), type='public-key',
                    response=dict(clientDataJSON=b64(client),
                                  attestationObject=b64(cbor2.dumps(dict(fmt='none', attStmt={}, authData=auth_data)))),
                    clientExtensionResults={})

    def authenticate(self, options, *, origin=ORIGIN, rp_id=RP_ID, verified=True):
        self.count += 1
        client = json.dumps(dict(type='webauthn.get', challenge=options['challenge'],
                                 origin=origin, crossOrigin=False), separators=(',', ':')).encode()
        flags = 0x01 | (0x04 if verified else 0)
        auth_data = hashlib.sha256(rp_id.encode()).digest() + bytes([flags]) + self.count.to_bytes(4, 'big')
        signature = self.key.sign(auth_data + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        return dict(id=b64(self.credential_id), rawId=b64(self.credential_id), type='public-key',
                    response=dict(clientDataJSON=b64(client), authenticatorData=b64(auth_data),
                                  signature=b64(signature), userHandle=self.user_id), clientExtensionResults={})


class HostedAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = self.temp.name + '/auth.sqlite'
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.clock = [100000]
        self.auth = HostedAuth(self.db, now=lambda: self.clock[0])

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def enroll(self, name='Alice'):
        authenticator = Authenticator()
        options = self.auth.begin_registration(name, ORIGIN)
        result = self.auth.finish_registration(options['challenge_id'],
                                             authenticator.register(options['public_key']), ORIGIN)
        return authenticator, result

    def test_real_enrollment_login_and_stable_node_after_restart(self):
        authenticator, enrolled = self.enroll()
        account_id = enrolled['account']['id']
        self.assertEqual(enrolled['account']['node_id'], 'n_'+account_id)
        self.assertEqual(len(enrolled['recovery_codes']), 8)
        self.db.close()
        self.db = sqlite3.connect(self.path)
        self.auth = HostedAuth(self.db, now=lambda: self.clock[0])
        self.assertEqual(self.auth.session(enrolled['session_token'])['account']['id'], account_id)
        options = self.auth.begin_authentication(ORIGIN)
        login = self.auth.finish_authentication(options['challenge_id'],
                                              authenticator.authenticate(options['public_key']), ORIGIN)
        self.assertEqual(login['account'], enrolled['account'])
        self.assertNotEqual(login['session_token'], enrolled['session_token'])
        self.assertEqual(self.auth.authorize(login['session_token'], login['csrf_token'], ORIGIN)['id'], account_id)

    def test_successful_challenges_cannot_be_replayed(self):
        authenticator = Authenticator()
        options = self.auth.begin_registration('Alice', ORIGIN)
        credential = authenticator.register(options['public_key'])
        self.auth.finish_registration(options['challenge_id'], credential, ORIGIN)
        with self.assertRaises(AuthError):
            self.auth.finish_registration(options['challenge_id'], credential, ORIGIN)
        options = self.auth.begin_authentication(ORIGIN)
        credential = authenticator.authenticate(options['public_key'])
        self.auth.finish_authentication(options['challenge_id'], credential, ORIGIN)
        with self.assertRaises(AuthError):
            self.auth.finish_authentication(options['challenge_id'], credential, ORIGIN)

    def test_origin_rp_and_user_verification_are_enforced_by_real_verifier(self):
        for overrides in (dict(origin='https://evil.example'), dict(rp_id='evil.example'), dict(verified=False)):
            with self.subTest(overrides=overrides):
                options = self.auth.begin_registration('Alice', ORIGIN)
                credential = Authenticator().register(options['public_key'], **overrides)
                with self.assertRaises(AuthError):
                    self.auth.finish_registration(options['challenge_id'], credential, ORIGIN)
        self.assertEqual(self.db.execute('SELECT count(*) FROM auth_accounts').fetchone()[0], 0)
        authenticator, _ = self.enroll()
        for overrides in (dict(origin='https://evil.example'), dict(rp_id='evil.example'), dict(verified=False)):
            with self.subTest(overrides=overrides):
                options = self.auth.begin_authentication(ORIGIN)
                credential = authenticator.authenticate(options['public_key'], **overrides)
                with self.assertRaises(AuthError):
                    self.auth.finish_authentication(options['challenge_id'], credential, ORIGIN)

    def test_signature_challenge_and_account_binding_cannot_be_forged(self):
        authenticator, _ = self.enroll()
        for mutation in ('signature', 'userHandle', 'challenge'):
            options = self.auth.begin_authentication(ORIGIN)
            credential = authenticator.authenticate(options['public_key'])
            if mutation == 'signature':
                credential['response']['signature'] = b64(bytes(64))
            elif mutation == 'userHandle':
                credential['response']['userHandle'] = b64(secrets.token_bytes(16))
            else:
                options = self.auth.begin_authentication(ORIGIN)
            with self.assertRaises(AuthError):
                self.auth.finish_authentication(options['challenge_id'], credential, ORIGIN)

    def test_cookie_possession_needs_csrf_and_exact_origin_for_writes(self):
        _, enrolled = self.enroll()
        for csrf, origin in ((None, ORIGIN), ('bad', ORIGIN), (enrolled['csrf_token'], None),
                             (enrolled['csrf_token'], 'https://app.ledgerloops.com.evil.example')):
            with self.assertRaises(AuthError):
                self.auth.authorize(enrolled['session_token'], csrf, origin)
        with self.assertRaises(AuthError):
            self.auth.begin_authentication('https://evil.example')
        self.auth.logout(enrolled['session_token'], enrolled['csrf_token'], ORIGIN)
        with self.assertRaises(AuthError):
            self.auth.session(enrolled['session_token'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM auth_accounts').fetchone()[0], 1)

    def test_expiry_and_raw_session_tokens_not_stored(self):
        _, enrolled = self.enroll()
        stored = self.db.execute('SELECT token_hash FROM auth_sessions').fetchone()[0]
        self.assertNotEqual(stored, enrolled['session_token'])
        stored_codes = [row[0] for row in self.db.execute('SELECT code_hash FROM auth_recovery')]
        self.assertTrue(set(stored_codes).isdisjoint(enrolled['recovery_codes']))
        options = self.auth.begin_registration('Expired', ORIGIN)
        credential = Authenticator().register(options['public_key'])
        self.clock[0] += 301
        with self.assertRaises(AuthError):
            self.auth.finish_registration(options['challenge_id'], credential, ORIGIN)
        self.clock[0] += SESSION_SECONDS
        with self.assertRaises(AuthError):
            self.auth.session(enrolled['session_token'])

    def test_add_second_passkey_requires_same_session_and_preserves_identity(self):
        _, enrolled = self.enroll()
        _, other = self.enroll('Bob')
        options = self.auth.begin_add_passkey(enrolled['session_token'], enrolled['csrf_token'], ORIGIN)
        second = Authenticator()
        credential = second.register(options['public_key'])
        with self.assertRaises(AuthError):
            self.auth.finish_add_passkey(options['challenge_id'], credential,
                                        other['session_token'], other['csrf_token'], ORIGIN)
        self.auth.finish_add_passkey(options['challenge_id'], credential,
                                    enrolled['session_token'], enrolled['csrf_token'], ORIGIN)
        options = self.auth.begin_authentication(ORIGIN)
        logged_in = self.auth.finish_authentication(options['challenge_id'], second.authenticate(options['public_key']), ORIGIN)
        self.assertEqual(logged_in['account']['node_id'], enrolled['account']['node_id'])

    def test_recovery_is_one_use_revokes_sessions_and_preserves_node(self):
        _, enrolled = self.enroll()
        _, other = self.enroll('Bob')
        account_id, code = enrolled['account']['id'], enrolled['recovery_codes'][0]
        with self.assertRaises(AuthError):
            self.auth.recover(other['account']['id'], code, ORIGIN)
        recovered = self.auth.recover(account_id, code, ORIGIN)
        self.assertEqual(recovered['account'], enrolled['account'])
        with self.assertRaises(AuthError):
            self.auth.session(enrolled['session_token'])
        with self.assertRaises(AuthError):
            self.auth.recover(account_id, code, ORIGIN)
        replacement = self.auth.replace_recovery_codes(recovered['session_token'], recovered['csrf_token'], ORIGIN)
        with self.assertRaises(AuthError):
            self.auth.recover(account_id, enrolled['recovery_codes'][1], ORIGIN)
        self.auth.recover(account_id, replacement['recovery_codes'][0], ORIGIN)

    def test_counter_reuse_rejected_with_fresh_challenge(self):
        authenticator, _ = self.enroll()
        options = self.auth.begin_authentication(ORIGIN)
        self.auth.finish_authentication(options['challenge_id'], authenticator.authenticate(options['public_key']), ORIGIN)
        authenticator.count = 0
        options = self.auth.begin_authentication(ORIGIN)
        with self.assertRaises(AuthError):
            self.auth.finish_authentication(options['challenge_id'], authenticator.authenticate(options['public_key']), ORIGIN)

    def test_config_rejects_wrong_rp_or_insecure_public_origin(self):
        for values in (dict(origin='https://evil.example'), dict(origin='http://app.ledgerloops.com'),
                       dict(origin=ORIGIN+'/path')):
            with self.assertRaises(ValueError):
                HostedAuth(self.db, **values)


if __name__ == '__main__':
    unittest.main()
