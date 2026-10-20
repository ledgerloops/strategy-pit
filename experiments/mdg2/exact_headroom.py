"""Exact static admissible unit-cycle research search over neighbour messages.

A fixed coordinator and the node count are supplied, but no actor knows the
credit graph. A counted echo flood establishes a control tree. Synchronous
Bellman--Ford rounds send prior-round distances and simple witness paths over
all neighbour channels; counted tree reports select a received negative-cycle
witness. The cycle collects real local quotes, then uses the unchanged bilateral
prepare/commit/cleanup protocol from comfort_headroom.py. Financial work is
serialized and arrivals may be posted only between fully drained clear calls.

No changing distance after a complete round certifies nonnegative reduced cost
on every currently admissible residual arc. Under broad all-opt-in comfort this
certifies the hard-bound minimum gross debt. Narrow comfort certifies absence of
an admissible improving unit cycle at the current state, not the relaxed global
hard-bound optimum or initial preference-constrained reachability.

Paths and costs are disclosed. Known membership count, a coordinator, reliable
exactly-once delivery, barriers, stable preferences/topology and buffered external
arrivals are explicit research assumptions, not product privacy/consensus/crash
recovery guarantees. Every control/search/settlement message is JSON serialized.
"""
from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from comfort_headroom import Actor,Network,compact,digest_transaction

VARIANT='exact-admissible-unit-bellman-ford-v1'


def choose(left,right):
    if left is None:return right
    if right is None:return left
    return min((left,right),key=compact)


def canonical_cycle(path,costs):
    if len(path)<3 or len(set(path))!=len(path) or len(path)!=len(costs) or sum(costs)>=0:
        return None
    rotations=[]
    for index,cost in enumerate(costs):
        if cost<0:
            rotations.append(dict(path=path[index:]+path[:index],costs=costs[index:]+costs[:index]))
    return min(rotations,key=compact)


class ExactActor(Actor):
    def initialize_exact(self):
        self.observer=self.complete
        self.complete=self.protocol_complete
        self.parent=None;self.children=[];self.tree_seen=False;self.tree_pending=set()
        self.tree_ready=False;self.tree_count=0;self.degree_sum=0
        self.epoch=None;self.distance=0;self.witness=[self.name];self.costs=[];self.round_states={}
        self.last_rows=[];self.last_report=None

    def protocol_complete(self,status,payload):
        report=dict(status=status,transaction=payload)
        if self.parent is None:self.observer(status,payload)
        else:self.emit(self.parent,'settled_report',report)

    def begin_tree(self,parent=None):
        self.tree_seen=True;self.parent=parent;self.children=[]
        self.tree_pending=set(self.links)-({parent} if parent is not None else set())
        self.tree_count=1;self.degree_sum=len(self.links)
        for peer in self.links:
            if peer in self.tree_pending:self.emit(peer,'tree_probe',{})
        self.finish_tree()

    def finish_tree(self):
        if self.tree_pending or self.tree_ready:return
        self.tree_ready=True
        report=dict(accepted=True,nodes=self.tree_count,degree_sum=self.degree_sum)
        if self.parent is None:self.observer('tree_ready',report)
        else:self.emit(self.parent,'tree_ack',report)

    def state(self,epoch,round_number):
        key=(epoch,round_number)
        if key not in self.round_states:
            self.round_states[key]=dict(packets={},children={},started=False,finalized=False,reported=False)
        return self.round_states[key]

    def start_round(self,epoch,round_number,policy):
        state=self.state(epoch,round_number)
        if state['started']:raise ValueError('Round was started twice')
        if self.epoch!=epoch:
            self.epoch=epoch;self.distance=0;self.witness=[self.name];self.costs=[]
            self.round_states={(epoch,round_number):state}
        state.update(started=True,policy=policy,old_distance=self.distance)
        for child in self.children:
            self.emit(child,'bf_start',dict(epoch=epoch,round=round_number,policy=policy))
        for peer,(before,_,_) in self.links.items():
            eligible=self.allowed(peer,1,policy)
            self.emit(peer,'bf_relax',dict(epoch=epoch,round=round_number,policy=policy,
                distance=self.distance,path=self.witness,costs=self.costs,eligible=eligible,
                cost=abs(before+1)-abs(before) if eligible else None))
        self.finish_round(epoch,round_number)

    def finish_round(self,epoch,round_number):
        state=self.state(epoch,round_number)
        if not state['started'] or len(state['packets'])!=len(self.links):return
        if not state['finalized']:
            old=state['old_distance'];best=old;best_path=self.witness;best_costs=self.costs;candidate=None
            for sender,packet in state['packets'].items():
                path,costs=packet['path'],packet['costs']
                if (path[-1]!=sender or len(set(path))!=len(path) or len(costs)!=len(path)-1
                        or sum(costs)!=packet['distance']):
                    raise ValueError('Invalid Bellman-Ford path witness')
                if not packet['eligible']:continue
                local=self.links[sender][0]
                expected=abs(local-1)-abs(local)
                if not self.allowed(sender,-1,state['policy']) or packet['cost']!=expected:
                    raise ValueError('Neighbour residual eligibility/cost disagrees with local mirror')
                proposed=packet['distance']+packet['cost']
                if self.name in path:
                    start=path.index(self.name)
                    candidate=choose(candidate,canonical_cycle(path[start:],costs[start:]+[packet['cost']]))
                    # A nonnegative repeated suffix cannot strictly improve this
                    # endpoint's monotone distance. Negative suffixes are elected.
                    continue
                new_path=path+[self.name];new_costs=costs+[packet['cost']]
                if proposed<best or (proposed==best and proposed<old and compact(new_path)<compact(best_path)):
                    best,best_path,best_costs=proposed,new_path,new_costs
            self.distance,self.witness,self.costs=best,list(best_path),list(best_costs)
            rows=[]
            for peer,(before,_,_) in self.links.items():
                eligible=self.allowed(peer,1,state['policy']);other=state['packets'][peer]['distance']
                cost=abs(before+1)-abs(before)
                rows.append(dict(peer=peer,before=before,after=before+1,eligible=eligible,cost=cost,
                                 peer_potential=other,reduced_cost=cost+best-other))
            reduced=[r['reduced_cost'] for r in rows if r['eligible']]
            state.update(finalized=True,local=dict(nodes=1,changed=int(best<old),candidate=candidate,
                         min_reduced_cost=min(reduced) if reduced else None))
            self.last_rows=rows
        if state['reported'] or len(state['children'])!=len(self.children):return
        report=dict(state['local'])
        for child_report in state['children'].values():
            report['nodes']+=child_report['nodes'];report['changed']+=child_report['changed']
            report['candidate']=choose(report['candidate'],child_report['candidate'])
            values=[x for x in (report['min_reduced_cost'],child_report['min_reduced_cost']) if x is not None]
            report['min_reduced_cost']=min(values) if values else None
        state['reported']=True;self.last_report=report
        data=dict(epoch=epoch,round=round_number,report=report)
        if self.parent is None:self.observer('bf_round',data)
        else:self.emit(self.parent,'bf_report',data)

    def select_cycle(self,data):
        for child in self.children:self.emit(child,'bf_select',data)
        candidate=data['candidate'];path=candidate['path']
        if self.name!=path[0]:return
        if candidate['costs'][0]>=0 or len(path)<3:raise ValueError('Cycle initiator must reduce its debt')
        transaction=dict(id='exact-'+str(data['epoch']),policy=data['policy'],path=path,quotes=[],gross_delta=0)
        self.collect_quote(transaction)

    def collect_quote(self,transaction):
        path=transaction['path'];index=path.index(self.name)
        if len(transaction['quotes'])!=index:raise ValueError('Quote collection must visit cycle in order')
        peer=path[(index+1)%len(path)]
        if not self.allowed(peer,1,transaction['policy']):raise ValueError('Static cycle became ineligible')
        quote=self.quote(peer);transaction['quotes'].append(quote)
        transaction['gross_delta']+=abs(quote['after'])-abs(quote['before'])
        self.emit(peer,'quote_ready' if index==len(path)-1 else 'quote_collect',transaction)

    def broadcast_certificate(self,data):
        self.certificate_epoch=data['epoch']
        for child in self.children:self.emit(child,'bf_certificate',data)

    def receive(self,sender,kind,payload):
        if sender not in self.links:raise ValueError('Unknown direct neighbour')
        if kind=='tree_probe':
            if self.tree_seen:self.emit(sender,'tree_ack',dict(accepted=False,nodes=0,degree_sum=0))
            else:self.begin_tree(sender)
        elif kind=='tree_ack':
            if sender not in self.tree_pending:raise ValueError('Unsolicited tree acknowledgment')
            self.tree_pending.remove(sender)
            if payload['accepted']:
                self.children.append(sender);self.tree_count+=payload['nodes'];self.degree_sum+=payload['degree_sum']
            self.finish_tree()
        elif kind=='bf_start':
            if sender!=self.parent:raise ValueError('Round start must use the control parent')
            self.start_round(payload['epoch'],payload['round'],payload['policy'])
        elif kind=='bf_relax':
            state=self.state(payload['epoch'],payload['round'])
            if sender in state['packets']:raise ValueError('Duplicate exactly-once relaxation')
            state['packets'][sender]=payload
            self.finish_round(payload['epoch'],payload['round'])
        elif kind=='bf_report':
            if sender not in self.children:raise ValueError('Round report must use a control child')
            state=self.state(payload['epoch'],payload['round'])
            if sender in state['children']:raise ValueError('Duplicate round report')
            state['children'][sender]=payload['report']
            self.finish_round(payload['epoch'],payload['round'])
        elif kind=='bf_select':
            if sender!=self.parent:raise ValueError('Cycle selection must use the control parent')
            self.select_cycle(payload)
        elif kind=='quote_collect':
            index=payload['path'].index(self.name)
            if sender!=payload['path'][index-1]:raise ValueError('Wrong quote predecessor')
            self.collect_quote(payload)
        elif kind=='quote_ready':
            if self.name!=payload['path'][0] or sender!=payload['path'][-1] or payload['gross_delta']>=0:
                raise ValueError('Non-improving or malformed exact candidate')
            payload['digest']=digest_transaction(payload);payload['prepared']=[]
            if not self.prepare_local(payload):raise ValueError('Static exact root quote was refused')
            payload['prepared'].append(self.name);self.emit(payload['path'][1],'prepare',payload)
        elif kind=='settled_report':
            if sender not in self.children:raise ValueError('Settlement report must follow the control tree')
            if self.parent is None:self.observer(payload['status'],payload['transaction'])
            else:self.emit(self.parent,'settled_report',payload)
        elif kind=='bf_certificate':
            if sender!=self.parent:raise ValueError('Certificate must use the control parent')
            self.broadcast_certificate(payload)
        else:return super().receive(sender,kind,payload)


class ExactNetwork(Network):
    def __init__(self,edges,seed=0,message_sample_limit=256):
        super().__init__(edges,seed)
        self.message_sample_limit=message_sample_limit
        self.coordinator=next(iter(self.actors),None);self.known_nodes=len(self.actors)
        self.search_rounds=0;self.epoch_serial=0;self.last_certificate=None
        for actor in self.actors.values():
            actor.__class__=ExactActor;actor.initialize_exact()

    def _send(self,source,target,kind,payload):
        if target not in self.actors[source].links:raise ValueError('Non-neighbour transport')
        if self._limit is not None and self.messages>=self._limit:
            raise AssertionError('Exact phase admission underestimated its message reserve')
        raw=compact(dict(source=source,target=target,kind=kind,payload=payload))
        self.messages+=1;self.message_bytes+=len(raw);self.by_kind[kind]+=1;self.bytes_by_kind[kind]+=len(raw)
        if len(self.message_records)<self.message_sample_limit:
            self.message_records.append(dict(index=self.messages,source=source,target=target,kind=kind,
                bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        self.queue.append(raw)

    def drain_messages(self):
        import json
        while self.queue:
            data=json.loads(self.queue.popleft());self.delivered+=1
            self.actors[data['target']].receive(data['source'],data['kind'],data['payload'])

    def score(self):
        score=super().score()
        categories={
            'tree_setup':{'tree_probe','tree_ack'},
            'relaxations':{'bf_relax'},
            'round_coordination':{'bf_start','bf_report'},
            'candidate_coordination':{'bf_select','quote_collect','quote_ready','settled_report'},
            'settlement':{'prepare','ready','commit','committed','cleanup','done','abort'},
            'certificate_broadcast':{'bf_certificate'}}
        score.update(search_rounds=self.search_rounds,
            phase_messages={phase:sum(self.by_kind[k] for k in kinds) for phase,kinds in categories.items()},
            phase_bytes={phase:sum(self.bytes_by_kind[k] for k in kinds) for phase,kinds in categories.items()},
            sampled_messages=len(self.message_records),message_sample_limit=self.message_sample_limit,
            message_sample_truncated=self.messages>len(self.message_records))
        return score

    def transfer(self,a,b,amount):
        accepted=super().transfer(a,b,amount)
        if accepted:self.last_certificate=None
        return accepted

    def clear_exact(self,message_limit=2_000_000,policy='comfort_headroom'):
        if type(message_limit) is not int or message_limit<0 or policy not in ('comfort_headroom','cancellation'):
            raise ValueError('Nonnegative additional message cap and known policy required')
        if self.queue or any(a.reservations for a in self.actors.values()):
            raise ValueError('Exact calls require drained epoch boundaries')
        before=self.messages;rounds_before=self.search_rounds;moves_before=self.moves
        self._limit=before+message_limit;setup=0;certificate=None;status='budget_exhausted';reason='phase_admission'
        n=self.known_nodes
        if n==0:
            status='certified';certificate=dict(policy=policy,known_nodes=0,reported_nodes=0,potentials={},nodes=[],min_reduced_cost=0,epoch=0,round=0)
        else:
            coordinator=self.actors[self.coordinator]
            if not coordinator.tree_ready:
                # Membership count gives a graph-independent safe flood bound.
                if self._limit-self.messages>=2*n*(n-1):
                    old=self.messages;self._result=None;coordinator.begin_tree();self.drain_messages();setup=self.messages-old
                    if self._result[0]!='tree_ready' or self._result[1]['nodes']!=n:
                        raise ValueError('Known membership must be connected to the coordinator')
                else:reason='insufficient_tree_setup_quota'
            while coordinator.tree_ready:
                self.epoch_serial+=1;epoch=self.epoch_serial;found=False
                round_bound=coordinator.degree_sum+2*(n-1)
                for round_number in range(1,n+1):
                    if self._limit-self.messages<round_bound+6*n:
                        reason='insufficient_round_and_settlement_quota';break
                    self._result=None;coordinator.start_round(epoch,round_number,policy);self.drain_messages()
                    self.search_rounds+=1
                    if self._result is None or self._result[0]!='bf_round':raise AssertionError('Round did not reach its counted barrier')
                    report=self._result[1]['report']
                    if report['nodes']!=n:raise AssertionError('Round report omitted membership')
                    if report['candidate'] is not None:
                        self._result=None
                        coordinator.select_cycle(dict(epoch=epoch,policy=policy,candidate=report['candidate']))
                        self.drain_messages()
                        if self._result is None or self._result[0]!='committed':raise AssertionError('Static exact settlement failed')
                        transaction=self._result[1]
                        changes=[(q['source'],q['target'],q['before'],q['after']) for q in transaction['quotes']]
                        self.receipts.append(dict(id=transaction['id'],policy=policy,path=transaction['path'],changes=changes,
                            gross_delta=transaction['gross_delta'],digest=transaction['digest']))
                        self.moves+=1;self.assisted_moves+=any(abs(new)>abs(old) for _,_,old,new in changes)
                        found=True;break
                    if report['changed']==0:
                        minimum=report['min_reduced_cost']
                        if minimum is not None and minimum<0:raise AssertionError('Invalid reduced-cost certificate')
                        coordinator.broadcast_certificate(dict(epoch=epoch,policy=policy,round=round_number))
                        self.drain_messages()
                        # Observational audit export only; acceptance above used
                        # solely the coordinator's received scalar echo report.
                        potentials={name:actor.distance for name,actor in self.actors.items()}
                        certificate=dict(epoch=epoch,round=round_number,policy=policy,known_nodes=n,reported_nodes=report['nodes'],
                            min_reduced_cost=minimum if minimum is not None else 0,potentials=potentials,
                            nodes=[dict(node=name,potential=actor.distance,outgoing=actor.last_rows) for name,actor in self.actors.items()])
                        status='certified';reason=None;break
                else:raise AssertionError('N strict Bellman-Ford rounds without a negative-cycle witness')
                if status=='certified' or not found:break
        if self.queue or any(a.reservations for a in self.actors.values()):raise AssertionError('Exact call left in-flight financial work')
        if self.messages>self._limit or self.messages!=self.delivered:raise AssertionError('Exact budget/delivery accounting failed')
        self._limit=None;self.last_certificate=certificate
        return dict(status=status,certified=status=='certified',reason=reason,used_messages=self.messages-before,
            budget=message_limit,unused_budget=message_limit-(self.messages-before),setup_messages=setup,
            rounds=self.search_rounds-rounds_before,cycles=self.moves-moves_before,certificate=certificate,
            potentials=certificate['potentials'] if certificate else None,quiescent=True,pending_messages=0,pending_reservations=0,
            score=self.score(),certificate_scope='no admissible negative unit cycle',
            global_optimality_requires='Broad all-opt-in comfort spanning the hard interval; independently certify the hard-L1 reference.')
