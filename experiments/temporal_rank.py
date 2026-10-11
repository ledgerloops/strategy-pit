"""One local dense-rank-weighted Numbat variant on strict episodes."""
import math
from distributed import Transaction
from numbat import NumbatNode
from temporal_protocol import LedgerObserver
from temporal_episodes import EpisodeNode, EpisodeTemporalProtocol


def dense_ranks(capacities):
    ranks = {amount: rank for rank, amount in enumerate(sorted(set(capacities.values())), 1)}
    return {neighbor: ranks[amount] for neighbor, amount in capacities.items()}


class RankNode(NumbatNode):
    def receive(self, kind, payload):
        if kind != 'step':
            return super().receive(kind, payload)
        token = payload
        if not hasattr(token, 'capacities'):
            token.capacities = []
        if token.hops >= self.sim.search_budget:
            self.finish(token)
            return
        candidates = [n for n in self.outgoing if self.available(n) > 0 and
                      (n not in token.visited or
                       (n in token.path and len(token.path) - token.path.index(n) >= 3))]
        # Equal balances share a dense ascending rank. Exponential races
        # select weighted order without replacement, preserving exploration.
        ranks = dense_ranks({n: self.available(n) for n in candidates})
        candidates.sort(key=lambda n: math.log(-math.log(max(self.sim.random.random(), 1e-300))) -
                        math.log(ranks[n]))
        if self.sim.close_first:
            candidates.sort(key=lambda n: n not in token.path)
        for neighbor in candidates:
            if neighbor in token.path:
                nodes = token.path[token.path.index(neighbor):]
                amount = self.available(neighbor)
                if self.sim.snapshot_capacity:
                    amount = min([amount] + token.capacities[token.path.index(neighbor):])
                tx = Transaction(token, nodes, amount, proposed_at=self.sim.time)
                self.sim.metrics['proposals'] += 1
                self.sim.send(self.name, neighbor, 'prepare', tx)
                return
            if len(token.path) < self.sim.max_hops:
                if self.sim.snapshot_capacity:
                    token.capacities.append(self.available(neighbor))
                token.path.append(neighbor)
                token.visited.add(neighbor)
                token.hops += 1
                self.sim.send(self.name, neighbor, 'step', token)
                return
        if len(token.path) > 1:
            token.path.pop()
            if token.capacities:
                token.capacities.pop()
            token.hops += 1
            self.sim.send(self.name, token.path[-1], 'step', token)
        else:
            self.active = False
            self.sim.metrics['exhausted_searches'] += 1


class EpisodeRankNode(EpisodeNode, LedgerObserver, RankNode):
    pass


class RankTemporalProtocol(EpisodeTemporalProtocol):
    def __init__(self,*args,**kwargs):
        if kwargs.pop('algorithm','numbat')!='numbat':
            raise ValueError('Rank variant uses Numbat capacity hints and settlement')
        super().__init__(*args,algorithm='numbat',**kwargs)

    def _post(self,a,b,amount,requested):
        for name in (a,b):
            if name not in self.nodes:
                self.nodes[name]=EpisodeRankNode(name,self)
                if self.searches_enabled:
                    self.schedule(self.time+self.random.randrange(self.retry_interval),name,'wake',None)
        super()._post(a,b,amount,requested)
