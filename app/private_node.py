#!/usr/bin/env python3
"""Neighbour-only private-route hashlock TEST network. Honest peers, crash recovery."""
import argparse
import hashlib
import json
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from http.server import ThreadingHTTPServer
from node import Node as TransportNode, make_handler, MAX_AMOUNT
from comfort import validate_preferences, shared_comfort, allows_balance

PROTOCOL = 'private-hashlock-v2'
HASHLOCK_SCHEME = 'sha256-context-v2'


def canonical_hex(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def hash_condition(ident, amount, preimage):
    if not canonical_hex(ident) or not canonical_hex(preimage) or type(amount) is not int or not 0 < amount <= MAX_AMOUNT:
        raise ValueError('Invalid hashlock context')
    context = dict(protocol=PROTOCOL, unit='TEST', id=ident, amount=amount, preimage=preimage)
    return hashlib.sha256(json.dumps(context,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')).hexdigest()


class Node:
    def __init__(self, config, database):
        if config.get('mode') != 'testnet':
            raise ValueError('Only explicit mode=testnet is supported')
        self.name, self.token, self.peers = config['node'], config['token'], config['peers']
        if not self.token or not self.peers or self.name in self.peers:
            raise ValueError('Distinct local identity and neighbours required')
        if any(not p.get('key') or p['key'] == self.token for p in self.peers.values()):
            raise ValueError('Distinct client and neighbour credentials required')
        self.lock = threading.RLock()
        self.db = sqlite3.connect(database, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables:
            version = self.db.execute("SELECT v FROM meta WHERE k='protocol'").fetchone() if 'meta' in tables else None
            if not version or version[0] != PROTOCOL:
                self.db.close()
                raise ValueError('Incompatible database: create a fresh private-hashlock-v2 testnet')
        self.db.executescript('''PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT);
        CREATE TABLE IF NOT EXISTS balances(peer TEXT PRIMARY KEY,balance INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY,data TEXT NOT NULL,status TEXT NOT NULL,approved INTEGER DEFAULT 0,prev TEXT,next TEXT,origin INTEGER DEFAULT 0,prepared INTEGER DEFAULT 0,ready_seen INTEGER DEFAULT 0,ready_forwarded INTEGER DEFAULT 0,next_rejected INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS private_secrets(id TEXT PRIMARY KEY,preimage TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reservations(peer TEXT PRIMARY KEY,proposal TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,peer TEXT NOT NULL,data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS inbox(id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS searches(id TEXT PRIMARY KEY,status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS contacts(peer TEXT PRIMARY KEY, own TEXT NOT NULL, peer_preferences TEXT);
        CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY,data TEXT NOT NULL);
        ''')
        with self.db:
            identity = self.db.execute("SELECT v FROM meta WHERE k='node'").fetchone()
            if identity and identity[0] != self.name:
                raise ValueError('Database belongs to another node')
            self.db.execute("INSERT OR IGNORE INTO meta VALUES('protocol',?)", (PROTOCOL,))
            self.db.execute("INSERT OR IGNORE INTO meta VALUES('node',?)", (self.name,))
            self.db.execute("INSERT OR IGNORE INTO meta VALUES('paused','false')")
            for peer, config in self.peers.items():
                if type(config['balance']) is not int or abs(config['balance']) > MAX_AMOUNT:
                    raise ValueError('Bounded integer TEST balance required')
                if not config['url'].startswith(('http://', 'https://')):
                    raise ValueError('HTTP(S) neighbour URL required')
                self.db.execute('INSERT OR IGNORE INTO balances VALUES(?,?)', (peer, config['balance']))
            for peer in self.peers:
                existing = self.db.execute('SELECT 1 FROM contacts WHERE peer=?',(peer,)).fetchone()
                if not existing:
                    own = dict(revision=1,credit_limit=max(0,self.balance(peer)),comfort_min=0,comfort_max=0,auto_adjust=False)
                    self.db.execute('INSERT INTO contacts VALUES(?,?,NULL)',(peer,json.dumps(own)))
                    self.enqueue(peer,dict(kind='preferences',protocol=PROTOCOL,preferences=own))
            if {r[0] for r in self.db.execute('SELECT peer FROM balances')} != set(self.peers):
                raise ValueError('Peer configuration changed: use a fresh testnet')
        self.stopped = threading.Event()

    paused = TransportNode.paused
    balance = TransportNode.balance
    enqueue = TransportNode.enqueue
    worker = TransportNode.worker
    proposal = TransportNode.proposal
    receipts = TransportNode.receipts

    def state(self):
        with self.lock:
            proposals = []
            for row in self.db.execute('SELECT * FROM proposals ORDER BY rowid DESC LIMIT 100'):
                data = json.loads(row['data'])
                if row['prepared'] or row['status'] in ('committed', 'aborted', 'declining'):
                    proposals.append(dict(data, status=row['status'], approved=bool(row['approved'])))
            return dict(node=self.name, mode='testnet', protocol=PROTOCOL, unit='TEST', paused=self.paused(),contacts=self.contacts(),
                        balances=[dict(r) for r in self.db.execute('SELECT b.*,r.proposal AS reserved_by FROM balances b LEFT JOIN reservations r USING(peer) ORDER BY peer')],
                        proposals=proposals, receipts=self.receipts(),
                        searches=[dict(r) for r in self.db.execute('SELECT * FROM searches ORDER BY rowid DESC LIMIT 100')],
                        outbox_pending=self.db.execute('SELECT count(*) FROM outbox').fetchone()[0])

    def contacts(self):
        result=[]
        for row in self.db.execute('SELECT * FROM contacts ORDER BY peer'):
            own=json.loads(row['own']); peer=json.loads(row['peer_preferences']) if row['peer_preferences'] else None
            overlap=shared_comfort(own,peer) if peer else None
            lock=self.db.execute('SELECT proposal FROM reservations WHERE peer=?',(row['peer'],)).fetchone()
            result.append(dict(peer=row['peer'],balance=self.balance(row['peer']),own=own,peer_preferences=peer,
                               hard_min=-peer['credit_limit'] if peer else None,hard_max=own['credit_limit'],
                               shared_comfort=overlap,reserved_by=lock[0] if lock else None,auto_adjust_active=False))
        return result

    def set_preferences(self,peer,values):
        if peer not in self.peers:
            raise ValueError('Unknown direct neighbour')
        preferences=validate_preferences(values)
        if type(values.get('expected_revision')) is not int or not 1 <= values['expected_revision'] < 10**12:
            raise ValueError('Expected revision required')
        with self.lock,self.db:
            row=self.db.execute('SELECT own FROM contacts WHERE peer=?',(peer,)).fetchone()
            own=json.loads(row[0])
            if own['revision'] != values['expected_revision']:
                raise ValueError('Preferences changed; refresh before saving')
            if self.db.execute('SELECT 1 FROM reservations WHERE peer=?',(peer,)).fetchone():
                raise ValueError('Cannot change preferences while this edge is reserved')
            preferences['revision']=own['revision']+1
            self.db.execute('UPDATE contacts SET own=? WHERE peer=?',(json.dumps(preferences),peer))
            self.enqueue(peer,dict(kind='preferences',protocol=PROTOCOL,preferences=preferences))
            return dict(ok=True,contact=next(c for c in self.contacts() if c['peer']==peer))

    def receive_preferences(self,sender,data):
        if set(data) != {'kind','protocol','preferences','message_id'} or data['protocol'] != PROTOCOL:
            raise ValueError('Invalid neighbour preferences envelope')
        preferences=validate_preferences(data['preferences'])
        revision=data['preferences'].get('revision')
        if type(revision) is not int or not 1 <= revision <= 10**12:
            raise ValueError('Invalid preferences revision')
        if set(data['preferences']) != set(preferences)|{'revision'}:
            raise ValueError('Unexpected preferences fields')
        if not isinstance(data['message_id'],str) or not 1 <= len(data['message_id']) <= 128:
            raise ValueError('Invalid message identifier')
        preferences['revision']=revision
        with self.lock,self.db:
            row=self.db.execute('SELECT peer_preferences FROM contacts WHERE peer=?',(sender,)).fetchone()
            previous=json.loads(row[0]) if row[0] else None
            if previous and previous['revision'] == revision and previous != preferences:
                raise ValueError('Conflicting preferences at same revision')
            if previous and previous['revision'] >= revision:
                return
            if self.db.execute('SELECT 1 FROM reservations WHERE peer=?',(sender,)).fetchone():
                raise ValueError('Preferences update deferred until reservation finishes')
            self.db.execute('UPDATE contacts SET peer_preferences=? WHERE peer=?',(json.dumps(preferences),sender))

    def permits(self,peer,before,after):
        row=self.db.execute('SELECT * FROM contacts WHERE peer=?',(peer,)).fetchone()
        return allows_balance(before,after,json.loads(row['own']),json.loads(row['peer_preferences']) if row['peer_preferences'] else None)

    def envelope(self, data, kind, **extra):
        return dict(kind=kind,id=data['id'],condition=data['condition'],amount=data['amount'],protocol=PROTOCOL,**extra)

    def send(self, peer, data, kind, **extra):
        if peer is not None:
            self.enqueue(peer, self.envelope(data, kind, **extra))

    def candidate(self, amount, exclude=None):
        for row in self.db.execute('SELECT peer FROM balances WHERE balance<=? ORDER BY peer', (-amount,)):
            if row['peer'] != exclude and self.permits(row['peer'],self.balance(row['peer']),self.balance(row['peer'])+amount) and not self.db.execute('SELECT 1 FROM reservations WHERE peer=?', (row['peer'],)).fetchone():
                return row['peer']
        return None

    def discover(self, amount):
        if type(amount) is not int or not 0 < amount <= MAX_AMOUNT:
            raise ValueError('amount must be a positive bounded integer')
        with self.lock, self.db:
            if self.paused():
                raise ValueError('Discovery paused')
            following = self.candidate(amount)
            if following is None:
                raise ValueError('No unreserved outgoing debt channel with requested capacity')
            preimage = secrets.token_bytes(32).hex()
            ident = secrets.token_bytes(32).hex()
            condition = hash_condition(ident,amount,preimage)
            data = dict(id=ident,condition=condition,amount=amount,protocol=PROTOCOL,hashlock_scheme=HASHLOCK_SCHEME,changes=[],created_at=time.time())
            self.db.execute('INSERT INTO proposals(id,data,status,next,origin) VALUES(?,?,?,?,1)', (ident,json.dumps(data),'searching',following))
            self.db.execute('INSERT INTO private_secrets VALUES(?,?)', (ident,preimage))
            self.db.execute('INSERT INTO searches VALUES(?,?)', (ident,'searching'))
            self.send(following,data,'probe')
            return dict(id=ident,status='searching')

    def bind(self, row, data):
        stored = json.loads(row['data'])
        if any(stored[key] != data[key] for key in ('id','condition','amount','protocol')):
            raise ValueError('Immutable proposal mismatch')
        return stored

    def prepare_local(self, row):
        data = json.loads(row['data'])
        if row['status'] in ('aborted','committed','declining','rejected'):
            return False
        if row['prepared']:
            return True
        prev, following = row['prev'], row['next']
        if not prev or not following or prev == following:
            return False
        incoming, outgoing = self.balance(prev), self.balance(following)
        if self.paused() or incoming < data['amount'] or outgoing > -data['amount']:
            return False
        if not self.permits(prev,incoming,incoming-data['amount']) or not self.permits(following,outgoing,outgoing+data['amount']):
            return False
        if self.db.execute('SELECT 1 FROM reservations WHERE peer IN (?,?)',(prev,following)).fetchone():
            return False
        data['changes'] = [dict(peer=prev,before=incoming,after=incoming-data['amount']),
                           dict(peer=following,before=outgoing,after=outgoing+data['amount'])]
        data['digest'] = hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        for peer in (prev,following):
            self.db.execute('INSERT INTO reservations VALUES(?,?)',(peer,row['id']))
        self.db.execute("UPDATE proposals SET data=?,status='pending',prepared=1 WHERE id=?",(json.dumps(data),row['id']))
        return True

    def approve(self, ident, digest=None):
        with self.lock,self.db:
            row = self.proposal(ident); data = json.loads(row['data'])
            if not digest or digest != data.get('digest'):
                raise ValueError('Approval must match displayed proposal digest')
            if row['approved']:
                return dict(ok=True,status=row['status'])
            if row['status'] != 'pending' or not row['prepared'] or self.paused():
                raise ValueError('Proposal is not available for approval')
            self.db.execute('UPDATE proposals SET approved=1 WHERE id=?',(ident,))
            self.ready(self.proposal(ident))
            return dict(ok=True)

    def decline(self, ident, digest):
        with self.lock,self.db:
            row = self.proposal(ident); data = json.loads(row['data'])
            if not digest or digest != data.get('digest'):
                raise ValueError('Decline must match displayed proposal digest')
            if row['status'] in ('declining','aborted'):
                return dict(ok=True,status=row['status'])
            if row['status'] != 'pending' or row['approved']:
                raise ValueError('Cannot decline after approval or decision')
            self.reject(row)
            return dict(ok=True,status='abort_requested')

    def reject(self,row):
        if row['status'] in ('committed','aborted'):
            return
        data=json.loads(row['data'])
        if row['origin']:
            self.apply(row,'abort')
            if not row['next_rejected']:
                self.send(row['next'],data,'abort')
            self.db.execute("UPDATE searches SET status='no_cycle_on_path' WHERE id=?",(row['id'],))
        else:
            self.db.execute("UPDATE proposals SET status='declining' WHERE id=?",(row['id'],))
            self.send(row['prev'],data,'reject')

    def ready(self,row):
        if row['status'] != 'pending' or not row['prepared'] or not row['approved'] or not row['ready_seen'] or row['ready_forwarded']:
            return
        self.db.execute('UPDATE proposals SET ready_forwarded=1 WHERE id=?',(row['id'],))
        self.send(row['next'],json.loads(row['data']),'ready')

    def check_preimage(self,data):
        preimage=data.get('preimage')
        if not canonical_hex(preimage) or hash_condition(data['id'],data['amount'],preimage) != data['condition']:
            raise ValueError('Invalid hashlock fulfillment')

    def apply(self,row,decision,preimage=None):
        data=json.loads(row['data'])
        if decision == 'fulfill':
            self.check_preimage(dict(data,preimage=preimage))
        status='committed' if decision == 'fulfill' else 'aborted'
        if row['status'] in ('committed','aborted'):
            if row['status'] != status:
                raise ValueError('Conflicting durable decision')
            return
        if decision == 'fulfill':
            if row['status'] != 'pending' or not row['prepared'] or not row['approved']:
                raise ValueError('Fulfillment requires local approval and reservations')
            for change in data['changes']:
                lock=self.db.execute('SELECT proposal FROM reservations WHERE peer=?',(change['peer'],)).fetchone()
                if not lock or lock[0] != row['id'] or self.balance(change['peer']) != change['before']:
                    raise ValueError('Local reservation mismatch')
                self.db.execute('UPDATE balances SET balance=? WHERE peer=?',(change['after'],change['peer']))
        self.db.execute('UPDATE proposals SET status=? WHERE id=?',(status,row['id']))
        self.db.execute('DELETE FROM reservations WHERE proposal=?',(row['id'],))
        receipt=dict(data,status=status,node=self.name,mode='testnet',unit='TEST',local_fulfilled=decision=='fulfill',decided_at=time.time())
        if decision == 'fulfill':
            receipt['preimage']=preimage
        self.db.execute('INSERT OR IGNORE INTO receipts VALUES(?,?)',(row['id'],json.dumps(receipt)))

    def receive(self,sender,data):
        if sender not in self.peers:
            raise ValueError('Unknown sender')
        if data.get('kind') == 'preferences':
            return self.receive_preferences(sender,data)
        allowed={'kind','id','condition','amount','protocol','message_id','preimage'}
        if set(data)-allowed:
            raise ValueError('Unexpected wire fields')
        if data.get('protocol') != PROTOCOL or not canonical_hex(data.get('condition')) or not canonical_hex(data.get('id')):
            raise ValueError('Invalid protocol or condition')
        if type(data.get('amount')) is not int or not 0 < data['amount'] <= MAX_AMOUNT:
            raise ValueError('Invalid amount')
        if not isinstance(data.get('message_id'),str) or not 1 <= len(data['message_id']) <= 128:
            raise ValueError('Invalid message identifier')
        kind=data.get('kind')
        if kind not in ('probe','probe_rejected','prepare','ready','reject','abort','fulfill'):
            raise ValueError('Unknown message kind')
        if kind == 'fulfill':
            self.check_preimage(data)
        elif 'preimage' in data:
            raise ValueError('Preimage permitted only on fulfillment')
        with self.lock,self.db:
            row=self.db.execute('SELECT * FROM proposals WHERE id=?',(data['id'],)).fetchone()
            if row:
                self.bind(row,data)
            # Validate evidence before deduplication, including terminal replay.
            if self.db.execute('SELECT 1 FROM inbox WHERE id=?',(data['message_id'],)).fetchone():
                return
            if kind == 'probe':
                if row:
                    if row['origin'] and row['status'] == 'searching' and sender != row['next']:
                        self.db.execute('UPDATE proposals SET prev=? WHERE id=?',(sender,row['id']))
                        row=self.proposal(row['id'])
                        if self.prepare_local(row):
                            self.db.execute("UPDATE searches SET status='cycle_found' WHERE id=?",(row['id'],))
                            self.send(row['next'],data,'prepare')
                        else:
                            self.reject(row)
                    elif sender == row['prev']:
                        pass  # Semantic replay: original forwarding is already durable.
                    else:
                        self.send(sender,data,'probe_rejected')
                else:
                    following=None if self.paused() or self.balance(sender) < data['amount'] else self.candidate(data['amount'],sender)
                    local=dict(id=data['id'],condition=data['condition'],amount=data['amount'],protocol=PROTOCOL,hashlock_scheme=HASHLOCK_SCHEME,changes=[],created_at=time.time())
                    self.db.execute('INSERT INTO proposals(id,data,status,prev,next) VALUES(?,?,?,?,?)',(data['id'],json.dumps(local),'searching',sender,following))
                    if following:
                        self.send(following,data,'probe')
                    else:
                        self.reject(self.proposal(data['id']))
            else:
                if not row:
                    raise ValueError('Unknown local proposal')
                predecessor = row['next'] if kind in ('reject','probe_rejected') else row['prev']
                if sender != predecessor:
                    raise ValueError('Message is not from bound neighbour')
                if kind == 'probe_rejected':
                    if row['status'] not in ('committed','aborted'):
                        self.db.execute('UPDATE proposals SET next_rejected=1 WHERE id=?',(row['id'],))
                        self.reject(self.proposal(row['id']))
                elif kind == 'reject':
                    self.reject(row)
                elif kind == 'prepare':
                    if row['origin']:
                        if row['status'] == 'pending':
                            self.db.execute('UPDATE proposals SET ready_seen=1 WHERE id=?',(row['id'],))
                            self.ready(self.proposal(row['id']))
                    elif self.prepare_local(row):
                        self.send(row['next'],data,'prepare')
                    elif row['status'] not in ('aborted','committed'):
                        self.reject(row)
                elif kind == 'ready':
                    if row['origin']:
                        if row['status'] == 'committed':
                            pass
                        elif row['status'] == 'pending' and row['approved'] and row['ready_forwarded']:
                            secret=self.db.execute('SELECT preimage FROM private_secrets WHERE id=?',(row['id'],)).fetchone()[0]
                            self.apply(row,'fulfill',secret)
                            self.send(row['next'],data,'fulfill',preimage=secret)
                        elif row['status'] != 'aborted':
                            raise ValueError('Unsolicited readiness return')
                    elif row['status'] == 'pending':
                        self.db.execute('UPDATE proposals SET ready_seen=1 WHERE id=?',(row['id'],))
                        self.ready(self.proposal(row['id']))
                elif kind == 'abort':
                    self.apply(row,'abort')
                    if not row['origin'] and not row['next_rejected'] and row['status'] != 'aborted':
                        self.send(row['next'],data,'abort')
                elif kind == 'fulfill':
                    self.apply(row,'fulfill',data['preimage'])
                    if not row['origin'] and row['status'] != 'committed':
                        self.send(row['next'],data,'fulfill',preimage=data['preimage'])
            self.db.execute('INSERT INTO inbox VALUES(?)',(data['message_id'],))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True); parser.add_argument('--db',required=True); parser.add_argument('--port',type=int,required=True); parser.add_argument('--host',default='127.0.0.1')
    args=parser.parse_args()
    node=Node(json.loads(Path(args.config).read_text()),args.db)
    worker=threading.Thread(target=node.worker,daemon=True); worker.start()
    server=ThreadingHTTPServer((args.host,args.port),make_handler(node))
    print(json.dumps(dict(node=node.name,mode='testnet',protocol=PROTOCOL,url=f'http://{args.host}:{args.port}')),flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        node.stopped.set(); server.server_close(); worker.join(timeout=2)

if __name__ == '__main__':
    main()
