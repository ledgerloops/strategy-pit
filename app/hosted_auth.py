"""Passkey accounts and opaque browser sessions for the hosted TEST alpha.

Only authentication/account metadata lives here: no node balances, credentials,
hashlocks or clearing decisions. ``db`` is a SQLite-compatible transactional
connection (the hosted adapter persists it to PostgreSQL). All mutating HTTP
routes must pass the exact browser Origin; cookie-authenticated ones also pass
the session CSRF token. The gateway sets the returned session token in a Secure,
HttpOnly, SameSite=Lax, Path=/ __Host-ledgerloops_session cookie, never in JSON.
"""
import base64
import hashlib
import json
import re
import secrets
import threading
import time
from urllib.parse import urlsplit

from webauthn import (generate_registration_options, generate_authentication_options,
                      options_to_json, verify_registration_response,
                      verify_authentication_response)
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria,
                                     ResidentKeyRequirement,
                                     UserVerificationRequirement,
                                     PublicKeyCredentialDescriptor)

COOKIE_NAME = '__Host-ledgerloops_session'
SESSION_SECONDS = 7 * 24 * 60 * 60
CHALLENGE_SECONDS = 5 * 60


class AuthError(ValueError):
    """Public authentication failure; no secrets or verifier internals attached."""


def b64(value):
    return base64.urlsafe_b64encode(value).decode('ascii').rstrip('=')


def unb64(value):
    if not isinstance(value, str) or not value or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise AuthError('Invalid credential encoding')
    try:
        result = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
    except (ValueError, TypeError):
        raise AuthError('Invalid credential encoding') from None
    if b64(result) != value:
        raise AuthError('Invalid credential encoding')
    return result


def digest(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 512:
        raise AuthError('Authentication required')
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class HostedAuth:
    def __init__(self, db, *, origin='https://app.ledgerloops.com', rp_id='app.ledgerloops.com',
                 development=False, now=time.time):
        parsed = urlsplit(origin)
        if (parsed.path or parsed.query or parsed.fragment or parsed.username or
                parsed.password or parsed.hostname != rp_id):
            raise ValueError('Canonical origin must match the passkey relying party')
        if parsed.scheme != 'https' and not (
                development and parsed.scheme == 'http' and rp_id in ('localhost', '127.0.0.1')):
            raise ValueError('HTTPS origin required')
        self.db, self.origin, self.rp_id, self.now = db, origin, rp_id, now
        self.lock = threading.RLock()
        with self.lock, self.db:
            self.db.executescript('''
            CREATE TABLE IF NOT EXISTS auth_accounts(
                id TEXT PRIMARY KEY, node_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL, created INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS auth_credentials(
                id TEXT PRIMARY KEY, account_id TEXT NOT NULL,
                public_key TEXT NOT NULL, sign_count INTEGER NOT NULL,
                created INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS auth_challenges(
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, challenge TEXT NOT NULL,
                context TEXT NOT NULL, expires INTEGER NOT NULL, consumed INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS auth_sessions(
                token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL,
                csrf TEXT NOT NULL, expires INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS auth_recovery(
                code_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL,
                consumed INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS auth_credentials_account ON auth_credentials(account_id);
            CREATE INDEX IF NOT EXISTS auth_sessions_account ON auth_sessions(account_id);
            ''')

    def check_origin(self, origin):
        if origin != self.origin:
            raise AuthError('Origin not allowed')

    def _one(self, sql, args=()):
        cursor = self.db.execute(sql, args)
        row = cursor.fetchone()
        if row is None:
            return None
        return {col[0]: row[index] for index, col in enumerate(cursor.description)}

    def _account(self, account_id):
        account = self._one('SELECT id,node_id,name,created FROM auth_accounts WHERE id=?', (account_id,))
        if account is None:
            raise AuthError('Authentication required')
        return account

    def _session(self, token):
        session = self._one('SELECT account_id,csrf,expires FROM auth_sessions WHERE token_hash=? AND expires>?',
                            (digest(token), int(self.now())))
        if session is None:
            raise AuthError('Authentication required')
        return session

    def session(self, token):
        with self.lock, self.db:
            session = self._session(token)
            return dict(account=self._account(session['account_id']), csrf_token=session['csrf'],
                        expires=session['expires'])

    def _authorized(self, token, csrf_token, origin):
        self.check_origin(origin)
        session = self._session(token)
        if not isinstance(csrf_token, str) or not secrets.compare_digest(session['csrf'], csrf_token):
            raise AuthError('Session CSRF check failed')
        return session

    def authorize(self, token, csrf_token, origin):
        """Authenticate a cookie-authenticated state-changing gateway request."""
        with self.lock, self.db:
            session = self._authorized(token, csrf_token, origin)
            return self._account(session['account_id'])

    def _issue_session(self, account_id):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        expires = int(self.now()) + SESSION_SECONDS
        self.db.execute('INSERT INTO auth_sessions VALUES(?,?,?,?)',
                        (digest(token), account_id, csrf, expires))
        return dict(account=self._account(account_id), session_token=token,
                    csrf_token=csrf, expires=expires)

    def _challenge(self, kind, context):
        ident, challenge = secrets.token_urlsafe(32), secrets.token_bytes(32)
        self.db.execute('DELETE FROM auth_challenges WHERE expires<=?', (int(self.now()),))
        self.db.execute('DELETE FROM auth_sessions WHERE expires<=?', (int(self.now()),))
        self.db.execute('INSERT INTO auth_challenges VALUES(?,?,?,?,?,0)',
                        (ident, kind, b64(challenge), json.dumps(context), int(self.now())+CHALLENGE_SECONDS))
        return ident, challenge

    def _consume_challenge(self, ident, kind):
        # Conditional update prevents successful replay even across worker processes.
        row = self._one('''UPDATE auth_challenges SET consumed=1
            WHERE id=? AND kind=? AND consumed=0 AND expires>?
            RETURNING challenge,context''', (ident, kind, int(self.now())))
        if row is None:
            raise AuthError('Challenge expired or already used; start again')
        return unb64(row['challenge']), json.loads(row['context'])

    def _registration_options(self, account_id, name, challenge):
        credentials = [PublicKeyCredentialDescriptor(id=unb64(row[0])) for row in
                       self.db.execute('SELECT id FROM auth_credentials WHERE account_id=?', (account_id,))]
        options = generate_registration_options(
            rp_id=self.rp_id, rp_name='LedgerLoops TEST alpha', user_id=bytes.fromhex(account_id),
            user_name=name, user_display_name=name, challenge=challenge,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED, require_resident_key=True,
                user_verification=UserVerificationRequirement.REQUIRED),
            exclude_credentials=credentials)
        return json.loads(options_to_json(options))

    def begin_registration(self, display_name, origin):
        self.check_origin(origin)
        if not isinstance(display_name, str) or not 1 <= len(display_name.strip()) <= 80:
            raise AuthError('Choose a display name of 1 to 80 characters')
        name = display_name.strip()
        if any(ord(char) < 32 for char in name):
            raise AuthError('Display name contains control characters')
        with self.lock, self.db:
            account_id = secrets.token_hex(16)
            ident, challenge = self._challenge('register', dict(account_id=account_id, name=name))
            return dict(challenge_id=ident, public_key=self._registration_options(account_id, name, challenge))

    def _verify_registration(self, credential, challenge):
        self._credential_shape(credential)
        try:
            return verify_registration_response(
                credential=credential, expected_challenge=challenge, expected_rp_id=self.rp_id,
                expected_origin=self.origin, require_user_presence=True, require_user_verification=True)
        except Exception:
            raise AuthError('Passkey registration could not be verified') from None

    def _save_credential(self, account_id, verified):
        credential_id = b64(verified.credential_id)
        if self._one('SELECT id FROM auth_credentials WHERE id=?', (credential_id,)):
            raise AuthError('Passkey is already registered')
        self.db.execute('INSERT INTO auth_credentials VALUES(?,?,?,?,?)',
                        (credential_id, account_id, b64(verified.credential_public_key),
                         verified.sign_count, int(self.now())))

    def _new_recovery_codes(self, account_id):
        codes = [secrets.token_urlsafe(24) for _ in range(8)]
        self.db.execute('DELETE FROM auth_recovery WHERE account_id=?', (account_id,))
        for code in codes:
            self.db.execute('INSERT INTO auth_recovery VALUES(?,?,0)', (digest(code), account_id))
        return codes

    def finish_registration(self, challenge_id, credential, origin):
        self.check_origin(origin)
        with self.lock, self.db:
            challenge, context = self._consume_challenge(challenge_id, 'register')
            verified = self._verify_registration(credential, challenge)
            account_id = context['account_id']
            self.db.execute('INSERT INTO auth_accounts VALUES(?,?,?,?)',
                            (account_id, 'n_'+account_id, context['name'], int(self.now())))
            self._save_credential(account_id, verified)
            result = self._issue_session(account_id)
            result['recovery_codes'] = self._new_recovery_codes(account_id)
            return result

    def begin_authentication(self, origin):
        self.check_origin(origin)
        with self.lock, self.db:
            ident, challenge = self._challenge('authenticate', {})
            options = generate_authentication_options(
                rp_id=self.rp_id, challenge=challenge,
                user_verification=UserVerificationRequirement.REQUIRED)
            return dict(challenge_id=ident, public_key=json.loads(options_to_json(options)))

    @staticmethod
    def _credential_shape(credential):
        if not isinstance(credential, dict) or len(json.dumps(credential)) > 32768:
            raise AuthError('Invalid passkey response')
        if not isinstance(credential.get('response'), dict):
            raise AuthError('Invalid passkey response')

    def finish_authentication(self, challenge_id, credential, origin):
        self.check_origin(origin)
        self._credential_shape(credential)
        credential_id = b64(unb64(credential.get('rawId')))
        with self.lock, self.db:
            challenge, _ = self._consume_challenge(challenge_id, 'authenticate')
            stored = self._one('SELECT account_id,public_key,sign_count FROM auth_credentials WHERE id=?',
                               (credential_id,))
            if stored is None:
                raise AuthError('Passkey authentication could not be verified')
            handle = credential['response'].get('userHandle')
            if handle is None or unb64(handle) != bytes.fromhex(stored['account_id']):
                raise AuthError('Passkey account binding could not be verified')
            try:
                verified = verify_authentication_response(
                    credential=credential, expected_challenge=challenge, expected_rp_id=self.rp_id,
                    expected_origin=self.origin, credential_public_key=unb64(stored['public_key']),
                    credential_current_sign_count=stored['sign_count'], require_user_verification=True)
            except Exception:
                raise AuthError('Passkey authentication could not be verified') from None
            updated = self.db.execute('UPDATE auth_credentials SET sign_count=? WHERE id=? AND sign_count=?',
                                     (verified.new_sign_count, credential_id, stored['sign_count']))
            if updated.rowcount != 1:
                raise AuthError('Passkey changed concurrently; start again')
            return self._issue_session(stored['account_id'])

    def begin_add_passkey(self, session_token, csrf_token, origin):
        with self.lock, self.db:
            session = self._authorized(session_token, csrf_token, origin)
            account = self._account(session['account_id'])
            ident, challenge = self._challenge('add-passkey', dict(
                account_id=account['id'], session_hash=digest(session_token)))
            return dict(challenge_id=ident, public_key=self._registration_options(account['id'], account['name'], challenge))

    def finish_add_passkey(self, challenge_id, credential, session_token, csrf_token, origin):
        with self.lock, self.db:
            session = self._authorized(session_token, csrf_token, origin)
            challenge, context = self._consume_challenge(challenge_id, 'add-passkey')
            if context != dict(account_id=session['account_id'], session_hash=digest(session_token)):
                raise AuthError('Passkey enrollment belongs to another session')
            verified = self._verify_registration(credential, challenge)
            self._save_credential(session['account_id'], verified)
            return dict(ok=True, account=self._account(session['account_id']))

    def logout(self, session_token, csrf_token, origin):
        with self.lock, self.db:
            self._authorized(session_token, csrf_token, origin)
            self.db.execute('DELETE FROM auth_sessions WHERE token_hash=?', (digest(session_token),))
            return dict(ok=True)

    def recover(self, account_id, recovery_code, origin):
        """A one-use high-entropy recovery code restores the SAME account/node."""
        self.check_origin(origin)
        with self.lock, self.db:
            recovered = self.db.execute('''UPDATE auth_recovery SET consumed=1
                WHERE account_id=? AND code_hash=? AND consumed=0''', (account_id, digest(recovery_code)))
            if recovered.rowcount != 1:
                raise AuthError('Recovery code could not be verified')
            self.db.execute('DELETE FROM auth_sessions WHERE account_id=?', (account_id,))
            return self._issue_session(account_id)

    def replace_recovery_codes(self, session_token, csrf_token, origin):
        with self.lock, self.db:
            session = self._authorized(session_token, csrf_token, origin)
            return dict(recovery_codes=self._new_recovery_codes(session['account_id']))
