"""Serial, local-message research model for comfort zones as clearing headroom.

Policies are 'cancellation' and 'comfort_headroom'. Each oriented cycle adds one
unit to the tail's signed balance and subtracts one from its peer's mirror.
Every actor independently admits both its incident changes. A received scalar
sum of absolute-balance changes must be negative before settlement: assistance
may increase individual debts but every committed cycle reduces gross debt.

One search/settlement is in flight. External transfers may occur only between
clear calls. Prepare, commit and cleanup are actual serialized neighbour messages;
commits are staged, not instantaneously atomic, and there is no crash recovery.
The serial scheduler selects initiators and delivers messages but never finds or
accepts a cycle. Search actors inspect only local links and received path tokens.
Tokens expose paths, preferences and balance quotes: no product privacy claim.
"""
from __future__ import annotations

from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'app'))
from comfort import comfort_move, discomfort, shared_comfort, validate_preferences

POLICIES = ('cancellation', 'comfort_headroom')


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def digest_transaction(transaction):
    return hashlib.sha256(compact({k:transaction[k] for k in ('id','policy','path','quotes','gross_delta')})).hexdigest()


class Actor:
    def __init__(self, name, seed, emit, complete):
        self.name = name
        self.links = {}
        self.reservations = {}
        self.rng = random.Random(int.from_bytes(hashlib.sha256(compact([seed,name])).digest()[:8], 'big'))
        self.emit = lambda peer, kind, payload: emit(self.name,peer,kind,payload)
        self.complete = complete

    def allowed(self, peer, delta, policy):
        balance, own, other = self.links[peer]
        after = balance+delta
        zone = shared_comfort(own,other)
        if not zone['hard_min'] <= after <= zone['hard_max']:
            return False
        if policy == 'cancellation':
            return abs(after)<abs(balance)
        if policy != 'comfort_headroom':
            raise ValueError('Unknown headroom policy')
        return comfort_move(balance,after,own,other)

    def quote(self, peer):
        before,own,other = self.links[peer]
        return dict(source=self.name,target=peer,before=before,after=before+1,own=own,other=other)

    def quote_matches(self, quote, outgoing, policy):
        peer = quote['target'] if outgoing else quote['source']
        if peer not in self.links:
            return False
        balance,own,other = self.links[peer]
        sign = 1 if outgoing else -1
        return (quote['before']==sign*balance and quote['after']==sign*balance+1
                and quote['own']==(own if outgoing else other)
                and quote['other']==(other if outgoing else own)
                and self.allowed(peer,1 if outgoing else -1,policy))

    def start(self, ident, policy, discovery_left, depth):
        token=dict(id=ident,policy=policy,path=[self.name],quotes=[],visited=[self.name],
                   tried=[],gross_delta=0,discovery_left=discovery_left,max_depth=depth)
        self.advance(token)

    def finish(self, token):
        if token['path'][-1] != self.name:
            raise ValueError('Search cleanup must follow its received path')
        if len(token['path'])==1:
            self.complete('failed',token)
            return
        token['path'].pop()
        quote=token['quotes'].pop()
        token['gross_delta']-=abs(quote['after'])-abs(quote['before'])
        self.emit(token['path'][-1],'finish',token)

    def advance(self, token):
        if token['discovery_left']<=0:
            return self.finish(token)
        root=token['path'][0]
        candidates=[]
        for peer in self.links:
            if [self.name,peer] in token['tried'] or not self.allowed(peer,1,token['policy']):
                continue
            # Every root attempt must begin on an actual debt-reducing edge;
            # strict discomfort improvement is deliberately not required.
            if len(token['path'])==1 and abs(self.links[peer][0]+1)>=abs(self.links[peer][0]):
                continue
            if peer==root:
                if len(token['path'])>=3:
                    candidates.append(peer)
            elif peer not in token['visited'] and len(token['path'])<token['max_depth']:
                candidates.append(peer)
        self.rng.shuffle(candidates)
        if not candidates:
            if len(token['path'])==1:
                return self.complete('failed',token)
            token['discovery_left']-=1
            token['path'].pop()
            quote=token['quotes'].pop()
            token['gross_delta']-=abs(quote['after'])-abs(quote['before'])
            self.emit(token['path'][-1],'resume',token)
            return
        peer=candidates[0]
        token['tried'].append([self.name,peer])
        quote=self.quote(peer)
        token['quotes'].append(quote)
        token['gross_delta']+=abs(quote['after'])-abs(quote['before'])
        if peer!=root:
            token['path'].append(peer)
            token['visited'].append(peer)
        token['discovery_left']-=1
        self.emit(peer,'probe',token)

    def reject_probe(self, sender, token, closing):
        quote=token['quotes'].pop()
        token['gross_delta']-=abs(quote['after'])-abs(quote['before'])
        if not closing:
            token['path'].pop()
        kind='resume' if token['discovery_left']>0 else 'finish'
        if kind=='resume':
            token['discovery_left']-=1
        self.emit(sender,kind,token)

    def prepare_local(self, transaction):
        if transaction['digest']!=digest_transaction(transaction) or transaction['gross_delta']>=0:
            return False
        path=transaction['path'];index=path.index(self.name)
        outgoing=transaction['quotes'][index];incoming=transaction['quotes'][index-1]
        if (outgoing['source']!=self.name or incoming['target']!=self.name
                or not self.quote_matches(outgoing,True,transaction['policy'])
                or not self.quote_matches(incoming,False,transaction['policy'])):
            return False
        peers={outgoing['target'],incoming['source']}
        if any(peer in state['changes'] for state in self.reservations.values() for peer in peers):
            return False
        changes={outgoing['target']:(outgoing['before'],outgoing['after']),
                 incoming['source']:(-incoming['before'],-incoming['after'])}
        self.reservations[transaction['id']]=dict(changes=changes,status='prepared')
        return True

    def commit_local(self, transaction):
        state=self.reservations[transaction['id']]
        if state['status']!='prepared':
            raise ValueError('Local unit commit must be prepared exactly once')
        for peer,(before,after) in state['changes'].items():
            if self.links[peer][0]!=before:
                raise ValueError('Reserved balance changed')
            self.links[peer][0]=after
        state['status']='committed'

    def receive(self, sender, kind, payload):
        if sender not in self.links:
            raise ValueError('Only authenticated direct neighbours may deliver messages')
        if kind in ('resume','finish'):
            if payload['path'][-1]!=self.name:
                raise ValueError('Wrong search return endpoint')
            return self.advance(payload) if kind=='resume' else self.finish(payload)
        if kind=='probe':
            quote=payload['quotes'][-1]
            closing=self.name==payload['path'][0]
            if quote['source']!=sender or quote['target']!=self.name:
                raise ValueError('Probe edge quote does not bind its sender')
            if not self.quote_matches(quote,False,payload['policy']):
                return self.reject_probe(sender,payload,closing)
            if not closing:
                if payload['path'][-1]!=self.name:
                    raise ValueError('Wrong probe path endpoint')
                return self.advance(payload)
            if (len(payload['path'])<3 or payload['gross_delta']>=0
                    or payload['gross_delta']!=sum(abs(q['after'])-abs(q['before']) for q in payload['quotes'])):
                return self.reject_probe(sender,payload,True)
            transaction={k:payload[k] for k in ('id','policy','path','quotes','gross_delta')}
            transaction['digest']=digest_transaction(transaction)
            transaction['prepared']=[]
            if not self.prepare_local(transaction):
                return self.complete('failed',transaction)
            transaction['prepared'].append(self.name)
            self.emit(transaction['path'][1],'prepare',transaction)
            return
        transaction=payload;path=transaction['path'];index=path.index(self.name)
        if transaction['digest']!=digest_transaction(transaction) or transaction['gross_delta']>=0:
            raise ValueError('Immutable cycle decision mismatch')
        expected_sender = (path[-1] if kind in ('ready','committed','done')
                           else (path[index+1] if kind=='abort' else path[index-1]))
        if sender!=expected_sender:
            raise ValueError('Cycle message is not from its bound neighbour')
        if kind=='prepare':
            if not self.prepare_local(transaction):
                self.emit(transaction['prepared'][-1],'abort',transaction)
                return
            transaction['prepared'].append(self.name)
            self.emit(path[(index+1)%len(path)],'ready' if index==len(path)-1 else 'prepare',transaction)
        elif kind=='abort':
            self.reservations.pop(transaction['id'],None)
            if transaction['prepared'].pop()!=self.name:
                raise ValueError('Prepare abort must unwind actual reservations')
            if transaction['prepared']:
                self.emit(transaction['prepared'][-1],'abort',transaction)
            else:
                self.complete('failed',transaction)
        elif kind=='ready':
            if index!=0 or transaction['prepared']!=path:
                raise ValueError('Incomplete cycle readiness')
            self.commit_local(transaction)
            self.emit(path[1],'commit',transaction)
        elif kind=='commit':
            self.commit_local(transaction)
            self.emit(path[(index+1)%len(path)],'committed' if index==len(path)-1 else 'commit',transaction)
        elif kind=='committed':
            if index!=0:
                raise ValueError('Completion must return to initiator')
            self.reservations.pop(transaction['id'])
            self.emit(path[1],'cleanup',transaction)
        elif kind=='cleanup':
            state=self.reservations.pop(transaction['id'])
            if state['status']!='committed':
                raise ValueError('Cannot release undecided reservation')
            self.emit(path[(index+1)%len(path)],'done' if index==len(path)-1 else 'cleanup',transaction)
        elif kind=='done':
            if index!=0:
                raise ValueError('Cleanup must return to initiator')
            self.complete('committed',transaction)
        else:
            raise ValueError('Unknown headroom message')


class Network:
    def __init__(self, edges, seed=0):
        self.actors={};self.edges=[];self.queue=deque();self.receipts=[];self.external=[]
        self.messages=0;self.delivered=0;self.message_bytes=0;self.by_kind=Counter();self.bytes_by_kind=Counter()
        self.message_records=[]
        self.moves=0;self.assisted_moves=0;self.serial=0;self.root_cursor=0;self._limit=None;self._result=None
        for a,b,balance,own,peer in edges:
            if a==b or (a,b) in self.edges or (b,a) in self.edges or type(balance) is not int:
                raise ValueError('Simple undirected trustlines and integer signed balances required')
            own=dict(validate_preferences(own));peer=dict(validate_preferences(peer))
            zone=shared_comfort(own,peer)
            if not zone['hard_min']<=balance<=zone['hard_max']:
                raise ValueError('Initial balance exceeds hard grants')
            self.edges.append((a,b))
            for name in (a,b):
                if name not in self.actors:
                    self.actors[name]=Actor(name,seed,self._send,self._complete)
            self.actors[a].links[b]=[balance,dict(own),dict(peer)]
            self.actors[b].links[a]=[-balance,dict(peer),dict(own)]
        self.initial_nets=self.nets()

    def _send(self, source, target, kind, payload):
        if target not in self.actors[source].links:
            raise ValueError('Transport destination is not a direct neighbour')
        if self._limit is not None and self.messages>=self._limit:
            raise AssertionError('Reserved settlement/cleanup quota was insufficient')
        raw=compact(dict(source=source,target=target,kind=kind,payload=payload))
        self.messages+=1;self.message_bytes+=len(raw);self.by_kind[kind]+=1;self.bytes_by_kind[kind]+=len(raw)
        self.message_records.append(dict(index=self.messages,source=source,target=target,kind=kind,
                                         bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        self.queue.append(raw)

    def _complete(self,status,payload):
        self._result=(status,payload)

    def snapshot(self):
        return [dict(source=a,target=b,balance=self.actors[a].links[b][0]) for a,b in self.edges]

    def nets(self):
        return {name:sum(link[0] for link in actor.links.values()) for name,actor in self.actors.items()}

    def score(self):
        gross=distance=empty=0
        for a,b in self.edges:
            balance,own,peer=self.actors[a].links[b];zone=shared_comfort(own,peer)
            gross+=abs(balance)
            if zone['empty']:
                empty+=1
            else:
                distance+=discomfort(balance,zone)
        return dict(debt=gross,gross_debt=gross,discomfort=distance,empty_zones=empty,messages=self.messages,
                    delivered_messages=self.delivered,message_bytes=self.message_bytes,moves=self.moves,
                    assisted_moves=self.assisted_moves,messages_by_kind=dict(self.by_kind),bytes_by_kind=dict(self.bytes_by_kind))

    def clear(self, policy, budget=250, max_hops=32):
        if policy not in POLICIES or type(budget) is not int or budget<0 or type(max_hops) is not int or max_hops<3:
            raise ValueError('Known policy, nonnegative additional message budget and path bound>=3 required')
        if self.queue or any(a.reservations for a in self.actors.values()):
            raise ValueError('Only one fully drained clearing call may be active')
        before=self.messages;self._limit=before+budget;roots=list(self.actors);failed=0
        while roots and failed<len(roots):
            remaining=self._limit-self.messages
            depth=min(max_hops,remaining//4)
            if depth<3:
                break
            root=roots[self.root_cursor%len(roots)];self.root_cursor+=1;self.serial+=1;self._result=None
            self.actors[root].start(str(self.serial),policy,remaining-3*depth,depth)
            while self.queue:
                wire=json.loads(self.queue.popleft());self.delivered+=1
                self.actors[wire['target']].receive(wire['source'],wire['kind'],wire['payload'])
            if self._result is None:
                raise AssertionError('Serial search did not terminate')
            status,payload=self._result
            if status=='committed':
                quotes=payload['quotes'];changes=[(q['source'],q['target'],q['before'],q['after']) for q in quotes]
                receipt=dict(id=payload['id'],policy=policy,changes=changes,gross_delta=payload['gross_delta'],
                             digest=payload['digest'],path=payload['path'])
                self.receipts.append(receipt);self.moves+=1
                self.assisted_moves+=any(abs(new)>abs(old) for _,_,old,new in changes)
                failed=0
            else:
                failed+=1
        if self.queue or any(a.reservations for a in self.actors.values()):
            raise AssertionError('Clearing returned with unfinished work')
        if self.messages>self._limit or self.messages!=self.delivered:
            raise AssertionError('Message-budget or exactly-once delivery accounting failed')
        used=self.messages-before;self._limit=None
        return dict(self.score(),used_messages=used,budget=budget,unused_budget=budget-used)

    def transfer(self,a,b,amount):
        if self.queue or any(actor.reservations for actor in self.actors.values()):
            raise ValueError('External arrivals must occur between drained service slots')
        if a not in self.actors or b not in self.actors[a].links or type(amount) is not int or amount==0:
            raise ValueError('Existing trustline and nonzero integer signed arrival required')
        balance,own,peer=self.actors[a].links[b];after=balance+amount;zone=shared_comfort(own,peer)
        if not zone['hard_min']<=after<=zone['hard_max']:
            return False
        self.actors[a].links[b][0]=after;self.actors[b].links[a][0]=-after
        self.external.append((a,b,amount))
        return True
