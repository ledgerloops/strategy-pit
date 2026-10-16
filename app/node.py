#!/usr/bin/env python3
"""Crash-recoverable neighbour-only clearing demo. TEST units, trusted peers only."""
import argparse
import hmac
import hashlib
import json
import sqlite3
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

MAX_AMOUNT = 10**12
MAX_PATH = 32


class Node:
    def __init__(self, config, database):
        if config.get('mode') != 'testnet':
            raise ValueError('Only explicit mode=testnet is supported')
        self.name = config['node']
        self.token = config['token']
        self.peers = config['peers']
        if not self.token or any(not p.get('key') or p['key'] == self.token for p in self.peers.values()):
            raise ValueError('Distinct nonempty client and peer credentials required')
        if self.name in self.peers or not self.peers:
            raise ValueError('Configure direct peers, excluding self')
        self.lock = threading.RLock()
        self.db = sqlite3.connect(database, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        has_meta = self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
        if has_meta:
            protocol = self.db.execute("SELECT v FROM meta WHERE k='protocol'").fetchone()
            if protocol and protocol[0] != 'ring-coordinator-v1':
                self.db.close()
                raise ValueError('Incompatible database protocol: legacy server requires a fresh or v1 testnet database')
        self.db.executescript('''PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT);
        CREATE TABLE IF NOT EXISTS balances(peer TEXT PRIMARY KEY,balance INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY,data TEXT NOT NULL,status TEXT NOT NULL,approved INTEGER DEFAULT 0,prepared INTEGER DEFAULT 0,votes TEXT DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS reservations(peer TEXT PRIMARY KEY,proposal TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,peer TEXT NOT NULL,data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS inbox(id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS searches(id TEXT PRIMARY KEY,status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY,data TEXT NOT NULL);
        ''')
        with self.db:
            identity = self.db.execute("SELECT v FROM meta WHERE k='node'").fetchone()
            if identity and identity[0] != self.name:
                raise ValueError('Database belongs to another node')
            self.db.execute("INSERT OR IGNORE INTO meta VALUES('node',?)", (self.name,))
            self.db.execute("INSERT OR IGNORE INTO meta VALUES('paused','false')")
            for peer, data in self.peers.items():
                balance = data['balance']
                if type(balance) is not int or abs(balance) > MAX_AMOUNT:
                    raise ValueError('Balances must be bounded integer TEST units')
                if not data['url'].startswith(('http://','https://')):
                    raise ValueError('Peer URL must be HTTP(S)')
                self.db.execute('INSERT OR IGNORE INTO balances VALUES(?,?)', (peer,balance))
            stored = {r[0] for r in self.db.execute('SELECT peer FROM balances')}
            if stored != set(self.peers):
                raise ValueError('Changing peers requires a new testnet database')
        self.stopped = threading.Event()

    def paused(self):
        return self.db.execute("SELECT v FROM meta WHERE k='paused'").fetchone()[0] == 'true'

    def enqueue(self, peer, message):
        if peer not in self.peers:
            raise ValueError('Message destination is not a direct neighbour')
        message = dict(message, message_id=uuid.uuid4().hex)
        self.db.execute('INSERT INTO outbox VALUES(?,?,?)', (message['message_id'],peer,json.dumps(message)))

    def balance(self, peer):
        row = self.db.execute('SELECT balance FROM balances WHERE peer=?',(peer,)).fetchone()
        if row is None:
            raise ValueError('Unknown peer')
        return row[0]

    def proposal(self, ident):
        row = self.db.execute('SELECT * FROM proposals WHERE id=?',(ident,)).fetchone()
        if not row:
            raise ValueError('Unknown proposal')
        return row

    def view(self, row):
        data = json.loads(row['data'])
        return dict(data,status=row['status'],approved=bool(row['approved']))

    def state(self):
        with self.lock:
            return dict(node=self.name,mode='testnet',unit='TEST',paused=self.paused(),
                        balances=[dict(r) for r in self.db.execute('SELECT b.*,r.proposal AS reserved_by FROM balances b LEFT JOIN reservations r USING(peer) ORDER BY peer')],
                        proposals=[self.view(r) for r in self.db.execute('SELECT * FROM proposals ORDER BY rowid DESC LIMIT 100')],
                        receipts=self.receipts(),searches=[dict(r) for r in self.db.execute('SELECT * FROM searches ORDER BY rowid DESC LIMIT 100')],outbox_pending=self.db.execute('SELECT count(*) FROM outbox').fetchone()[0])

    def receipts(self):
        with self.lock:
            return [json.loads(r[0]) for r in self.db.execute('SELECT data FROM receipts ORDER BY rowid DESC LIMIT 100')]

    def discover(self, amount):
        if type(amount) is not int or not 0 < amount <= MAX_AMOUNT:
            raise ValueError('amount must be a positive bounded integer')
        with self.lock, self.db:
            if self.paused():
                raise ValueError('Discovery paused')
            candidates = [r for r in self.db.execute('SELECT * FROM balances WHERE balance<0 ORDER BY peer')
                          if not self.db.execute('SELECT 1 FROM reservations WHERE peer=?',(r['peer'],)).fetchone()]
            if not candidates:
                raise ValueError('No unreserved outgoing debt channel')
            peer = candidates[0]
            ident = uuid.uuid4().hex
            self.db.execute('INSERT INTO searches VALUES(?,?)',(ident,'searching'))
            self.enqueue(peer['peer'],dict(kind='discover',id=ident,path=[self.name],amount=min(amount,-peer['balance'])))
            return dict(id=ident,status='searching')

    def route(self, data, kind, **extra):
        path = data['path']
        next_peer = path[(path.index(self.name)+1)%len(path)]
        self.enqueue(next_peer,dict(kind=kind,id=data['id'],path=path,amount=data['amount'],**extra))

    def approve(self, ident, digest=None):
        with self.lock,self.db:
            row = self.proposal(ident)
            local = json.loads(row['data'])
            if digest != local.get('digest'):
                raise ValueError('Approval must match displayed proposal digest')
            if row['approved']:
                return dict(ok=True,status=row['status'])
            if row['status'] != 'pending':
                raise ValueError('Proposal is not pending approval')
            if self.paused():
                raise ValueError('Approvals paused')
            if row['approved']:
                return dict(ok=True)
            data = json.loads(row['data'])
            self.db.execute('UPDATE proposals SET approved=1 WHERE id=?',(ident,))
            if data['path'][0] == self.name:
                self.vote(data,self.name)
            else:
                self.route(data,'vote',voter=self.name)
            return dict(ok=True)

    def decline(self, ident, digest):
        with self.lock,self.db:
            row = self.proposal(ident)
            data = json.loads(row['data'])
            if digest != data.get('digest'):
                raise ValueError('Decline must match displayed proposal digest')
            if row['status'] in ('aborted','declining'):
                return dict(ok=True,status=row['status'])
            if row['status'] != 'pending' or row['approved']:
                raise ValueError('Cannot decline after approval or decision')
            if data['path'][0] == self.name:
                self.decide(data,'abort')
            else:
                self.db.execute("UPDATE proposals SET status='declining' WHERE id=?",(ident,))
                self.route(data,'reject')
            return dict(ok=True,status='abort_requested')

    def vote(self, data, voter):
        row = self.proposal(data['id'])
        if row['status'] != 'pending':
            return
        votes = set(json.loads(row['votes']))
        votes.add(voter)
        self.db.execute('UPDATE proposals SET votes=? WHERE id=?',(json.dumps(sorted(votes)),data['id']))
        if row['prepared'] and votes == set(data['path']):
            self.decide(data,'commit')

    def prepare(self, data):
        existing = self.db.execute('SELECT * FROM proposals WHERE id=?',(data['id'],)).fetchone()
        if existing:
            stored = json.loads(existing['data'])
            if stored['path'] != data['path'] or stored['amount'] != data['amount']:
                raise ValueError('Proposal payload mismatch')
            return
        path = data['path']; index = path.index(self.name)
        prev_peer,next_peer = path[index-1],path[(index+1)%len(path)]
        if prev_peer not in self.peers or next_peer not in self.peers:
            raise ValueError('Cycle must use direct neighbours')
        before_prev,before_next = self.balance(prev_peer),self.balance(next_peer)
        valid = (not self.paused() and before_prev >= data['amount'] and before_next <= -data['amount']
                 and not self.db.execute('SELECT 1 FROM reservations WHERE peer IN (?,?)',(prev_peer,next_peer)).fetchone())
        local = dict(id=data['id'],path=path,amount=data['amount'],created_at=time.time(),changes=[
            dict(peer=prev_peer,before=before_prev,after=before_prev-data['amount']),
            dict(peer=next_peer,before=before_next,after=before_next+data['amount'])])
        local['digest'] = hashlib.sha256(json.dumps(local,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.db.execute('INSERT INTO proposals(id,data,status) VALUES(?,?,?)', (data['id'],json.dumps(local),'pending' if valid else 'rejected'))
        if not valid:
            if index == 0:
                self.decide(data,'abort')
            else:
                self.route(data,'reject')
            return
        for peer in (prev_peer,next_peer):
            self.db.execute('INSERT INTO reservations VALUES(?,?)',(peer,data['id']))
        self.route(data,'prepared' if index == len(path)-1 else 'prepare')

    def decide(self,data,decision):
        self.apply(data,decision)
        self.route(data,decision)

    def apply(self,data,decision):
        row = self.db.execute('SELECT * FROM proposals WHERE id=?',(data['id'],)).fetchone()
        if not row:
            if decision == 'commit':
                raise ValueError('Commit requires local prepared proposal')
            tombstone = dict(id=data['id'],path=data['path'],amount=data['amount'],changes=[],created_at=time.time())
            self.db.execute('INSERT INTO proposals(id,data,status) VALUES(?,?,?)',(data['id'],json.dumps(tombstone),'aborted'))
            receipt = dict(tombstone,status='aborted',unit='TEST',mode='testnet',node=self.name,committed_at=time.time(),cycle_complete=False)
            self.db.execute('INSERT INTO receipts VALUES(?,?)',(data['id'],json.dumps(receipt)))
            return
        if row['status'] in ('committed','aborted'):
            if row['status'] != ('committed' if decision == 'commit' else 'aborted'):
                raise ValueError('Conflicting durable decision')
            return
        local = json.loads(row['data'])
        if decision == 'commit':
            if not row['approved'] or row['status'] != 'pending':
                raise ValueError('Commit requires local approval and reservation')
            for change in local['changes']:
                lock = self.db.execute('SELECT proposal FROM reservations WHERE peer=?',(change['peer'],)).fetchone()
                if not lock or lock[0] != data['id'] or self.balance(change['peer']) != change['before']:
                    raise ValueError('Local reservation mismatch')
                self.db.execute('UPDATE balances SET balance=? WHERE peer=?',(change['after'],change['peer']))
        status = 'committed' if decision == 'commit' else 'aborted'
        self.db.execute('UPDATE proposals SET status=? WHERE id=?',(status,data['id']))
        self.db.execute('DELETE FROM reservations WHERE proposal=?',(data['id'],))
        receipt = dict(local,status=status,unit='TEST',mode='testnet',node=self.name,committed_at=time.time(),cycle_complete=False)
        self.db.execute('INSERT OR IGNORE INTO receipts VALUES(?,?)',(data['id'],json.dumps(receipt)))

    def receive(self,sender,data):
        if sender not in self.peers:
            raise ValueError('Unknown sender')
        path = data.get('path'); amount = data.get('amount')
        if not isinstance(path,list) or not 1 <= len(path) <= MAX_PATH or len(set(path)) != len(path) or not all(isinstance(x,str) for x in path):
            raise ValueError('Invalid path')
        if type(amount) is not int or not 0 < amount <= MAX_AMOUNT:
            raise ValueError('Invalid amount')
        if not isinstance(data.get('id'),str) or len(data['id']) > 128 or not isinstance(data.get('message_id'),str) or len(data['message_id']) > 128:
            raise ValueError('Invalid identifier')
        with self.lock,self.db:
            if self.db.execute('SELECT 1 FROM inbox WHERE id=?',(data['message_id'],)).fetchone():
                return
            kind = data['kind']
            existing = self.db.execute('SELECT data FROM proposals WHERE id=?',(data['id'],)).fetchone()
            if existing:
                stored = json.loads(existing[0])
                if stored['path'] != path or stored['amount'] != amount:
                    raise ValueError('Proposal payload mismatch')
            if kind == 'discover':
                if sender != path[-1]:
                    raise ValueError('Invalid discovery predecessor')
                forwarded = False
                if not self.paused() and self.balance(sender) >= amount:
                    if self.name == path[0] and len(path) >= 3:
                        self.db.execute("UPDATE searches SET status='cycle_found' WHERE id=?",(data['id'],))
                        self.prepare(data)
                        forwarded = True
                    elif self.name not in path and len(path) < MAX_PATH:
                        candidates = [r for r in self.db.execute('SELECT * FROM balances WHERE balance<0 ORDER BY peer')
                                      if r['peer'] == path[0] or r['peer'] not in path]
                        if candidates:
                            peer = candidates[0]
                            self.enqueue(peer['peer'],dict(kind='discover',id=data['id'],path=path+[self.name],amount=min(amount,-peer['balance'])))
                            forwarded = True
                if not forwarded:
                    self.enqueue(sender,dict(kind='search_failed',id=data['id'],path=path,amount=amount))
            elif kind == 'search_failed':
                if self.name != path[-1]:
                    raise ValueError('Invalid failure route')
                if len(path) == 1:
                    self.db.execute("UPDATE searches SET status='no_cycle_on_path' WHERE id=?",(data['id'],))
                else:
                    self.enqueue(path[-2],dict(kind='search_failed',id=data['id'],path=path[:-1],amount=amount))
            else:
                if len(path) < 3 or self.name not in path or sender != path[path.index(self.name)-1]:
                    raise ValueError('Invalid ring predecessor')
                if kind == 'prepare':
                    self.prepare(data)
                elif kind == 'prepared':
                    if self.name != path[0]:
                        raise ValueError('Prepared acknowledgement must reach coordinator')
                    self.db.execute('UPDATE proposals SET prepared=1 WHERE id=?',(data['id'],))
                    row = self.proposal(data['id'])
                    if row['status'] == 'pending' and set(json.loads(row['votes'])) == set(path):
                        self.decide(data,'commit')
                elif kind == 'vote':
                    if data.get('voter') not in path:
                        raise ValueError('Unknown voter')
                    if self.name == path[0]:
                        self.vote(data,data['voter'])
                    else:
                        self.route(data,'vote',voter=data['voter'])
                elif kind == 'reject':
                    if self.name == path[0]:
                        if self.proposal(data['id'])['status'] == 'pending':
                            self.decide(data,'abort')
                    else:
                        self.route(data,'reject')
                elif kind in ('commit','abort'):
                    if self.name == path[0]:
                        # Ring acknowledgement: local decision was durable before sending.
                        row = self.proposal(data['id'])
                        if row['status'] != ('committed' if kind == 'commit' else 'aborted'):
                            raise ValueError('Unsolicited decision at coordinator')
                        self.complete(dict(data,decision=kind))
                        self.route(data,'complete',decision=kind)
                    else:
                        self.apply(data,kind)
                        self.route(data,kind)
                elif kind == 'complete':
                    if self.name != path[0]:
                        self.complete(data)
                        self.route(data,'complete',decision=data['decision'])
                else:
                    raise ValueError('Unknown message kind')
            self.db.execute('INSERT INTO inbox VALUES(?)',(data['message_id'],))

    def complete(self,data):
        row = self.db.execute('SELECT data FROM receipts WHERE id=?',(data['id'],)).fetchone()
        if not row:
            raise ValueError('Completion requires a local durable decision')
        if row:
            receipt = json.loads(row[0])
            expected = {'commit':'committed','abort':'aborted'}.get(data.get('decision'))
            if receipt['status'] != expected:
                raise ValueError('Completion contradicts local decision')
            receipt['cycle_complete'] = True
            self.db.execute('UPDATE receipts SET data=? WHERE id=?',(json.dumps(receipt),data['id']))

    def worker(self):
        while not self.stopped.wait(.25):
            with self.lock:
                rows = list(self.db.execute('SELECT * FROM outbox LIMIT 100'))
            for row in rows:
                if self.stopped.is_set():
                    return
                request = Request(self.peers[row['peer']]['url'].rstrip('/')+'/peer/message',data=row['data'].encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+self.peers[row['peer']]['key'],'X-Peer-ID':self.name})
                try:
                    with urlopen(request,timeout=1) as response:
                        response.read(4096)
                        if response.status != 200:
                            continue
                    with self.lock,self.db:
                        self.db.execute('DELETE FROM outbox WHERE id=?',(row['id'],))
                except (URLError,OSError,TimeoutError):
                    pass


def make_handler(node):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def reply(self,status,data):
            body=json.dumps(data).encode()
            self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)

        def authorized(self,peer=False):
            sender=self.headers.get('X-Peer-ID','')
            if peer and sender not in node.peers:
                return False
            expected='Bearer '+(node.peers[sender]['key'] if peer else node.token)
            return hmac.compare_digest(self.headers.get('Authorization',''),expected)

        def do_GET(self):
            if self.path.startswith('/api/'):
                if not self.authorized():
                    return self.reply(401,dict(error='Client authentication required'))
                if self.path == '/api/state':
                    return self.reply(200,node.state())
                if self.path == '/api/obligations' and hasattr(node,'obligations'):
                    return self.reply(200,node.obligations())
                if self.path == '/api/receipts':
                    return self.reply(200,node.receipts())
                if self.path.startswith('/api/receipts/'):
                    ident=self.path.split('/')[-1]
                    with node.lock:
                        row=node.db.execute('SELECT data FROM receipts WHERE id=?',(ident,)).fetchone()
                    return self.reply(200,json.loads(row[0])) if row else self.reply(404,dict(error='Receipt not found'))
                return self.reply(404,dict(error='Not found'))
            target={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/style.css':'style.css','/styles.css':'styles.css','/logo.jpg':'logo.jpg'}.get(self.path)
            if not target:
                return self.reply(404,dict(error='Not found'))
            file=Path(__file__).parent/'static'/target
            if not file.is_file():
                return self.reply(404,dict(error='UI not installed'))
            body=file.read_bytes(); mime={'.html':'text/html','.js':'application/javascript','.css':'text/css','.jpg':'image/jpeg'}[file.suffix]
            self.send_response(200); self.send_header('Content-Type',mime+'; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(body)

        def do_POST(self):
            peer=self.path == '/peer/message'
            if not self.authorized(peer):
                return self.reply(401,dict(error='Authentication required'))
            try:
                if self.headers.get('Content-Type','').split(';')[0].strip() != 'application/json':
                    raise ValueError('Content-Type application/json required')
                origin=self.headers.get('Origin')
                if origin and origin not in ('http://'+self.headers.get('Host',''),'https://'+self.headers.get('Host','')):
                    raise ValueError('Cross-origin writes are forbidden')
                length=int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 65536:
                    raise ValueError('Request body must be between 1 and 65536 bytes')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):
                    raise ValueError('Expected JSON object')
                if peer:
                    node.receive(self.headers.get('X-Peer-ID',''),data)
                    result=dict(ok=True)
                elif self.path == '/api/obligations' and hasattr(node,'propose_obligation'):
                    result=node.propose_obligation(data)
                elif self.path.startswith('/api/obligations/') and self.path.endswith('/approve') and hasattr(node,'approve_obligation'):
                    result=node.approve_obligation(self.path.split('/')[-2],data.get('digest'))
                elif self.path.startswith('/api/obligations/') and self.path.endswith('/decline') and hasattr(node,'decline_obligation'):
                    result=node.decline_obligation(self.path.split('/')[-2],data.get('digest'))
                elif self.path.startswith('/api/contacts/') and self.path.endswith('/preferences') and hasattr(node,'set_preferences'):
                    from urllib.parse import unquote
                    result=node.set_preferences(unquote(self.path.split('/')[-2]),data)
                elif self.path == '/api/discover':
                    mode=data.get('mode','cancellation')
                    if hasattr(node,'comfort_candidate'):
                        result=node.discover(data.get('amount'),mode=mode)
                    else:
                        if mode != 'cancellation':
                            raise ValueError('This legacy node supports cancellation mode only')
                        result=node.discover(data.get('amount'))
                elif self.path.startswith('/api/proposals/') and self.path.endswith('/approve'):
                    result=node.approve(self.path.split('/')[-2],data.get('digest'))
                elif self.path.startswith('/api/proposals/') and self.path.endswith('/decline'):
                    result=node.decline(self.path.split('/')[-2],data.get('digest'))
                elif self.path == '/api/pause':
                    if type(data.get('paused')) is not bool:
                        raise ValueError('paused must be boolean')
                    with node.lock,node.db:
                        node.db.execute("UPDATE meta SET v=? WHERE k='paused'",('true' if data['paused'] else 'false',))
                    result=dict(paused=data['paused'])
                else:
                    return self.reply(404,dict(error='Not found'))
                self.reply(200,result)
            except (ValueError,KeyError,TypeError,sqlite3.IntegrityError) as error:
                self.reply(400,dict(error=str(error)))
    return Handler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True); parser.add_argument('--db',required=True); parser.add_argument('--port',type=int,required=True); parser.add_argument('--host',default='127.0.0.1')
    args=parser.parse_args()
    node=Node(json.loads(Path(args.config).read_text()),args.db)
    thread=threading.Thread(target=node.worker,daemon=True); thread.start()
    server=ThreadingHTTPServer((args.host,args.port),make_handler(node))
    print(json.dumps(dict(node=node.name,mode='testnet',url=f'http://{args.host}:{args.port}')),flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        node.stopped.set(); server.server_close(); thread.join(timeout=2)

if __name__ == '__main__':
    main()
