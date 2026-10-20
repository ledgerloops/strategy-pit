"""Bounded successful-cycle continuation on close-first Numbat.

After the final commit has applied, return over the direct closing-neighbour
channel to the first cycle node and resume the retained search prefix there.
This preserves the original search root's active flag until ordinary finish.
Each continuation receives a fresh transaction identifier from the closer's own
monotonic sequence counter; its issuer can differ from token.path[0]. Old commit
records retain their original token and identifier.

A continuation costs the cycle length against the existing search-hop budget.
The standard search-admission flag suppresses continuations after the common
horizon or message cutoff; ordinary finish then drains all admitted work. No
routing choice uses remote state, a global graph, or instrumentation counters.

The one return step is in-flight control traffic over an admitted acquaintance
channel, even if settlement has just reduced that relationship to zero. Normal
forward choices still require strictly positive local available debt. This is
an explicit static control-message grace, not evidence of compatibility with
strict dynamic channel episodes. The simulator retains path/capacity disclosure,
debtor-owned balances, honest participants and staged commits: not the private
product app, replicated bilateral agreement, or crash recovery.
"""
from __future__ import annotations

from pathlib import Path
import sys

EXPERIMENTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXPERIMENTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from distributed import Token
from numbat import NumbatNode
from ledgerloops_benchmark import JsonNumbat

VARIANT = 'numbat-close-first-continuation-v1'


class ContinuationNode(NumbatNode):
    def receive(self, kind, payload):
        final_commit = (kind == 'commit' and self.name == payload.nodes[-1]
                        and payload.token.ident not in self.committed)
        if not final_commit:
            return super().receive(kind, payload)
        previous = getattr(self, '_completed_cycle', None)
        self._completed_cycle = payload
        try:
            # The inherited handler applies the last edge, records the complete
            # cycle, then invokes our finish hook. No reservation is bypassed.
            return super().receive(kind, payload)
        finally:
            self._completed_cycle = previous

    def finish(self, token):
        completed = getattr(self, '_completed_cycle', None)
        if completed is None or completed.token is not token:
            return super().finish(token)
        next_hops = token.hops + len(completed.nodes)
        if not self.sim.searches_enabled or next_hops >= self.sim.search_budget:
            return super().finish(token)
        start = token.path.index(completed.nodes[0])
        capacities = getattr(token, 'capacities', [])
        if token.path[start:] != completed.nodes or len(capacities) != len(token.path)-1:
            raise ValueError('Completed cycle must match the Numbat path and capacity hints')
        prefix = token.path[:start+1]
        # Own wake events use this same counter, so identifiers cannot collide
        # with either this actor's searches or earlier continuations it issued.
        self.sequence += 1
        continuation = Token((self.name, self.sequence), prefix, set(prefix), next_hops)
        continuation.capacities = capacities[:start]
        self.sim.metrics['successful_search_continuations'] += 1
        self.sim.send(self.name, completed.nodes[0], 'step', continuation)


class ContinuationNumbat(JsonNumbat):
    """One isolated policy change against the existing close-first control."""
    def __init__(self, graph=None, **kwargs):
        if kwargs.get('close_first', True) is not True:
            raise ValueError('Continuation experiment requires the close-first control')
        if kwargs.get('snapshot_capacity', True) is not True:
            raise ValueError('Continuation requires Numbat capacity hints')
        kwargs['close_first'] = True
        super().__init__(graph, **kwargs)

    def add_edge(self, a, b, amount, at=None):
        super().add_edge(a, b, amount, at)
        if at is None:
            for name in (a, b):
                self.nodes[name].__class__ = ContinuationNode
