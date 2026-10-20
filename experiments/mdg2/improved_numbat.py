"""Objective-scored closure experiment on unchanged Numbat settlement.

When the received DFS token already exposes a locally closable cycle, select the
closure with greatest observed gross debt reduction (cycle length times observed
bottleneck). Prefer a shorter cycle on equal scores, then the neighbour identity.
When no closure exists, use unchanged exponent-four Numbat exploration.

Only this actor's outgoing balances/reservations and the received token enter the
choice. Historical capacity hints may be stale: unchanged prepare/commit recheck
and reserve actual capacities. This adds no credit or restoration. It retains
path-bearing research tokens, honest actors, exactly-once delivery, debtor-owned
balances and staged commits; it is not the neighbour-private product app.

The MDG2 baseline files and original result artifacts are deliberately unchanged.
"""
from __future__ import annotations

from pathlib import Path
import sys

EXPERIMENTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXPERIMENTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from distributed import Transaction
from numbat import NumbatNode
from ledgerloops_benchmark import JsonNumbat

VARIANT = 'numbat-objective-closure-v1'


class ObjectiveClosureNode(NumbatNode):
    def receive(self, kind, payload):
        if kind != 'step' or payload.hops >= self.sim.search_budget:
            return super().receive(kind, payload)
        token = payload
        if not hasattr(token, 'capacities'):
            token.capacities = []
        if len(token.capacities) != len(token.path)-1:
            raise ValueError('Numbat capacity hints must match the received path')
        ranked = []
        for neighbor in self.outgoing:
            available = self.available(neighbor)
            if available <= 0 or neighbor not in token.path:
                continue
            start = token.path.index(neighbor)
            length = len(token.path)-start
            if length < 3:
                continue
            bottleneck = min([available] + token.capacities[start:])
            # All inputs belong to this node or the received neighbour message.
            ranked.append((-length*bottleneck, length, neighbor, start, bottleneck))
        if not ranked:
            return super().receive(kind, token)
        _, _, neighbor, start, amount = min(ranked)
        transaction = Transaction(token, token.path[start:], amount, proposed_at=self.sim.time)
        self.sim.metrics['proposals'] += 1
        self.sim.metrics['objective_closure_proposals'] += 1
        self.sim.send(self.name, neighbor, 'prepare', transaction)


class ImprovedNumbat(JsonNumbat):
    """Fresh node-local variant using the frozen JSON transport and fixed caps."""
    def __init__(self, graph=None, **kwargs):
        if kwargs.get('snapshot_capacity', True) is not True:
            raise ValueError('Objective closure requires observed bottleneck hints')
        if kwargs.get('close_first', False) is not False:
            raise ValueError('Objective closure owns closure ordering; do not combine close_first')
        super().__init__(graph, **kwargs)

    def add_edge(self, a, b, amount, at=None):
        super().add_edge(a, b, amount, at)
        if at is None:
            for name in (a, b):
                self.nodes[name].__class__ = ObjectiveClosureNode
