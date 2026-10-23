"""Hosted infrastructure around independent local TEST node state machines.

The registry schedules nodes but never chooses a route or evaluates a cycle.
Each node operation has one fixed-key durable store. Delivery leaves the local
transaction before contacting a peer, and the peer commits separately.
"""
from contextlib import contextmanager
import hashlib
import hmac
import json
import re
import secrets
import time
import unicodedata
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from private_node import Node, PROTOCOL
from headroom_policy import edge_allowed as headroom_edge_allowed

NODE_ID = re.compile(r'n_[0-9a-f]{32}\Z')
MAX_TRUST = 10**9
MESSAGE_PROTOCOL = 'hosted-message-v1'
MESSAGE_KIND = 'hosted_message'
SEARCH_RETRY_MAX = 300


class HostedRuntime:
    def __init__(self, stores, origin):
        self.stores, self.origin = stores, origin.rstrip('/')

    @staticmethod
    def key(node_id):
        if not isinstance(node_id, str) or not NODE_ID.fullmatch(node_id):
            raise ValueError('Invalid node identity')
        return 'node:'+node_id

    def provision(self, account):
        """Idempotent provisioning only, never reset credentials or balances."""
        key = self.key(account['node_id'])
        self.stores.create(key)
        db = self.stores.connection(key)
        try:
            with db:
                tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                previous = db.execute("SELECT v FROM meta WHERE k='hosted_config'").fetchone() if 'meta' in tables else None
                if previous:
                    self._invite_schema(db)
                    return
                config = dict(node=account['node_id'], token=secrets.token_urlsafe(32),
                              mode='testnet', peers={}, label=account['name'])
                node = Node(config, ':memory:', connection=db)
                db.execute("INSERT INTO meta VALUES('hosted_config',?)", (json.dumps(config),))
                db.execute("INSERT INTO meta VALUES('hosted_automation','true')")
                db.execute("INSERT INTO meta VALUES('hosted_automatic_clearing_v1','[]')")
                self._invite_schema(db)
                node.stopped.set()
        finally:
            db.close()

    @staticmethod
    def _invite_schema(db):
        """Add invitation metadata without replacing provisioned node state."""
        db.execute('''CREATE TABLE IF NOT EXISTS hosted_invites(
            token_hash TEXT PRIMARY KEY,expires REAL NOT NULL,
            accepted_by TEXT,peer_key TEXT,peer_name TEXT NOT NULL DEFAULT '')''')
        columns = {row[1] for row in db.execute('PRAGMA table_info(hosted_invites)')}
        if 'peer_name' not in columns:
            db.execute("ALTER TABLE hosted_invites ADD COLUMN peer_name TEXT NOT NULL DEFAULT ''")
        if 'max_trust' not in columns:
            db.execute('ALTER TABLE hosted_invites ADD COLUMN max_trust INTEGER NOT NULL DEFAULT 10')
        if 'accepted_max_trust' not in columns:
            db.execute('ALTER TABLE hosted_invites ADD COLUMN accepted_max_trust INTEGER')

    @staticmethod
    def _message_schema(db):
        db.execute('''CREATE TABLE IF NOT EXISTS hosted_messages(
            id TEXT NOT NULL,peer TEXT NOT NULL,direction TEXT NOT NULL,text TEXT NOT NULL,
            status TEXT NOT NULL,created_at REAL NOT NULL,sent_at REAL,received_at REAL,
            delivered_at REAL,PRIMARY KEY(peer,id,direction))''')
        db.execute('CREATE INDEX IF NOT EXISTS hosted_messages_peer_time ON hosted_messages(peer,created_at)')

    @staticmethod
    def _automatic_clearing_defaults(node):
        """One hosted TEST policy upgrade, respecting later explicit opt-outs.

        Only untouched revision-one assistance defaults are upgraded. Limits,
        comfort, balances, pauses and proposal digests remain unchanged. A
        reserved edge retains its exact quoted revision until its protocol
        finishes; the durable pending list retries that upgrade on later wakes.
        """
        marker = node.db.execute("SELECT v FROM meta WHERE k='hosted_automatic_clearing_v1'").fetchone()
        if marker:
            pending = json.loads(marker[0])
            if not pending:
                return
        else:
            pending = []
            for row in node.db.execute('SELECT peer,own FROM contacts'):
                own = json.loads(row['own'])
                if own in (dict(revision=1, credit_limit=0, comfort_min=0, comfort_max=0, auto_adjust=False),
                           dict(revision=1, credit_limit=10, comfort_min=-10, comfort_max=10, auto_adjust=False)):
                    pending.append(row['peer'])
            # The demo's newly requested policy replaces its old node-wide
            # default once. Subsequent explicit automation=false is retained.
            node.db.execute("INSERT OR REPLACE INTO meta VALUES('hosted_automation','true')")
        deferred = []
        for peer in pending:
            row = node.db.execute('SELECT own FROM contacts WHERE peer=?', (peer,)).fetchone()
            if not row:
                continue
            own = json.loads(row[0])
            if own['revision'] != 1 or own['auto_adjust']:
                continue
            if node.db.execute('SELECT 1 FROM reservations WHERE peer=?', (peer,)).fetchone():
                deferred.append(peer)
                continue
            node.set_preferences(peer, dict(own, expected_revision=own['revision'], auto_adjust=True))
        value = json.dumps(deferred)
        if not marker or marker[0] != value:
            node.db.execute("INSERT OR REPLACE INTO meta VALUES('hosted_automatic_clearing_v1',?)", (value,))

    @contextmanager
    def node(self, node_id):
        db = self.stores.connection(self.key(node_id))
        try:
            # Constructor + operation are one local transaction. No peer store is
            # opened while this context is active.
            with db:
                row = db.execute("SELECT v FROM meta WHERE k='hosted_config'").fetchone()
                if not row:
                    raise ValueError('Node not provisioned')
                n = Node(json.loads(row[0]), ':memory:', connection=db)
                try:
                    self._invite_schema(db)
                    self._message_schema(db)
                    self._automatic_clearing_defaults(n)
                    yield n
                finally:
                    n.stopped.set()
        finally:
            db.close()

    def state(self, node_id):
        with self.node(node_id) as node:
            state = node.state()
            # The older comfort mode optimizes discomfort and can increase debt.
            # Keep it available for legacy local demos, not this hosted product.
            state['discovery_modes'] = [m for m in state['discovery_modes'] if m in ('cancellation','headroom')]
            enabled = node.db.execute("SELECT v FROM meta WHERE k='hosted_automation'").fetchone()
            state['automation'] = dict(enabled=bool(enabled and enabled[0] == 'true'))
            state['hosted'] = True
            state['operator_access'] = True
            state['messages'] = self._messages(node)
            for contact in state['contacts']:
                contact['name'] = node.peers[contact['peer']].get('name', '')
            return state

    def automation(self, node_id, enabled):
        if type(enabled) is not bool:
            raise ValueError('enabled must be boolean')
        with self.node(node_id) as node:
            node.db.execute("INSERT OR REPLACE INTO meta VALUES('hosted_automation',?)", ('true' if enabled else 'false',))
        return dict(enabled=enabled)

    @staticmethod
    def _max_trust(value):
        if type(value) is not int or not 0 <= value <= MAX_TRUST:
            raise ValueError('Maximum trust must be a whole TEST amount between 0 and 1000000000')
        return value

    def invite(self, node_id, peer_name='', max_trust=10):
        max_trust = self._max_trust(max_trust)
        if (not isinstance(peer_name, str) or len(peer_name) > 80 or
                any(unicodedata.category(char) in ('Cc', 'Cf', 'Cs') for char in peer_name)):
            raise ValueError('Peer name must be at most 80 characters without control characters')
        peer_name = peer_name.strip()
        token = secrets.token_urlsafe(32)
        expires = time.time()+24*60*60
        with self.node(node_id) as node:
            config = json.loads(node.db.execute("SELECT v FROM meta WHERE k='hosted_config'").fetchone()[0])
            node.db.execute('DELETE FROM hosted_invites WHERE expires<? AND accepted_by IS NULL', (time.time(),))
            node.db.execute('INSERT INTO hosted_invites(token_hash,expires,peer_name,max_trust) VALUES(?,?,?,?)',
                            (hashlib.sha256(token.encode()).hexdigest(), expires, peer_name, max_trust))
        invitation = node_id+'.'+token
        return dict(invite_token=invitation, expires_at=expires, inviter_name=config.get('label', ''),
                    peer_name=peer_name, max_trust=max_trust,
                    invite_url=self.origin+'/#invite='+quote(invitation, safe=''))

    def _invitation(self, invitation):
        if not isinstance(invitation, str) or len(invitation) > 200 or '.' not in invitation:
            raise ValueError('Invalid invitation')
        issuer, token = invitation.split('.', 1)
        self.key(issuer)
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise ValueError('Invalid invitation')
        return issuer, hashlib.sha256(token.encode()).hexdigest()

    def preview_invite(self, invitation):
        """Only names, offered trust and expiry reach an unused invite bearer."""
        issuer, token_hash = self._invitation(invitation)
        with self.node(issuer) as node:
            row = node.db.execute('SELECT expires,accepted_by,peer_name,max_trust FROM hosted_invites WHERE token_hash=?',
                                  (token_hash,)).fetchone()
            if not row or row['accepted_by'] is not None or row['expires'] < time.time():
                raise ValueError('Invitation expired or unavailable')
            config = json.loads(node.db.execute("SELECT v FROM meta WHERE k='hosted_config'").fetchone()[0])
            return dict(inviter_name=config.get('label', ''), peer_name=row['peer_name'],
                        max_trust=row['max_trust'], expires_at=row['expires'])

    def _connect_local(self, node_id, peer, key, max_trust=10):
        """Enrollment is a separate local action at each endpoint, at zero debt."""
        with self.node(node_id) as node:
            config = json.loads(node.db.execute("SELECT v FROM meta WHERE k='hosted_config'").fetchone()[0])
            if peer in config['peers']:
                if not hmac.compare_digest(config['peers'][peer]['key'], key):
                    raise ValueError('Relationship already exists; its key will not be rotated')
                return
            config['peers'][peer] = dict(url=self.origin+'/nodes/'+peer, key=key, balance=0)
            node.peers[peer] = config['peers'][peer]
            node.db.execute('INSERT INTO balances VALUES(?,0)', (peer,))
            # Positive balance means this peer owes us. Round the half bound
            # down: whole TEST balances <= MAX/2 are exactly those <= MAX//2.
            own = dict(revision=1, credit_limit=max_trust, comfort_min=-max_trust,
                       comfort_max=max_trust//2, auto_adjust=True)
            node.db.execute('INSERT INTO contacts VALUES(?,?,NULL)', (peer,json.dumps(own)))
            node.enqueue(peer, dict(kind='preferences',protocol=PROTOCOL,preferences=own))
            node.db.execute("UPDATE meta SET v=? WHERE k='hosted_config'", (json.dumps(config),))

    def _name_local(self, node_id, peer, name):
        # Display metadata only; never replaces an established private label.
        if not name:
            return
        with self.node(node_id) as node:
            config = json.loads(node.db.execute("SELECT v FROM meta WHERE k='hosted_config'").fetchone()[0])
            if not config['peers'][peer].get('name'):
                config['peers'][peer]['name'] = name
                node.db.execute("UPDATE meta SET v=? WHERE k='hosted_config'", (json.dumps(config),))

    @staticmethod
    def _direct_peer(node, peer):
        if not isinstance(peer, str) or peer == node.name or peer not in node.peers:
            raise ValueError('Choose an existing direct peer')

    def rename(self, node_id, peer, name):
        if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or
                any(unicodedata.category(char) in ('Cc', 'Cf', 'Cs') for char in name)):
            raise ValueError('Peer name must be 1 to 80 characters without control characters')
        name = name.strip()
        with self.node(node_id) as node:
            self._direct_peer(node, peer)
            config = json.loads(node.db.execute("SELECT v FROM meta WHERE k='hosted_config'").fetchone()[0])
            config['peers'][peer]['name'] = name
            node.db.execute("UPDATE meta SET v=? WHERE k='hosted_config'", (json.dumps(config),))
        return dict(ok=True, peer=peer, name=name)

    @staticmethod
    def _message_values(ident, text):
        if not isinstance(ident, str) or not re.fullmatch(r'[0-9a-f]{64}', ident):
            raise ValueError('Message id must be 64 lowercase hexadecimal characters')
        if (not isinstance(text, str) or not 1 <= len(text) <= 2000 or not text.strip() or
                any(unicodedata.category(char) in ('Cc', 'Cf', 'Cs') and char not in '\n\t\u200c\u200d'
                    for char in text)):
            raise ValueError('Message must be 1 to 2000 characters without unsupported control characters')
        return ident, text.strip()

    @staticmethod
    def _messages(node, peer=None):
        where, values = (' WHERE peer=?', (peer,)) if peer is not None else ('', ())
        # Keep every unresolved send visible, even when more than 100 newer
        # received/delivered messages exist. This is a display cap, not deletion.
        query = f'''SELECT * FROM hosted_messages {where} AND status='queued' ''' if where else "SELECT * FROM hosted_messages WHERE status='queued' "
        query += f'''UNION SELECT * FROM (SELECT * FROM hosted_messages {where}
                    ORDER BY created_at DESC,id DESC,direction DESC LIMIT 100)
                    ORDER BY created_at DESC,id DESC,direction DESC'''
        return [dict(row) for row in node.db.execute(query, values+values)]

    def messages(self, node_id, peer):
        with self.node(node_id) as node:
            self._direct_peer(node, peer)
            return self._messages(node, peer)

    def send_message(self, node_id, peer, ident, text):
        ident, text = self._message_values(ident, text)
        with self.node(node_id) as node:
            self._direct_peer(node, peer)
            previous = node.db.execute("SELECT * FROM hosted_messages WHERE id=? AND direction='outgoing'", (ident,)).fetchone()
            if previous:
                if previous['peer'] != peer or previous['text'] != text:
                    raise ValueError('Message id already binds different terms')
                return dict(ok=True, message=dict(previous))
            now = time.time()
            node.db.execute('''INSERT INTO hosted_messages
                (id,peer,direction,text,status,created_at,sent_at) VALUES(?,?,'outgoing',?,'queued',?,?)''',
                (ident, peer, text, now, now))
            node.enqueue(peer, dict(kind=MESSAGE_KIND, protocol=MESSAGE_PROTOCOL, id=ident, text=text))
            row = node.db.execute("SELECT * FROM hosted_messages WHERE peer=? AND id=? AND direction='outgoing'", (peer, ident)).fetchone()
            return dict(ok=True, message=dict(row))

    def _receive_message(self, node, sender, data):
        if (set(data) != {'kind', 'protocol', 'id', 'text', 'message_id'} or
                data['protocol'] != MESSAGE_PROTOCOL or not isinstance(data['message_id'], str) or
                not re.fullmatch(r'[0-9a-f]{32}', data['message_id'])):
            raise ValueError('Invalid hosted message envelope')
        ident, text = self._message_values(data['id'], data['text'])
        previous = node.db.execute("SELECT * FROM hosted_messages WHERE peer=? AND id=? AND direction='incoming'", (sender, ident)).fetchone()
        if previous:
            if previous['text'] != text:
                raise ValueError('Message id already binds different terms')
            return
        now = time.time()
        node.db.execute('''INSERT INTO hosted_messages
            (id,peer,direction,text,status,created_at,received_at) VALUES(?,?,'incoming',?,'received',?,?)''',
            (ident, sender, text, now, now))

    def history(self, node_id, peer, offset=0):
        if type(offset) is not int or not 0 <= offset <= 10**9:
            raise ValueError('History offset must be a nonnegative bounded integer')
        with self.node(node_id) as node:
            self._direct_peer(node, peer)
            entries = [dict(dict(row), type='message', timestamp=row['created_at'])
                       for row in node.db.execute('SELECT * FROM hosted_messages WHERE peer=?', (peer,))]
            for row in node.db.execute('SELECT * FROM obligations WHERE peer=?', (peer,)):
                item = node.obligation_view(row)
                entries.append(dict(item, type='delivery', timestamp=item['created_at']))
            # Filter meaningful outcomes and the direct peer before materializing
            # receipts, so thousands of failed background probes cannot hide a
            # completed clearing or another peer's history.
            for row in node.db.execute('''SELECT data FROM receipts
                    WHERE json_extract(data,'$.status')='committed' AND EXISTS(
                    SELECT 1 FROM json_each(receipts.data,'$.changes') AS change
                    WHERE json_extract(change.value,'$.peer')=?)''', (peer,)):
                item = json.loads(row['data'])
                entries.append(dict(item, type='clearing', timestamp=item['decided_at']))
            entries.sort(key=lambda item: (item['timestamp'], item['type'], item['id'], item.get('direction', '')), reverse=True)
            return dict(entries=entries[offset:offset+100], has_more=offset+100 < len(entries), total=len(entries))

    def accept_invite(self, node_id, invitation, max_trust=10):
        max_trust = self._max_trust(max_trust)
        issuer, token_hash = self._invitation(invitation)
        if issuer == node_id:
            raise ValueError('Invite a different participant')
        with self.node(issuer) as node:
            row = node.db.execute('SELECT * FROM hosted_invites WHERE token_hash=?',
                                  (token_hash,)).fetchone()
            if not row or (row['accepted_by'] is None and row['expires'] < time.time()):
                raise ValueError('Invitation expired or unavailable')
            if row['accepted_by'] not in (None,node_id):
                raise ValueError('Invitation already accepted')
            # Fix the recipient's independent choice before either local
            # enrollment. A crash/retry cannot substitute different bounds.
            accepted_max_trust = row['accepted_max_trust']
            if accepted_max_trust is None:
                accepted_max_trust = max_trust if row['accepted_by'] is None else 10
            node.db.execute('UPDATE hosted_invites SET accepted_by=?,accepted_max_trust=? WHERE token_hash=?',
                            (node_id,accepted_max_trust,token_hash))
            issuer_max_trust = row['max_trust']
            peer_name = row['peer_name']
            config = json.loads(node.db.execute("SELECT v FROM meta WHERE k='hosted_config'").fetchone()[0])
            inviter_name = config.get('label', '')
        # Account enrollment assigns a stable channel key once per pair. This
        # prevents crossed invitations racing to install different secrets.
        # The registry is never passed to an algorithm or queried for routing.
        self.stores.create('enrollment')
        enrollment=self.stores.connection('enrollment')
        try:
            with enrollment:
                enrollment.execute('CREATE TABLE IF NOT EXISTS channel_keys(pair TEXT PRIMARY KEY,secret TEXT NOT NULL)')
                pair=json.dumps(sorted((issuer,node_id)))
                enrollment.execute('INSERT OR IGNORE INTO channel_keys VALUES(?,?)',(pair,secrets.token_urlsafe(32)))
                key=enrollment.execute('SELECT secret FROM channel_keys WHERE pair=?',(pair,)).fetchone()[0]
        finally:
            enrollment.close()
        # Retrying the same invitation completes either half after a crash.
        # This is bilateral account enrollment, never a clearing decision.
        self._connect_local(node_id,issuer,key,accepted_max_trust)
        self._name_local(node_id,issuer,inviter_name)
        self._connect_local(issuer,node_id,key,issuer_max_trust)
        self._name_local(issuer,node_id,peer_name)
        return dict(ok=True,peer=issuer)

    def receive(self, node_id, sender, authorization, data):
        with self.node(node_id) as node:
            if not isinstance(sender, str) or not isinstance(authorization, str) or sender not in node.peers or not hmac.compare_digest(
                    authorization, 'Bearer '+node.peers[sender]['key']):
                raise PermissionError('Peer authentication required')
            if isinstance(data, dict) and data.get('kind') == MESSAGE_KIND:
                self._receive_message(node, sender, data)
            else:
                node.receive(sender,data)
        return dict(ok=True)

    @staticmethod
    def _search_fingerprint(node):
        """Eligibility changes are local balances and exchanged preferences.

        Failed searches, received probes and outbox retries deliberately do not
        reset the backoff: they reveal no new local clearing capacity.
        """
        terms = [(row['peer'], row['balance'], json.loads(row['own']),
                  json.loads(row['peer_preferences']) if row['peer_preferences'] else None)
                 for row in node.db.execute('''SELECT peer,balance,own,peer_preferences
                     FROM balances JOIN contacts USING(peer) ORDER BY peer''')]
        return hashlib.sha256(json.dumps(terms, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    @staticmethod
    def _can_originate(node):
        """A headroom origin must reduce both of its incident exposures.

        The existing origin surplus rule requires local cost -2a. Each quoted
        edge changes exposure by exactly +/-a, so both must decrease: one
        positive and one negative balance on distinct unreserved neighbours.
        Zero edges may still help forward someone else's search.
        """
        signs = set()
        for row in node.db.execute('''SELECT b.peer,b.balance FROM balances b
                LEFT JOIN reservations r USING(peer) WHERE r.peer IS NULL AND b.balance<>0'''):
            before = row['balance']
            after = before-1 if before > 0 else before+1
            try:
                term = node.edge_terms(row['peer'], before, after)
            except ValueError:
                continue
            if headroom_edge_allowed(before, after, term['own_preferences'], term['peer_preferences']):
                signs.add(1 if before > 0 else -1)
                if len(signs) == 2:
                    return True
        return False

    def _search_if_due(self, node):
        now = time.time()
        previous = node.db.execute("SELECT v FROM meta WHERE k='hosted_search_backoff'").fetchone()
        previous = json.loads(previous[0]) if previous else None
        fingerprint = self._search_fingerprint(node)
        changed = previous and previous['fingerprint'] != fingerprint
        wake = node.db.execute("SELECT v FROM meta WHERE k='hosted_next_search'").fetchone()
        if wake and float(wake[0]) > now and not changed:
            return
        active = node.db.execute("SELECT count(*) FROM proposals WHERE status IN ('searching','pending')").fetchone()[0]
        if active >= 2 or not self._can_originate(node):
            return
        # A changed balance or exchanged preference restarts fast attempts.
        # Otherwise exponential retry still explores remote changes periodically
        # without writing unbounded failed-probe journals every few seconds.
        attempts = min(8, previous['attempts']+1) if previous and not changed else 1
        node.discover(1, mode='headroom')
        delay = min(SEARCH_RETRY_MAX, 4*2**(attempts-1)+secrets.randbelow(1000)/1000)
        node.db.execute("INSERT OR REPLACE INTO meta VALUES('hosted_search_backoff',?)",
                        (json.dumps(dict(fingerprint=fingerprint, attempts=attempts)),))
        node.db.execute("INSERT OR REPLACE INTO meta VALUES('hosted_next_search',?)", (str(now+delay),))

    def tick(self, node_id):
        """One local wakeup. No global graph/counter or other node object."""
        with self.node(node_id) as node:
            enabled = node.db.execute("SELECT v FROM meta WHERE k='hosted_automation'").fetchone()
            if enabled and enabled[0] == 'true' and not node.paused():
                # No automatic obligation approvals. Clearing requires a saved
                # bilateral assistance preference on BOTH of this node's edges.
                for row in list(node.db.execute("SELECT * FROM proposals WHERE status='pending' AND approved=0")):
                    data=json.loads(row['data'])
                    if data.get('clearing_mode') not in (None,'headroom'):
                        continue
                    changes=data.get('changes',[])
                    if len(changes) != 2:
                        continue
                    permitted=True
                    for change in changes:
                        try:
                            term=node.edge_terms(change['peer'],change['before'],change['after'])
                        except ValueError:
                            permitted=False
                            break
                        zone=term['shared_comfort']
                        permitted &= (term['own_preferences']['auto_adjust']
                                      and term['peer_preferences']['auto_adjust']
                                      and not zone['empty']
                                      and zone['min'] <= change['after'] <= zone['max'])
                    if permitted:
                        node.approve(row['id'],data.get('digest'))
                self._search_if_due(node)
            outgoing=[]
            # Chats to an unavailable peer cannot sit ahead of financial
            # protocol work merely because their outbox rows were queued first.
            for row in node.db.execute("SELECT * FROM outbox ORDER BY CASE WHEN json_extract(data,'$.kind')=? THEN 1 ELSE 0 END,rowid LIMIT 5", (MESSAGE_KIND,)):
                peer=node.peers[row['peer']]
                outgoing.append(dict(id=row['id'],url=peer['url'].rstrip('/')+'/peer/message',
                                     key=peer['key'],peer=row['peer'],body=row['data']))
        # Network delivery never holds local/remote database locks together.
        for item in outgoing:
            request=Request(item['url'],data=item['body'].encode(),headers={
                'Content-Type':'application/json','Authorization':'Bearer '+item['key'],'X-Peer-ID':node_id})
            try:
                with urlopen(request,timeout=3) as response:
                    response.read(4096)
                    if response.status != 200:
                        continue
            except (URLError,OSError,TimeoutError):
                continue
            with self.node(node_id) as node:
                data = json.loads(item['body'])
                if data.get('kind') == MESSAGE_KIND:
                    node.db.execute("""UPDATE hosted_messages SET status='delivered',
                        delivered_at=coalesce(delivered_at,?)
                        WHERE peer=? AND id=? AND direction='outgoing'""",
                        (time.time(), item['peer'], data['id']))
                node.db.execute('DELETE FROM outbox WHERE id=?',(item['id'],))

    def scheduled_nodes(self):
        return [key[5:] for key in self.stores.list_nodes() if key.startswith('node:')]
