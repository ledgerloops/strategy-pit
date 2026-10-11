"""Concurrent signed residual discovery with endpoint-local fail-fast locks.

Research substrate: the same atomic pair posting/state adapter and lossy reliable
transport as temporal_episodes; no crashes, bounded-memory or atomic cycles.
Each prepare locks both incident pairs locally; any conflict aborts immediately.
Only the debtor writes its owned edge during staged commit.
"""
from dataclasses import dataclass, field
from copy import deepcopy
from distributed import Node, Token
from temporal_protocol import TemporalProtocol
from temporal_episodes import Episode, EpisodeMessage, EpisodeTemporalProtocol


@dataclass
class Search(Token):
    arcs: list = field(default_factory=list)
    tried: list = field(default_factory=lambda: [set()])


@dataclass
class Proposal:
    token: Search
    nodes: list
    arcs: list
    amount: int
    prepared: list = field(default_factory=list)
    proposed_at: int = 0


class ResidualNode(Node):
    def __init__(self, name, sim):
        super().__init__(name,sim)
        self.episodes = {}
        self.admitted_tokens = set()

    def capacity(self, peer, direction):
        ep = self.episodes.get(peer,Episode())
        if not ep.live:
            return 0
        if direction == 1:
            return max(ep.balance,0)
        return ep.ceiling + ep.balance if ep.balance < 0 and self.sim.restoration else 0

    def locked(self, peer):
        return any(dest == peer for dest,_ in self.reservations.values())

    def release(self, tx):
        for key in list(self.reservations):
            if key[0] == tx.token.ident:
                del self.reservations[key]
                self.sim.metrics['live_reservations'] -= 1

    def fail(self, tx):
        self.sim.metrics['aborted'] += 1
        if tx.prepared:
            self.sim.send(self.name,tx.prepared[-1],'habort',tx)
        else:
            self.sim.send(self.name,tx.token.path[-1],'hfinish',tx.token)

    def finish(self, token):
        assert token.path[-1] == self.name
        if len(token.path)>1:
            token.path.pop()
            self.sim.send(self.name,token.path[-1],'hfinish',token)
        else:
            self.active = False

    def receive(self, kind, payload):
        if isinstance(payload,EpisodeMessage):
            msg,payload = payload,payload.payload
            token = payload.token if hasattr(payload,'token') else payload
            if kind in ('hstep','hprepare'):
                ep=self.episodes.get(msg.source,Episode())
                if not ep.live or (ep.number,ep.revision)!=(msg.episode,msg.revision):
                    self.sim.metrics['stale_episode_rejections'] += 1
                    self.finish(payload) if kind=='hstep' else self.fail(payload)
                    return
                self.admitted_tokens.add(token.ident)
            elif token.ident not in self.admitted_tokens:
                self.sim.metrics['unknown_control_rejections'] += 1
                return
        if kind=='wake':
            if not self.sim.searches_enabled:
                return
            self.sim.schedule(self.sim.time+self.sim.retry_interval+self.sim.random.randrange(self.sim.retry_interval),self.name,'wake',None)
            if self.active or not any(self.capacity(p,d) and not self.locked(p) for p in self.episodes for d in (1,-1)):
                return
            self.active=True
            self.sequence+=1
            self.sim.metrics['searches']+=1
            self.receive('hstep',Search((self.name,self.sequence),[self.name],{self.name}))
        elif kind=='hstep':
            self.admitted_tokens.add(payload.ident)
            self.search(payload)
        elif kind=='hfinish':
            self.finish(payload)
        elif kind=='hprepare':
            tx=payload
            if len(tx.nodes)<3 or len(set(tx.nodes))!=len(tx.nodes) or sum(a[2] for a in tx.arcs)<=0 or tx.amount<=0:
                self.fail(tx)
                return
            i=tx.nodes.index(self.name)
            outgoing,incoming=tx.arcs[i],tx.arcs[(i-1)%len(tx.arcs)]
            # Incoming residual direction is reversed at this endpoint.
            incidences=[(outgoing[1],outgoing[2],outgoing[4:6]),
                        (incoming[0],-incoming[2],incoming[4:6])]
            valid=True
            capacities=[]
            for peer,direction,quote in incidences:
                ep=self.episodes.get(peer,Episode())
                capacity=self.capacity(peer,direction)
                # Incoming incidence checks the same arc from its other end.
                if peer==incoming[0]:
                    capacity=(max(-ep.balance,0) if incoming[2]==1 else
                              ep.ceiling-ep.balance if ep.balance>0 else 0)
                valid &= ep.live and (ep.number,ep.revision)==tuple(quote) and not self.locked(peer) and capacity>0
                capacities.append(capacity)
            if not valid:
                self.sim.metrics['prepare_conflicts']+=1
                self.fail(tx)
                return
            tx.amount=min(tx.amount,*capacities)
            for peer,_,_ in incidences:
                self.reservations[(tx.token.ident,peer)]=(peer,tx.amount)
                self.sim.metrics['live_reservations']+=1
            self.sim.metrics['max_reservations']=max(self.sim.metrics['max_reservations'],self.sim.metrics['live_reservations'])
            tx.prepared.append(self.name)
            self.sim.send(self.name,outgoing[1],'hcommit' if len(tx.prepared)==len(tx.nodes) else 'hprepare',tx)
        elif kind=='habort':
            tx=payload
            self.release(tx)
            assert tx.prepared.pop()==self.name
            if tx.prepared:
                self.sim.send(self.name,tx.prepared[-1],'habort',tx)
            else:
                self.sim.send(self.name,tx.token.path[-1],'hfinish',tx.token)
        elif kind=='hcommit':
            tx=payload
            ident=tx.token.ident
            if ident in self.committed:
                self.sim.metrics['duplicate_commit_receipts']+=1
                return
            i=tx.nodes.index(self.name)
            outgoing,incoming=tx.arcs[i],tx.arcs[(i-1)%len(tx.arcs)]
            if not all((ident,peer) in self.reservations for peer in (outgoing[1],incoming[0])):
                self.sim.metrics['unknown_control_rejections']+=1
                return
            for arc in (outgoing,incoming):
                a,b,direction=arc[:3]
                owner,peer=(a,b) if direction==1 else (b,a)
                if owner==self.name:
                    delta=-direction*tx.amount
                    ep=self.episodes[peer]
                    assert ep.live and 0<=self.outgoing[peer]+delta<=ep.ceiling
                    self.outgoing[peer]+=delta
                    self.sim.record_ledger('commit',self.name,peer,delta,ident)
            self.committed.add(ident)
            self.release(tx)
            if i+1<len(tx.nodes):
                self.sim.send(self.name,outgoing[1],'hcommit',tx)
            else:
                gain=sum(a[2] for a in tx.arcs)*tx.amount
                self.sim.metrics['cleared']+=gain
                self.sim.metrics['cycles']+=1
                self.sim.metrics['restored_volume']+=sum(a[2]==-1 for a in tx.arcs)*tx.amount
                self.sim.metrics['mixed_cycles']+=any(a[2]==-1 for a in tx.arcs)
                self.sim.cycles.append((list(tx.nodes),tx.amount))
                self.sim.cycle_records.append(dict(nodes=list(tx.nodes),amount=tx.amount,directions=[a[2] for a in tx.arcs],time=self.sim.time,proposed_at=tx.proposed_at,duration=self.sim.time-tx.proposed_at))
                self.finish(tx.token)
        else:
            raise ValueError(kind)

    def search(self, token):
        if token.hops>=self.sim.search_budget:
            self.finish(token)
            return
        candidates=[(p,d) for p in self.episodes for d in (1,-1) if (p,d) not in token.tried[-1] and self.capacity(p,d)>0 and not self.locked(p)]
        self.sim.random.shuffle(candidates)
        for peer,direction in candidates:
            token.tried[-1].add((peer,direction))
            ep=self.episodes[peer]
            arc=(self.name,peer,direction,self.capacity(peer,direction),ep.number,ep.revision)
            if peer in token.path:
                start=token.path.index(peer)
                arcs=token.arcs[start:]+[arc]
                if len(arcs)<3 or sum(a[2] for a in arcs)<=0:
                    continue
                tx=Proposal(token,token.path[start:],arcs,min(a[3] for a in arcs),proposed_at=self.sim.time)
                self.sim.metrics['proposals']+=1
                self.sim.send(self.name,peer,'hprepare',tx)
                return
            if len(token.path)<self.sim.max_hops:
                token.path.append(peer);token.arcs.append(arc);token.tried.append(set())
                token.visited.add(peer);token.hops+=1
                self.sim.send(self.name,peer,'hstep',token)
                return
        if len(token.path)>1:
            token.path.pop();token.arcs.pop();token.tried.pop();token.hops+=1
            self.sim.send(self.name,token.path[-1],'hstep',token)
        else:
            self.active=False
            self.sim.metrics['exhausted_searches']+=1


class ConcurrentHeadroom(EpisodeTemporalProtocol):
    def __init__(self,*args,restoration=True,**kwargs):
        self.restoration=restoration
        super().__init__(*args,**kwargs)

    def _post(self,a,b,amount,requested):
        for name in (a,b):
            if name not in self.nodes:
                self.nodes[name]=ResidualNode(name,self)
                if self.searches_enabled:
                    self.schedule(self.time+self.random.randrange(self.retry_interval),name,'wake',None)
        super()._post(a,b,amount,requested)

    def send(self,source,dest,kind,payload):
        actor=self.nodes[source]
        ep=actor.episodes.get(dest,Episode())
        token=payload.token if hasattr(payload,'token') else payload
        actor.admitted_tokens.add(token.ident)
        TemporalProtocol.send(self,source,dest,kind,EpisodeMessage(source,ep.number,ep.revision,deepcopy(payload)))
