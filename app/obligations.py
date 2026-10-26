"""Bilateral TEST obligations with explicit consent and durable two-party commit.

The proposer consents and reserves on submission. The recipient reserves the exact
quoted edge before showing an approval. Its approval is irrevocable; only the
proposer decides commit, durably with its balance and outgoing commit message.
Reservations never expire: an offline approved peer needs to recover to finish.
"""
import hashlib
import json
import math
import time

from node import MAX_AMOUNT

SCHEME = 'bilateral-obligation-v1'
PROTOCOL = 'private-hashlock-v2'
DESCRIPTION_MAX = 200
TERM_FIELDS = {'scheme', 'protocol', 'unit', 'id', 'origin', 'recipient', 'amount',
               'direction', 'description', 'before', 'after', 'origin_revision',
               'recipient_revision', 'created_at'}


def canonical_id(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def digest_terms(terms):
    return hashlib.sha256(json.dumps(terms, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True).encode('ascii')).hexdigest()


def validate_request(values):
    if set(values) != {'id', 'peer', 'amount', 'direction', 'description'}:
        raise ValueError('Complete obligation id, peer, amount, direction and description required')
    if not canonical_id(values['id']):
        raise ValueError('Obligation id must be 64 lowercase hexadecimal characters')
    if type(values['amount']) is not int or not 0 < values['amount'] <= MAX_AMOUNT:
        raise ValueError('Obligation amount must be a positive bounded integer TEST amount')
    if values['direction'] not in ('i_owe', 'peer_owes'):
        raise ValueError('Obligation direction must be i_owe or peer_owes')
    if not isinstance(values['description'], str) or len(values['description']) > DESCRIPTION_MAX:
        raise ValueError('Obligation description must be at most 200 characters')
    if any(ord(c) < 32 and c not in '\n\t' for c in values['description']):
        raise ValueError('Obligation description contains control characters')
    if not isinstance(values['peer'], str):
        raise ValueError('Direct neighbour required')


class Obligations:
    def initialize_obligations(self):
        if getattr(self.db, 'dialect', None) == 'postgres':
            return  # Release migrations provision native tables.
        self.db.execute('''CREATE TABLE IF NOT EXISTS obligations(
            id TEXT PRIMARY KEY,peer TEXT NOT NULL,data TEXT NOT NULL,digest TEXT NOT NULL,
            status TEXT NOT NULL,origin INTEGER NOT NULL,approved INTEGER NOT NULL,
            applied_at REAL,reason TEXT)''')

    def obligation_row(self, ident):
        row = self.db.execute('SELECT * FROM obligations WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('Unknown obligation')
        return row

    def obligation_view(self, row):
        terms = json.loads(row['data'])
        sign = 1 if row['origin'] else -1
        direction = terms['direction']
        if not row['origin']:
            direction = 'peer_owes' if direction == 'i_owe' else 'i_owe'
        return dict(id=terms['id'], peer=row['peer'], amount=terms['amount'], direction=direction,
                    description=terms['description'], before=sign*terms['before'], after=sign*terms['after'],
                    digest=row['digest'], created_at=terms['created_at'], status=row['status'],
                    origin=bool(row['origin']), approved=bool(row['approved']),
                    applied_at=row['applied_at'], reason=row['reason'], unit='TEST')

    def obligations(self):
        with self.lock:
            return [self.obligation_view(r) for r in self.db.execute(
                """SELECT * FROM obligations WHERE status NOT IN ('committed','aborted')
                   OR rowid IN (SELECT rowid FROM obligations WHERE status IN ('committed','aborted')
                                ORDER BY rowid DESC LIMIT 100) ORDER BY rowid DESC""")]

    @staticmethod
    def obligation_reservation(ident):
        return 'obligation:' + ident

    def obligation_check_edge(self, peer, before, after, own_revision, peer_revision, ident=None):
        if self.paused():
            raise ValueError('Obligations paused')
        row = self.db.execute('SELECT * FROM contacts WHERE peer=?', (peer,)).fetchone()
        own = json.loads(row['own'])
        remote = json.loads(row['peer_preferences']) if row['peer_preferences'] else None
        if remote is None:
            raise ValueError('Peer preferences not synchronized')
        if self.balance(peer) != before or own['revision'] != own_revision or remote['revision'] != peer_revision:
            raise ValueError('Obligation quote is stale; refresh and propose again')
        if not -remote['credit_limit'] <= after <= own['credit_limit'] or abs(after) > MAX_AMOUNT:
            raise ValueError('Obligation exceeds the agreed credit limits')
        reservation = self.db.execute('SELECT proposal FROM reservations WHERE peer=?', (peer,)).fetchone()
        if reservation and (ident is None or reservation[0] != self.obligation_reservation(ident)):
            raise ValueError('Neighbour balance is reserved by another operation')
        if ident and (not reservation or reservation[0] != self.obligation_reservation(ident)):
            raise ValueError('Missing obligation reservation')

    def send_obligation(self, row, action, **extra):
        message = dict(kind='obligation_' + action, protocol=PROTOCOL, id=row['id'], digest=row['digest'])
        if action == 'offer':
            message['terms'] = json.loads(row['data'])
        self.enqueue(row['peer'], dict(message, **extra))

    def propose_obligation(self, values):
        validate_request(values)
        peer, ident = values['peer'], values['id']
        if peer not in self.peers:
            raise ValueError('Unknown direct neighbour')
        with self.lock, self.db:
            existing = self.db.execute('SELECT * FROM obligations WHERE id=?', (ident,)).fetchone()
            if existing:
                terms = json.loads(existing['data'])
                expected = dict(id=ident, peer=existing['peer'], amount=terms['amount'],
                                direction=terms['direction'], description=terms['description'])
                if not existing['origin'] or values != expected:
                    raise ValueError('Obligation id already binds different terms')
                return dict(ok=True, obligation=self.obligation_view(existing))
            row = self.db.execute('SELECT * FROM contacts WHERE peer=?', (peer,)).fetchone()
            own = json.loads(row['own'])
            remote = json.loads(row['peer_preferences']) if row['peer_preferences'] else None
            if remote is None:
                raise ValueError('Peer preferences not synchronized')
            before = self.balance(peer)
            after = before + (-1 if values['direction'] == 'i_owe' else 1)*values['amount']
            self.obligation_check_edge(peer, before, after, own['revision'], remote['revision'])
            terms = dict(scheme=SCHEME, protocol=PROTOCOL, unit='TEST', id=ident, origin=self.name,
                         recipient=peer, amount=values['amount'], direction=values['direction'],
                         description=values['description'], before=before, after=after,
                         origin_revision=own['revision'], recipient_revision=remote['revision'], created_at=time.time())
            self.db.execute('INSERT INTO obligations(id,peer,data,digest,status,origin,approved) VALUES(?,?,?,?,?,1,1)',
                            (ident, peer, json.dumps(terms), digest_terms(terms), 'proposed'))
            self.db.execute('INSERT INTO reservations VALUES(?,?)', (peer, self.obligation_reservation(ident)))
            row = self.obligation_row(ident)
            self.send_obligation(row, 'offer')
            return dict(ok=True, obligation=self.obligation_view(row))

    def approve_obligation(self, ident, digest):
        with self.lock, self.db:
            row = self.obligation_row(ident)
            if not digest or digest != row['digest']:
                raise ValueError('Approval must match displayed obligation digest')
            if row['origin']:
                raise ValueError('Proposer already approved on submission')
            if row['approved']:
                return dict(ok=True, obligation=self.obligation_view(row))
            if row['status'] != 'pending':
                raise ValueError('Obligation is not pending approval')
            terms = json.loads(row['data'])
            self.obligation_check_edge(row['peer'], -terms['before'], -terms['after'],
                                       terms['recipient_revision'], terms['origin_revision'], ident)
            self.db.execute("UPDATE obligations SET status='approved',approved=1 WHERE id=?", (ident,))
            self.send_obligation(self.obligation_row(ident), 'accept')
            return dict(ok=True, obligation=self.obligation_view(self.obligation_row(ident)))

    def decline_obligation(self, ident, digest):
        with self.lock, self.db:
            row = self.obligation_row(ident)
            if not digest or digest != row['digest']:
                raise ValueError('Decline must match displayed obligation digest')
            if row['origin'] or row['approved']:
                raise ValueError('Cannot decline after approving an obligation')
            if row['status'] != 'aborted':
                if row['status'] != 'pending':
                    raise ValueError('Obligation is not pending approval')
                self.abort_obligation(row, 'Declined by counterparty')
                self.send_obligation(self.obligation_row(ident), 'reject', reason='Declined by counterparty')
            return dict(ok=True, obligation=self.obligation_view(self.obligation_row(ident)))

    def abort_obligation(self, row, reason):
        if row['applied_at'] is not None or (not row['origin'] and row['approved']):
            raise ValueError('Cannot abort an irreversible obligation')
        self.db.execute("UPDATE obligations SET status='aborted',reason=? WHERE id=?", (reason, row['id']))
        self.db.execute('DELETE FROM reservations WHERE proposal=?', (self.obligation_reservation(row['id']),))

    def apply_obligation(self, row):
        if row['applied_at'] is not None:
            return
        terms = json.loads(row['data'])
        sign = 1 if row['origin'] else -1
        reservation = self.db.execute('SELECT proposal FROM reservations WHERE peer=?', (row['peer'],)).fetchone()
        if not row['approved'] or not reservation or reservation[0] != self.obligation_reservation(row['id']):
            raise ValueError('Obligation requires local consent and reservation')
        if self.balance(row['peer']) != sign*terms['before']:
            raise ValueError('Reserved obligation balance mismatch')
        self.db.execute('UPDATE balances SET balance=? WHERE peer=?', (sign*terms['after'], row['peer']))
        self.db.execute('UPDATE obligations SET applied_at=? WHERE id=?', (time.time(), row['id']))

    def validate_obligation_offer(self, sender, data):
        terms = data['terms']
        if not isinstance(terms, dict) or set(terms) != TERM_FIELDS:
            raise ValueError('Invalid obligation terms')
        validate_request(dict(id=terms['id'], peer=terms['recipient'], amount=terms['amount'],
                              direction=terms['direction'], description=terms['description']))
        if (terms['scheme'] != SCHEME or terms['protocol'] != PROTOCOL or terms['unit'] != 'TEST'
                or terms['id'] != data['id'] or terms['origin'] != sender or terms['recipient'] != self.name):
            raise ValueError('Obligation identities or protocol mismatch')
        for key in ('before', 'after', 'origin_revision', 'recipient_revision'):
            if type(terms[key]) is not int:
                raise ValueError('Invalid obligation snapshot')
        if max(abs(terms['before']), abs(terms['after'])) > MAX_AMOUNT:
            raise ValueError('Invalid obligation balance')
        if any(not 1 <= terms[key] <= 10**12 for key in ('origin_revision', 'recipient_revision')):
            raise ValueError('Invalid obligation preference revision')
        if (type(terms['created_at']) not in (int, float) or not math.isfinite(terms['created_at'])
                or not 0 < terms['created_at'] < 10**12):
            raise ValueError('Invalid obligation creation time')
        delta = (-1 if terms['direction'] == 'i_owe' else 1)*terms['amount']
        if terms['after'] != terms['before'] + delta or digest_terms(terms) != data['digest']:
            raise ValueError('Obligation terms do not match digest or direction')
        return terms

    def receive_obligation(self, sender, data):
        kind = data.get('kind')
        allowed = {'kind', 'protocol', 'id', 'digest', 'message_id'}
        if kind == 'obligation_offer':
            allowed.add('terms')
        elif kind == 'obligation_reject':
            allowed.add('reason')
        elif kind not in ('obligation_accept', 'obligation_commit', 'obligation_settled'):
            raise ValueError('Unknown obligation message')
        if (set(data) != allowed or data['protocol'] != PROTOCOL or not canonical_id(data['id'])
                or not canonical_id(data['digest']) or not isinstance(data['message_id'], str)
                or not 1 <= len(data['message_id']) <= 128):
            raise ValueError('Invalid obligation envelope')
        if kind == 'obligation_reject' and (not isinstance(data['reason'], str) or len(data['reason']) > 200):
            raise ValueError('Invalid obligation rejection reason')
        terms = self.validate_obligation_offer(sender, data) if kind == 'obligation_offer' else None
        with self.lock, self.db:
            row = self.db.execute('SELECT * FROM obligations WHERE id=?', (data['id'],)).fetchone()
            if row:
                if row['peer'] != sender or row['digest'] != data['digest']:
                    raise ValueError('Obligation sender or digest mismatch')
                if terms is not None and (row['origin'] or json.loads(row['data']) != terms):
                    raise ValueError('Conflicting obligation offer')
                expected_origin = kind in ('obligation_accept', 'obligation_reject', 'obligation_settled')
                if kind != 'obligation_offer' and bool(row['origin']) != expected_origin:
                    raise ValueError('Obligation message has wrong direction')
            elif kind != 'obligation_offer':
                raise ValueError('Unknown obligation')
            if self.db.execute('SELECT 1 FROM inbox WHERE id=?', (data['message_id'],)).fetchone():
                return
            if kind == 'obligation_offer':
                if not row:
                    self.db.execute('INSERT INTO obligations(id,peer,data,digest,status,origin,approved) VALUES(?,?,?,?,?,0,0)',
                                    (data['id'], sender, json.dumps(terms), data['digest'], 'pending'))
                    row = self.obligation_row(data['id'])
                    try:
                        self.obligation_check_edge(sender, -terms['before'], -terms['after'],
                                                   terms['recipient_revision'], terms['origin_revision'])
                    except ValueError as error:
                        self.abort_obligation(row, str(error))
                        self.send_obligation(self.obligation_row(data['id']), 'reject', reason=str(error))
                    else:
                        self.db.execute('INSERT INTO reservations VALUES(?,?)', (sender, self.obligation_reservation(data['id'])))
                # Semantic replays need no new messages: each original outcome is durable in the outbox.
            elif kind == 'obligation_accept':
                if row['status'] == 'proposed':
                    self.apply_obligation(row)
                    self.db.execute("UPDATE obligations SET status='committing' WHERE id=?", (row['id'],))
                    self.send_obligation(row, 'commit')
                elif row['status'] not in ('committing', 'committed'):
                    raise ValueError('Acceptance conflicts with durable obligation decision')
            elif kind == 'obligation_reject':
                if row['status'] not in ('proposed', 'aborted'):
                    raise ValueError('Rejection conflicts with durable obligation decision')
                self.abort_obligation(row, data['reason'])
            elif kind == 'obligation_commit':
                if row['status'] == 'approved':
                    self.apply_obligation(row)
                    self.db.execute("UPDATE obligations SET status='committed' WHERE id=?", (row['id'],))
                    self.db.execute('DELETE FROM reservations WHERE proposal=?', (self.obligation_reservation(row['id']),))
                    self.send_obligation(row, 'settled')
                elif row['status'] != 'committed':
                    raise ValueError('Commit requires exact counterparty approval')
            elif kind == 'obligation_settled':
                if row['status'] not in ('committing', 'committed'):
                    raise ValueError('Unsolicited obligation completion')
                self.db.execute("UPDATE obligations SET status='committed' WHERE id=?", (row['id'],))
                self.db.execute('DELETE FROM reservations WHERE proposal=?', (self.obligation_reservation(row['id']),))
            self.db.execute('INSERT INTO inbox VALUES(?)', (data['message_id'],))
