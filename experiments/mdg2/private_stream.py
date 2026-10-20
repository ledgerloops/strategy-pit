"""Asynchronous research adapter for the real neighbour-private v2 SQLite engine.

Only event transport and offline scoring see the fixture. Participants receive
only their own Node, direct-peer packets and independent local clock events.
No global cycle, path, length, coordinator, membership or acceptance oracle is
provided. The isolated research comfort policy is explicitly versioned; original
production modules are unchanged. Reliable delivery is the default, not a claim
of Byzantine security or a completeness guarantee. SQLite durability is real;
HTTP headers/TCP, signatures and process isolation are not simulated.
"""
from collections import deque, Counter
from copy import deepcopy
import hashlib
import heapq
import json
from pathlib import Path
import random
import secrets
import sys
import tempfile
import time

APP = Path(__file__).resolve().parents[2] / 'app'
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))
import private_node as private_app
from private_node import Node as OriginalNode, PROTOCOL, HASHLOCK_SCHEME, MAX_AMOUNT, canonical_hex, hash_condition
from comfort import comfort_move

COMFORT_POLICY = 'private-local-nonexpansion-v1'
COMFORT_SCHEME = 'sha256-private-local-nonexpansion-v1'
METHODS = ('randomized_cancellation', 'private_nonexpansion', 'faithful_comfort')


def hash_comfort_condition(ident, amount, preimage, direction):
    hash_condition(ident, amount, preimage)
    if type(direction) is not int or direction not in (-1, 1):
        raise ValueError('Invalid comfort direction')
    context = dict(protocol=PROTOCOL, unit='TEST', id=ident, amount=amount,
                   preimage=preimage, clearing_mode='comfort',
                   policy=COMFORT_POLICY, direction=direction)
    return hashlib.sha256(json.dumps(context, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True).encode('ascii')).hexdigest()


def seeded(seed, node, purpose):
    return random.Random(int.from_bytes(hashlib.sha256(
        f'{seed}:{node}:{purpose}'.encode()).digest(), 'big'))


class RandomizedPrivateNode(OriginalNode):
    """Same original policy, shuffled eligible direct neighbours at each choice."""
    def __init__(self, config, database, rng=None):
        self.choice_rng = rng or random.Random(0)
        super().__init__(config, database)

    def candidate(self, amount, exclude=None):
        eligible = []
        for row in self.db.execute('SELECT peer FROM balances WHERE balance<=? ORDER BY peer', (-amount,)):
            peer = row['peer']
            if (peer != exclude and self.permits(peer, self.balance(peer), self.balance(peer)+amount)
                    and not self.db.execute('SELECT 1 FROM reservations WHERE peer=?', (peer,)).fetchone()):
                eligible.append(peer)
        self.choice_rng.shuffle(eligible)
        return eligible[0] if eligible else None

    def comfort_candidate(self, amount, direction, exclude=None, strict=False):
        eligible = []
        for peer in sorted(self.peers):
            if peer == exclude or self.db.execute('SELECT 1 FROM reservations WHERE peer=?', (peer,)).fetchone():
                continue
            before, after = self.balance(peer), self.balance(peer)+direction*amount
            try:
                term = self.edge_terms(peer, before, after)
            except ValueError:
                continue
            if self.origin_eligible(before, after, term, strict):
                eligible.append(peer)
        self.choice_rng.shuffle(eligible)
        return eligible[0] if eligible else None

    def origin_eligible(self, before, after, term, strict):
        return comfort_move(before, after, term['own_preferences'], term['peer_preferences'], strict)


class NonexpandingPrivateNode(RandomizedPrivateNode):
    """Versioned local consent: each pair nonexpanding, origin strictly reducing.

    Four protocol methods below are static copies of the original v2 engine.
    Only the comfort policy/hash scheme, origin eligibility and pair-L1 consent
    differ. Immutable quotes, digests, per-link locks, durable outbox, readiness,
    SHA256 secret release and actual local fulfillment remain the v2 machinery.
    No runtime monkeypatch of production module globals is used.
    """
    def origin_eligible(self, before, after, term, strict):
        return (comfort_move(before, after, term['own_preferences'], term['peer_preferences'])
                and (not strict or abs(after) < abs(before)))

    def discover(self, amount, mode="cancellation"):
        if type(amount) is not int or not 0 < amount <= MAX_AMOUNT:
            raise ValueError('amount must be a positive bounded integer')
        if mode not in ('cancellation','comfort'):
            raise ValueError('Unknown clearing mode')
        with self.lock, self.db:
            if self.paused():
                raise ValueError('Discovery paused')
            direction=1
            following=self.candidate(amount) if mode == 'cancellation' else None
            if mode == 'comfort':
                for direction in (1,-1):
                    following=self.comfort_candidate(amount,direction,strict=True)
                    if following is not None:
                        break
            if following is None:
                raise ValueError('No unreserved outgoing debt channel with requested capacity')
            preimage = secrets.token_bytes(32).hex()
            ident = secrets.token_bytes(32).hex()
            condition = hash_condition(ident,amount,preimage) if mode == 'cancellation' else hash_comfort_condition(ident,amount,preimage,direction)
            data = dict(id=ident,condition=condition,amount=amount,protocol=PROTOCOL,hashlock_scheme=HASHLOCK_SCHEME,changes=[],created_at=time.time())
            if mode == 'comfort':
                data.update(clearing_mode='comfort',policy=COMFORT_POLICY,direction=direction,hashlock_scheme=COMFORT_SCHEME,
                            outgoing_quote=self.edge_terms(following,self.balance(following),self.balance(following)+direction*amount))
            self.db.execute('INSERT INTO proposals(id,data,status,next,origin) VALUES(?,?,?,?,1)', (ident,json.dumps(data),'searching',following))
            self.db.execute('INSERT INTO private_secrets VALUES(?,?)', (ident,preimage))
            self.db.execute('INSERT INTO searches VALUES(?,?)', (ident,'searching'))
            self.send(following,data,'probe')
            return dict(id=ident,status='searching')

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
        if self.paused():
            return False
        comfort=data.get('clearing_mode') == 'comfort'
        delta=data.get('direction',1)*data['amount']
        if comfort:
            try:
                changes=[self.edge_terms(prev,incoming,incoming-delta),self.edge_terms(following,outgoing,outgoing+delta)]
            except ValueError:
                return False
            if any(not comfort_move(c['before'],c['after'],c['own_preferences'],c['peer_preferences']) for c in changes):
                return False
            local_cost = sum(abs(c['after'])-abs(c['before']) for c in changes)
            if local_cost > 0 or (row['origin'] and local_cost >= 0):
                return False
            if row['origin'] and abs(outgoing+delta) >= abs(outgoing):
                return False
            if data.get('incoming_quote') != changes[0] or data.get('outgoing_quote') != changes[1]:
                return False
        else:
            if incoming < data['amount'] or outgoing > -data['amount']:
                return False
            if not self.permits(prev,incoming,incoming-delta) or not self.permits(following,outgoing,outgoing+delta):
                return False
            changes=[dict(peer=prev,before=incoming,after=incoming-delta),dict(peer=following,before=outgoing,after=outgoing+delta)]
        if self.db.execute('SELECT 1 FROM reservations WHERE peer IN (?,?)',(prev,following)).fetchone():
            return False
        data['changes'] = changes
        data['digest'] = hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        for peer in (prev,following):
            self.db.execute('INSERT INTO reservations VALUES(?,?)',(peer,row['id']))
        self.db.execute("UPDATE proposals SET data=?,status='pending',prepared=1 WHERE id=?",(json.dumps(data),row['id']))
        return True

    def check_preimage(self,data):
        preimage=data.get('preimage')
        if not canonical_hex(preimage):
            raise ValueError('Invalid hashlock fulfillment')
        condition=hash_comfort_condition(data['id'],data['amount'],preimage,data['direction']) if data.get('clearing_mode') == 'comfort' else hash_condition(data['id'],data['amount'],preimage)
        if condition != data['condition']:
            raise ValueError('Invalid hashlock fulfillment')

    def receive(self,sender,data):
        if sender not in self.peers:
            raise ValueError('Unknown sender')
        if isinstance(data.get('kind'),str) and data['kind'].startswith('obligation_'):
            return self.receive_obligation(sender,data)
        if data.get('kind') == 'preferences':
            return self.receive_preferences(sender,data)
        allowed={'kind','id','condition','amount','protocol','message_id','preimage','clearing_mode','policy','direction','edge_quote'}
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
        comfort=data.get('clearing_mode') == 'comfort'
        if comfort:
            if data.get('policy') != COMFORT_POLICY or type(data.get('direction')) is not int or data['direction'] not in (-1,1):
                raise ValueError('Invalid comfort policy')
            if ('edge_quote' in data) != (kind in ('probe','prepare')):
                raise ValueError('Edge quote only required on comfort admission')
        elif any(key in data for key in ('clearing_mode','policy','direction','edge_quote')):
            raise ValueError('Unexpected cancellation policy fields')
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
                        if comfort and not self.quote_matches(sender,data):
                            self.send(sender,data,'probe_rejected')
                            self.db.execute('INSERT INTO inbox VALUES(?)',(data['message_id'],))
                            return
                        local=json.loads(row['data'])
                        if comfort:
                            local['incoming_quote']=self.edge_terms(sender,self.balance(sender),self.balance(sender)-data['direction']*data['amount'])
                        self.db.execute('UPDATE proposals SET prev=?,data=? WHERE id=?',(sender,json.dumps(local),row['id']))
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
                    if comfort and not self.quote_matches(sender,data):
                        self.send(sender,data,'probe_rejected')
                        self.db.execute('INSERT INTO inbox VALUES(?)',(data['message_id'],))
                        return
                    if comfort:
                        following=None if self.paused() else self.comfort_candidate(data['amount'],data['direction'],sender)
                    else:
                        following=None if self.paused() or self.balance(sender) < data['amount'] else self.candidate(data['amount'],sender)
                    local=dict(id=data['id'],condition=data['condition'],amount=data['amount'],protocol=PROTOCOL,hashlock_scheme=HASHLOCK_SCHEME,changes=[],created_at=time.time())
                    if comfort:
                        local.update(clearing_mode='comfort',policy=COMFORT_POLICY,direction=data['direction'],hashlock_scheme=COMFORT_SCHEME,
                                     incoming_quote=self.edge_terms(sender,self.balance(sender),self.balance(sender)-data['direction']*data['amount']))
                        if following:
                            local['outgoing_quote']=self.edge_terms(following,self.balance(following),self.balance(following)+data['direction']*data['amount'])
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
                    if comfort and not self.quote_matches(sender,data):
                        self.reject(row)
                        self.db.execute('INSERT INTO inbox VALUES(?)',(data['message_id'],))
                        return
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


class LocalActor:
    """Local automation only; holds no other node, graph or observer reference."""
    def __init__(self, node, seed, method, discovery_until):
        self.node, self.method = node, method
        self.discovery_until = discovery_until
        self.timer_rng = seeded(seed, node.name, 'timer')
        self.wire_rng = seeded(seed, node.name, 'wire')
        self.offers = deque()
        self.current_attempt = None
        self.completed_offers = []
        self.attempt_number = 0

    def next_wakeup(self, mean):
        return self.timer_rng.expovariate(1/mean)

    def pending_approvals(self):
        return [(r['id'], json.loads(r['data'])['digest']) for r in self.node.db.execute(
            "SELECT * FROM proposals WHERE status='pending' AND prepared=1 AND approved=0 ORDER BY rowid")]

    def pending_obligation_approvals(self):
        return [(r['id'], r['digest']) for r in self.node.db.execute(
            "SELECT * FROM obligations WHERE status='pending' AND origin=0 AND approved=0 ORDER BY rowid")]

    def offer_action(self):
        """A client retries an aborted quote under a fresh attempt id, locally."""
        if self.current_attempt:
            row = self.node.obligation_row(self.current_attempt)
            if row['status'] == 'committed':
                offer = self.offers.popleft()
                completed = dict(offer, attempt_id=self.current_attempt)
                self.completed_offers.append(completed)
                self.current_attempt = None
                return 'accepted', completed
            if row['status'] == 'aborted':
                old = self.current_attempt
                self.current_attempt = None
                return 'retry', dict(self.offers[0], attempt_id=old)
            return None
        if not self.offers:
            return None
        offer = self.offers[0]
        self.attempt_number += 1
        ident = secrets.token_hex(32)
        values = dict(id=ident, peer=offer['b'], amount=abs(offer['amount']),
                      direction='peer_owes' if offer['amount'] > 0 else 'i_owe',
                      description='synthetic offered transfer')
        try:
            result = self.node.propose_obligation(values)
        except ValueError as error:
            return 'blocked', dict(offer, error=str(error))
        self.current_attempt = ident
        return 'attempt', dict(offer, attempt_id=ident, digest=result['obligation']['digest'])

    def discovery(self, now):
        if now >= self.discovery_until:
            return None
        if self.node.db.execute("SELECT 1 FROM proposals WHERE origin=1 AND status NOT IN ('committed','aborted') LIMIT 1").fetchone():
            return None
        mode = 'cancellation' if self.method == 'randomized_cancellation' else 'comfort'
        try:
            return self.node.discover(1, mode)
        except ValueError:
            return None


class PrivateStream:
    """Event transport around isolated real SQLite v2 nodes, no protocol coordinator.

    The simulator heap delivers events and records measurements; it never
    chooses a route, accepts a cycle, or controls participant synchronization.
    ``edges`` are (a,b,balance_at_a,preferences_at_a,preferences_at_b).
    Arrivals use actual bilateral-obligation packets and per-edge reservations.
    An offer's signed ``amount`` is the change at a (its mirror is -amount).
    Initialization preference packets are counted. Local automation approves
    exact immutable proposals upon message reception; local wakeups independently
    initiate searches and retry client offers. Offered flows and approvals remain
    active after the local discovery cutoff. No work is forcibly unlocked.

    Full journal captures actual local applications. Offline causal reconstruction
    belongs outside measured run() and cannot influence any actor. HTTP/TCP/header
    bytes are excluded; exact stored JSON request and response-body bytes are
    separately counted. Unknown/crashed/permanently unavailable peers are not
    modeled by the default reliable queue.
    """
    def __init__(self, edges, seed=0, method='randomized_cancellation', *,
                 wake_mean=1., wire_delay=(.005,.015), retry_delay=.05,
                 discovery_until=30., message_cap=250000, directory=None,
                 drop_request_ids=(), drop_ack_ids=()):
        if method not in METHODS:
            raise ValueError('Unknown private stream method')
        if (wake_mean <= 0 or retry_delay <= 0 or len(wire_delay) != 2
                or not 0 <= wire_delay[0] <= wire_delay[1] or wire_delay[1] <= 0
                or type(message_cap) is not int or message_cap < 0):
            raise ValueError('Invalid finite transport configuration')
        self.method, self.seed = method, seed
        self.wake_mean, self.wire_delay, self.retry_delay = wake_mean, wire_delay, retry_delay
        self.discovery_until, self.message_cap = discovery_until, message_cap
        self._temporary = tempfile.TemporaryDirectory(prefix='ledgerloops-private-') if directory is None else None
        self.directory = Path(self._temporary.name if self._temporary else directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        if any(self.directory.glob('*.sqlite')):
            raise ValueError('Research adapter requires a fresh isolated directory')
        self.edges = [(str(a),str(b),balance,deepcopy(pa),deepcopy(pb)) for a,b,balance,pa,pb in edges]
        if not self.edges:
            raise ValueError('At least one trustline required')
        self.initial_balances, own = {}, {}
        pairs = set()
        for a,b,balance,pa,pb in self.edges:
            pair = tuple(sorted((a,b)))
            if a == b or pair in pairs or type(balance) is not int:
                raise ValueError('Distinct integer-valued trustlines required')
            pairs.add(pair)
            self.initial_balances.setdefault(a,{})[b] = balance
            self.initial_balances.setdefault(b,{})[a] = -balance
            own.setdefault(a,{})[b] = pa
            own.setdefault(b,{})[a] = pb
        self.initial_preferences = own
        self.actors = {}
        self.queue, self.serial = [], 0
        self.now, self.events, self.trace = 0., [], []
        self.messages, self.message_bytes, self.delivered, self.delivery_failures = 0,0,0,0
        self.acks, self.ack_bytes, self.delivered_acks, self.dropped_requests, self.dropped_acks = 0,0,0,0,0
        self.message_kinds = Counter()
        self.inflight = set()
        self.drop_request_ids, self.drop_ack_ids = set(drop_request_ids), set(drop_ack_ids)
        self.sent_per_id = Counter()
        self.censored, self.closed, self.runtime_seconds = False,False,0.
        self.offered_ids = set()
        self.endpoint_balances = deepcopy(self.initial_balances)
        self.node_stats = {}
        self._receipt_rowid, self._obligation_seen = {}, {}
        self.initialized_preferences = {}
        NodeClass = NonexpandingPrivateNode if method == 'private_nonexpansion' else (OriginalNode if method == 'faithful_comfort' else RandomizedPrivateNode)
        for name, balances in sorted(self.initial_balances.items()):
            config = dict(node=name, mode='testnet', token=secrets.token_hex(32), peers={
                peer:dict(balance=balance,url='http://isolated.invalid',key=secrets.token_hex(32))
                for peer,balance in balances.items()})
            database = self.directory / (hashlib.sha256(name.encode()).hexdigest()+'.sqlite')
            node = NodeClass(config,str(database),rng=seeded(seed,name,'choice')) if NodeClass is not OriginalNode else NodeClass(config,str(database))
            self.actors[name] = LocalActor(node,seed,method,discovery_until)
            self._receipt_rowid[name] = 0
            self._obligation_seen[name] = {}
            self.initialized_preferences[name] = {}
            for peer,preferences in sorted(own[name].items()):
                values = {key:preferences[key] for key in ('credit_limit','comfort_min','comfort_max','auto_adjust')}
                node.set_preferences(peer,dict(values,expected_revision=1))
                self.initialized_preferences[name][peer] = dict(values,revision=2)
            self._capture(name, {})
        self._record(dict(kind='initial',time=0.))
        for name, actor in self.actors.items():
            self._schedule(actor.next_wakeup(wake_mean),'wake',name)
            self._pump(name)

    def _schedule(self, at, kind, *args):
        self.serial += 1
        heapq.heappush(self.queue,(at,self.serial,kind,args))

    def _capture(self, name, event):
        """Instrumentation reads only the node just acted on; never routes traffic."""
        node = self.actors[name].node
        changes = []
        for row in node.db.execute('SELECT peer,balance FROM balances ORDER BY peer'):
            before = self.endpoint_balances[name][row['peer']]
            if before != row['balance']:
                changes.append(dict(node=name,peer=row['peer'],before=before,after=row['balance']))
                self.endpoint_balances[name][row['peer']] = row['balance']
        if changes:
            event.setdefault('balance_changes',[]).extend(changes)
        for row in node.db.execute('SELECT rowid,data FROM receipts WHERE rowid>? ORDER BY rowid',(self._receipt_rowid[name],)):
            self._receipt_rowid[name] = row['rowid']
            receipt = json.loads(row['data'])
            # Aborts also retained, but separate from actual local fulfillment.
            key = 'local_receipts' if receipt.get('local_fulfilled') else 'local_aborts'
            event.setdefault(key,[]).append(dict(node=name,receipt=receipt))
        for row in node.db.execute('SELECT * FROM obligations ORDER BY rowid'):
            signature = (row['status'],row['approved'],row['applied_at'],row['reason'])
            if self._obligation_seen[name].get(row['id']) != signature:
                self._obligation_seen[name][row['id']] = signature
                event.setdefault('local_obligations',[]).append(dict(node=name,obligation=node.obligation_view(row)))
        self.node_stats[name] = dict(
            reservations=node.db.execute('SELECT count(*) FROM reservations').fetchone()[0],
            outbox=node.db.execute('SELECT count(*) FROM outbox').fetchone()[0],
            unresolved_proposals=node.db.execute("SELECT count(*) FROM proposals WHERE status NOT IN ('committed','aborted')").fetchone()[0],
            unresolved_obligations=node.db.execute("SELECT count(*) FROM obligations WHERE status NOT IN ('committed','aborted')").fetchone()[0])

    def _record(self, event):
        event.setdefault('time',self.now)
        event['messages'] = self.messages
        event['message_bytes'] = self.message_bytes
        event['acknowledgements'] = self.acks
        event['ack_body_bytes'] = self.ack_bytes
        self.events.append(event)
        pairs = [(a,b) for a,links in self.endpoint_balances.items() for b in links if a < b]
        gaps = [self.endpoint_balances[a][b]+self.endpoint_balances[b][a] for a,b in pairs]
        stats = {key:sum(s[key] for s in self.node_stats.values()) for key in ('reservations','outbox','unresolved_proposals','unresolved_obligations')}
        self.trace.append(dict(time=self.now,event_end_index=len(self.events),messages=self.messages,
            message_bytes=self.message_bytes,acknowledgements=self.acks,ack_body_bytes=self.ack_bytes,
            delivered_messages=self.delivered,
            debt=sum(max(-balance,0) for links in self.endpoint_balances.values() for balance in links.values()),
            mirror_mismatches=sum(gap != 0 for gap in gaps),absolute_mirror_gap=sum(abs(gap) for gap in gaps),
            pending_messages=len(self.inflight),offered=len(self.offered_ids),
            accepted_offers=sum(len(a.completed_offers) for a in self.actors.values()),
            offer_backlog=sum(len(a.offers) for a in self.actors.values()),**stats))

    def _pump(self, name):
        if self.censored:
            return
        actor = self.actors[name]
        for row in actor.node.db.execute('SELECT * FROM outbox ORDER BY rowid').fetchall():
            key = (name,row['id'])
            if key in self.inflight:
                continue
            if self.messages >= self.message_cap:
                self.censored = True
                self._record(dict(kind='message_cap',time=self.now))
                return
            raw = row['data']
            self.inflight.add(key)
            self.sent_per_id[key] += 1
            self.messages += 1
            self.message_bytes += len(raw.encode('utf-8'))
            payload = json.loads(raw)
            self.message_kinds[payload['kind']] += 1
            attempt = self.messages
            event = dict(kind='request',source=name,target=row['peer'],payload=payload,
                         raw_json=raw,bytes=len(raw.encode('utf-8')),attempt=attempt,
                         retry=self.sent_per_id[key]>1)
            self._record(event)
            delay = actor.wire_rng.uniform(*self.wire_delay)
            if attempt in self.drop_request_ids:
                self.dropped_requests += 1
                self._schedule(self.now+self.retry_delay,'request_lost',name,row['id'],attempt)
            else:
                self._schedule(self.now+delay,'deliver',name,row['peer'],row['id'],raw,attempt)

    def offer(self, at, a, b, amount, offer_id):
        a,b = str(a),str(b)
        if (a not in self.actors or b not in self.actors[a].node.peers
                or type(amount) is not int or not 0 < abs(amount) <= MAX_AMOUNT
                or not isinstance(offer_id,str) or offer_id in self.offered_ids
                or at < self.now):
            raise ValueError('Unique bounded direct-neighbour offer at a future time required')
        # Registered scheduling IDs are distinct from offers that have arrived.
        if not hasattr(self,'_scheduled_offer_ids'):
            self._scheduled_offer_ids = set()
        if offer_id in self._scheduled_offer_ids:
            raise ValueError('Duplicate offered transaction id')
        self._scheduled_offer_ids.add(offer_id)
        self._schedule(float(at),'offer',dict(a=a,b=b,amount=amount,offer_id=offer_id))

    def _local_automation(self, name):
        actor = self.actors[name]
        for ident,digest in actor.pending_approvals():
            event = dict(kind='local_approval',node=name,id=ident,digest=digest,
                         approval_policy=COMFORT_POLICY if self.method == 'private_nonexpansion' else 'original-v2',accepted=True)
            self._record(event)  # Local consent causally precedes possible fulfillment.
            actor.node.approve(ident,digest)
            applied = dict(kind='approval_result',node=name,id=ident)
            self._capture(name,applied)
            self._record(applied)
        for ident,digest in actor.pending_obligation_approvals():
            event = dict(kind='obligation_approval',node=name,id=ident,digest=digest,accepted=True)
            self._record(event)
            actor.node.approve_obligation(ident,digest)
            applied = dict(kind='obligation_approval_result',node=name,id=ident)
            self._capture(name,applied)
            self._record(applied)
        outcome = actor.offer_action()
        if outcome:
            action,details = outcome
            event = dict(kind='offer_'+action,node=name,**details)
            self._capture(name,event)
            self._record(event)
        self._pump(name)

    def run(self, until):
        if self.closed or until < self.now:
            raise ValueError('Run requires open adapter and nondecreasing time')
        start = time.perf_counter()
        while self.queue and self.queue[0][0] <= until and not self.censored:
            at,serial,kind,args = heapq.heappop(self.queue)
            self.now = at
            if kind == 'wake':
                name, = args
                actor = self.actors[name]
                self._local_automation(name)
                found = actor.discovery(self.now)
                if found:
                    event = dict(kind='discover',node=name,**found)
                    self._capture(name,event)
                    self._record(event)
                self._pump(name)
                self._schedule(self.now+actor.next_wakeup(self.wake_mean),'wake',name)
            elif kind == 'offer':
                offer, = args
                self.offered_ids.add(offer['offer_id'])
                self.actors[offer['a']].offers.append(offer)
                self._record(dict(kind='offer',**offer))
                self._local_automation(offer['a'])
            elif kind == 'deliver':
                source,target,ident,raw,attempt = args
                event = dict(kind='message',source=source,target=target,payload=json.loads(raw),
                             raw_json=raw,bytes=len(raw.encode('utf-8')),attempt=attempt)
                try:
                    self.actors[target].node.receive(source,event['payload'])
                    self.delivered += 1
                    event['ok'] = True
                except ValueError as error:
                    self.delivery_failures += 1
                    event.update(ok=False,error=str(error))
                self._capture(target,event)
                self._record(event)
                self._local_automation(target)
                ack = json.dumps(dict(ok=True)) if event['ok'] else json.dumps(dict(error=event['error']))
                self.acks += 1
                self.ack_bytes += len(ack.encode('utf-8'))
                self._record(dict(kind='ack_request',source=target,target=source,id=ident,attempt=attempt,
                                  ok=event['ok'],raw_json=ack,bytes=len(ack.encode('utf-8'))))
                self._schedule(self.now+self.actors[target].wire_rng.uniform(*self.wire_delay),
                               'ack',source,target,ident,attempt,event['ok'],ack)
            elif kind == 'ack':
                source,target,ident,attempt,success,raw = args
                lost = attempt in self.drop_ack_ids
                self.delivered_acks += int(not lost)
                self.dropped_acks += int(lost)
                self._record(dict(kind='ack',source=target,target=source,id=ident,attempt=attempt,
                                  ok=success,lost=lost,raw_json=raw,bytes=len(raw.encode('utf-8'))))
                if success and not lost:
                    node = self.actors[source].node
                    with node.lock,node.db:
                        node.db.execute('DELETE FROM outbox WHERE id=?',(ident,))
                    self.inflight.discard((source,ident))
                    event = dict(kind='outbox_acknowledged',node=source,id=ident)
                    self._capture(source,event)
                    self._record(event)
                    self._local_automation(source)
                else:
                    self._schedule(self.now+self.retry_delay,'retry',source,ident)
            elif kind in ('retry','request_lost'):
                source,ident = args[:2]
                if kind == 'request_lost':
                    self.dropped_requests += 0  # Counted at emission.
                    self._record(dict(kind='request_lost',source=source,id=ident,attempt=args[2]))
                if self.messages >= self.message_cap:
                    # The outstanding logical request still awaits its ACK.
                    # Preserve it and its durable outbox if retry is censored.
                    self.censored = True
                    self._record(dict(kind='message_cap',time=self.now))
                else:
                    self.inflight.discard((source,ident))
                    self._pump(source)
            else:
                raise AssertionError('Unknown transport event')
        if not self.censored:
            self.now = float(until)
        self.runtime_seconds += time.perf_counter()-start
        self._record(dict(kind='checkpoint',censored=self.censored))
        return self.result()

    def result(self):
        return dict(method=self.method,policy=COMFORT_POLICY if self.method == 'private_nonexpansion' else None,
            seed=self.seed,time=self.now,censored=self.censored,status='message_cap' if self.censored else 'fixed_window',
            messages=self.messages,message_bytes=self.message_bytes,acknowledgements=self.acks,ack_body_bytes=self.ack_bytes,
            delivered_messages=self.delivered,
            delivery_failures=self.delivery_failures,
            delivered_acknowledgements=self.delivered_acks,
            dropped_requests=self.dropped_requests,dropped_acknowledgements=self.dropped_acks,
            retried_requests=sum(max(0,n-1) for n in self.sent_per_id.values()),
            message_kinds=dict(self.message_kinds),runtime_seconds=self.runtime_seconds,
            initial_balances=deepcopy(self.initial_balances),initial_preferences=deepcopy(self.initialized_preferences),
            final_balances=deepcopy(self.endpoint_balances),original_trustlines=len(self.edges),
            events=self.events,trace=self.trace,final=self.trace[-1],
            accepted_offers=[dict(item,node=name) for name,actor in self.actors.items() for item in actor.completed_offers],
            pending_offers=[dict(item,node=name,current_attempt=actor.current_attempt if i == 0 else None)
                            for name,actor in self.actors.items() for i,item in enumerate(actor.offers)],
            pending_events=len(self.queue),sampling='full journal, all exact request JSON bodies',
            accounting='Request and ACK JSON bodies counted at emission; deliveries, retries and loss separately. HTTP/TCP headers excluded.',
            assumptions=['honest isolated SQLite nodes','simulated authenticated direct-neighbour transport',
                         'independent exponential local wakeups','bounded reliable asynchronous delivery unless injected loss',
                         'automatic exact-digest local consent','fixed local discovery cutoff; no forced reservation release',
                         'no completeness guarantee; local nonexpansion can exclude improving loops'])

    def close(self):
        if not self.closed:
            for actor in self.actors.values():
                actor.node.db.close()
            self.closed = True
            if self._temporary:
                self._temporary.cleanup()

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()
