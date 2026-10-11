"""Fixed 50/50 local exploration mixture for temporal Numbat.

At each search step, a local coin chooses uniform neighbour ordering or Numbat's
power-four capacity ordering. All observations, path hints and settlement behavior
remain unchanged. This is one preregistered hypothesis, not a parameter sweep.
TemporalProtocol's existing reliability and non-atomic settlement assumptions apply.
"""
import math
from distributed import Transaction
from numbat import NumbatNode
from temporal_protocol import TemporalProtocol, LedgerObserver


class ExplorationNode(NumbatNode):
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
        # Exponential races produce weighted sampling without replacement.
        # alpha=0 is uniform; finite alpha retains exploration unlike largest.
        if self.sim.random.random() < 0.5:
            self.sim.random.shuffle(candidates)
        else:
            candidates.sort(key=lambda n: math.log(-math.log(max(self.sim.random.random(), 1e-300))) -
                            self.sim.capacity_power * math.log(self.available(n)))
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

class TemporalExplorationNode(LedgerObserver, ExplorationNode):
    pass


class ExplorationTemporalProtocol(TemporalProtocol):
    def __init__(self, *args, **kwargs):
        if kwargs.pop('algorithm', 'numbat') != 'numbat':
            raise ValueError('exploration variant requires Numbat settlement')
        super().__init__(*args, algorithm='numbat', **kwargs)

    def _post(self, a, b, amount, requested):
        super()._post(a, b, amount, requested)
        # Adapter initialization only: inspect the two externally named endpoints.
        # No global graph access selects an exploration route.
        for name in (a, b):
            self.nodes[name].__class__ = TemporalExplorationNode
