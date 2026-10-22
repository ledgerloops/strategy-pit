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

NODE_ID = re.compile(r'n_[0-9a-f]{32}\Z')


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
        node.db.execute("INSERT OR REPLACE INTO meta VALUES('hosted_automatic_clearing_v1',?)",
                        (json.dumps(deferred),))

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
            for contact in state['contacts']:
                contact['name'] = node.peers[contact['peer']].get('name', '')
            return state

    def automation(self, node_id, enabled):
        if type(enabled) is not bool:
            raise ValueError('enabled must be boolean')
        with self.node(node_id) as node:
            node.db.execute("INSERT OR REPLACE INTO meta VALUES('hosted_automation',?)", ('true' if enabled else 'false',))
        return dict(enabled=enabled)

    def invite(self, node_id, peer_name=''):
        if (not isinstance(peer_name, str) or len(peer_name) > 80 or
                any(unicodedata.category(char) in ('Cc', 'Cf', 'Cs') for char in peer_name)):
            raise ValueError('Peer name must be at most 80 characters without control characters')
        peer_name = peer_name.strip()
        token = secrets.token_urlsafe(32)
        expires = time.time()+24*60*60
        with self.node(node_id) as node:
            config = json.loads(node.db.execute("SELECT v FROM meta WHERE k='hosted_config'").fetchone()[0])
            node.db.execute('DELETE FROM hosted_invites WHERE expires<? AND accepted_by IS NULL', (time.time(),))
            node.db.execute('INSERT INTO hosted_invites(token_hash,expires,peer_name) VALUES(?,?,?)',
                            (hashlib.sha256(token.encode()).hexdigest(), expires, peer_name))
        invitation = node_id+'.'+token
        return dict(invite_token=invitation, expires_at=expires, inviter_name=config.get('label', ''),
                    peer_name=peer_name, invite_url=self.origin+'/#invite='+quote(invitation, safe=''))

    def _invitation(self, invitation):
        if not isinstance(invitation, str) or len(invitation) > 200 or '.' not in invitation:
            raise ValueError('Invalid invitation')
        issuer, token = invitation.split('.', 1)
        self.key(issuer)
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise ValueError('Invalid invitation')
        return issuer, hashlib.sha256(token.encode()).hexdigest()

    def preview_invite(self, invitation):
        """Only names/expiry are disclosed to a bearer of an unused invitation."""
        issuer, token_hash = self._invitation(invitation)
        with self.node(issuer) as node:
            row = node.db.execute('SELECT expires,accepted_by,peer_name FROM hosted_invites WHERE token_hash=?',
                                  (token_hash,)).fetchone()
            if not row or row['accepted_by'] is not None or row['expires'] < time.time():
                raise ValueError('Invitation expired or unavailable')
            config = json.loads(node.db.execute("SELECT v FROM meta WHERE k='hosted_config'").fetchone()[0])
            return dict(inviter_name=config.get('label', ''), peer_name=row['peer_name'], expires_at=row['expires'])

    def _connect_local(self, node_id, peer, key):
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
            own = dict(revision=1,credit_limit=10,comfort_min=-10,comfort_max=10,auto_adjust=True)
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

    def accept_invite(self, node_id, invitation):
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
            node.db.execute('UPDATE hosted_invites SET accepted_by=? WHERE token_hash=?',
                            (node_id,token_hash))
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
        self._connect_local(node_id,issuer,key)
        self._name_local(node_id,issuer,inviter_name)
        self._connect_local(issuer,node_id,key)
        self._name_local(issuer,node_id,peer_name)
        return dict(ok=True,peer=issuer)

    def receive(self, node_id, sender, authorization, data):
        with self.node(node_id) as node:
            if sender not in node.peers or not hmac.compare_digest(
                    authorization, 'Bearer '+node.peers[sender]['key']):
                raise PermissionError('Peer authentication required')
            node.receive(sender,data)
        return dict(ok=True)

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
                wake=node.db.execute("SELECT v FROM meta WHERE k='hosted_next_search'").fetchone()
                if not wake or float(wake[0]) <= time.time():
                    active=node.db.execute("SELECT count(*) FROM proposals WHERE status IN ('searching','pending')").fetchone()[0]
                    # Check local starting eligibility before entering discover's
                    # nested transaction. An expected no-candidate exception
                    # would otherwise roll back the whole local wakeup.
                    if active < 2 and any(node.headroom_candidate(1,direction)[0]
                                          is not None for direction in (1,-1)):
                        node.discover(1,mode='headroom')
                    node.db.execute("INSERT OR REPLACE INTO meta VALUES('hosted_next_search',?)",
                                    (str(time.time()+2+secrets.randbelow(4000)/1000),))
            outgoing=[]
            for row in node.db.execute('SELECT * FROM outbox LIMIT 5'):
                peer=node.peers[row['peer']]
                outgoing.append(dict(id=row['id'],url=peer['url'].rstrip('/')+'/peer/message',
                                     key=peer['key'],body=row['data']))
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
                node.db.execute('DELETE FROM outbox WHERE id=?',(item['id'],))

    def scheduled_nodes(self):
        return [key[5:] for key in self.stores.list_nodes() if key.startswith('node:')]
