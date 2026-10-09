"""Numbat: local weighted DFS experiments on DistributedDFS's settlement protocol.

The scheduler records results only. Decisions use this node's outgoing balances,
its reservations and the received token. No graph-wide choices are made.

Capacity-weighted sampling retains exploration; observed path bottlenecks reduce
provisional overreservation. Every capacity is rechecked during prepare. Default
power four was selected on synthetic training seeds 101 and 102, before held-out
evaluation. The algorithm inherits reliable exactly-once delivery, honest peers,
no-crash assumptions and non-atomic in-flight commit from DistributedDFS. Tokens
reveal their paths, visited nodes and observed capacities to participants. Shared
simulator RNG supplies local random draws and network delays; it contains no
credit-graph information. This is a research simulator, not a payment protocol.
"""
from __future__ import annotations

import math
from distributed import DistributedDFS, Node, Transaction


class NumbatNode(Node):
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

    def finish(self, token):
        if len(token.path) > 1 and getattr(token, 'capacities', None):
            token.capacities.pop()
        return super().finish(token)


class Numbat(DistributedDFS):
    def __init__(self, graph=None, *, capacity_power=4., close_first=False, snapshot_capacity=True, **kwargs):
        if not math.isfinite(capacity_power) or capacity_power < 0:
            raise ValueError('capacity_power must be nonnegative')
        self.snapshot_capacity = snapshot_capacity
        self.capacity_power, self.close_first = capacity_power, close_first
        super().__init__(graph, **kwargs)

    def send(self, source, dest, kind, payload):
        token = payload.token if isinstance(payload, Transaction) else payload
        # Extra scalar payload beyond the baseline; node-ID count is not bytes.
        self.metrics['message_capacity_values'] += len(getattr(token, 'capacities', ()))
        return super().send(source, dest, kind, payload)

    def add_edge(self, a, b, amount, at=None):
        super().add_edge(a, b, amount, at)
        if at is None:
            for name in (a, b):
                if not isinstance(self.nodes[name], NumbatNode):
                    # The base constructor only allocated fresh, unused nodes.
                    # Change their behavior while preserving their local state.
                    self.nodes[name].__class__ = NumbatNode
