"""Exact, centralized trustline-cycle research model (integer accounting units).

A canonical line (a < b) has balance b owes a, and limits [lower, upper].
Upper is the maximum debt of b approved by a; lower is minus the maximum
debt of a approved by b. Thus each endpoint controls the exposure it accepts.
The reverse viewpoint has balance -balance and bounds [-upper, -lower].
A cycle move adds delta to every source's view of the next peer's balance.
This preserves every node's net position, but may increase individual debts.
Debt counts each bilateral balance once. This is a bird's-eye optimizer, not
an asynchronous settlement protocol; limits represent prior authorization.
"""
from dataclasses import dataclass, replace
import random
from typing import Iterable


def _integer(value):
    if type(value) is not int:
        raise ValueError('amounts and limits must be integers (not bools)')


@dataclass(frozen=True)
class Trustline:
    a: str
    b: str
    balance: int
    lower: int
    upper: int

    def __post_init__(self):
        if not isinstance(self.a, str) or not isinstance(self.b, str) or self.a >= self.b:
            raise ValueError('endpoints must be distinct canonical strings a < b')
        for value in (self.balance, self.lower, self.upper):
            _integer(value)
        if not self.lower <= 0 <= self.upper:
            raise ValueError('limits must contain zero')
        if not self.lower <= self.balance <= self.upper:
            raise ValueError('balance outside limits')


class TrustlineNetwork:
    def __init__(self, lines: Iterable[Trustline] = ()):
        self.lines = {}
        for line in lines:
            self.add_line(line)

    def add_line(self, line: Trustline):
        if not isinstance(line, Trustline):
            raise ValueError('expected Trustline')
        key = (line.a, line.b)
        if key in self.lines:
            raise ValueError('duplicate bilateral line')
        self.lines[key] = line

    def copy(self):
        return TrustlineNetwork(self.lines.values())

    def view(self, source, target):
        line = self.lines[tuple(sorted((source, target)))]
        return line.balance if source == line.a else -line.balance

    def bounds(self, source, target):
        line = self.lines[tuple(sorted((source, target)))]
        return (line.lower, line.upper) if source == line.a else (-line.upper, -line.lower)

    def debt(self):
        return sum(abs(line.balance) for line in self.lines.values())

    def positions(self):
        positions = {}
        for line in self.lines.values():
            positions[line.a] = positions.get(line.a, 0) + line.balance
            positions[line.b] = positions.get(line.b, 0) - line.balance
        return positions


def _edges(network, cycle):
    cycle = tuple(cycle)
    if len(cycle) < 3 or len(set(cycle)) != len(cycle):
        raise ValueError('cycle must contain at least three distinct nodes; do not repeat start')
    edges = tuple(zip(cycle, cycle[1:] + cycle[:1]))
    if any(tuple(sorted(edge)) not in network.lines for edge in edges):
        raise ValueError('cycle contains missing trustline')
    return cycle, edges


@dataclass(frozen=True)
class CycleMove:
    cycle: tuple
    delta: int
    debt_before: int
    debt_after: int
    balances_before: tuple

    @property
    def reduction(self):
        return self.debt_before - self.debt_after


def best_cycle_move(network, cycle):
    """Minimize sum |balance + delta| within all endpoint-approved limits.

    Convex piecewise-linear cost changes slope only at zero crossings. All
    crossings and endpoints are integral, so these candidates give an exact
    optimum; ties prefer smallest absolute delta, then negative delta. Only
    balances and limits on the chosen loop determine the optimizing delta;
    total network debt is inspected solely to report before/after values.
    """
    cycle, edges = _edges(network, cycle)
    balances = tuple(network.view(*edge) for edge in edges)
    limits = tuple(network.bounds(*edge) for edge in edges)
    lower = max(lo - b for b, (lo, hi) in zip(balances, limits))
    upper = min(hi - b for b, (lo, hi) in zip(balances, limits))
    candidates = {0, lower, upper}
    candidates.update(-b for b in balances if lower <= -b <= upper)
    cost = lambda d: sum(abs(b + d) for b in balances)
    delta = min(candidates, key=lambda d: (cost(d), abs(d), d))
    before = network.debt()
    after = before - cost(0) + cost(delta)
    # Explicitly forbid plateau moves: every accepted move strictly improves D.
    if after >= before:
        delta, after = 0, before
    return CycleMove(cycle, delta, before, after, balances)


def apply_move(network, move):
    """Validate and apply an optimal quote atomically in this simulator.

    Quotes become stale after any intervening relevant balance or debt change.
    This guards simulator misuse; it is not a distributed locking protocol.
    """
    if not isinstance(move, CycleMove):
        raise ValueError('expected CycleMove')
    for value in (move.delta, move.debt_before, move.debt_after, *move.balances_before):
        _integer(value)
    expected = best_cycle_move(network, move.cycle)
    if move != expected:
        raise ValueError('stale or invalid cycle quote')
    _, edges = _edges(network, move.cycle)
    updates = {}
    for source, target in edges:
        key = tuple(sorted((source, target)))
        line = network.lines[key]
        change = move.delta if source == line.a else -move.delta
        updates[key] = replace(line, balance=line.balance + change)
    network.lines.update(updates)


@dataclass(frozen=True)
class CycleEnumeration:
    cycles: tuple
    complete: bool


def enumerate_cycles(network, max_length=None, max_cycles=None):
    """Enumerate simple undirected cycles once, in deterministic order.

    Exponential in graph size; intended for small experimental networks.
    Length truncation reports incomplete conservatively even when a blocked
    path would ultimately have proved unable to close.
    """
    if max_length is not None and (type(max_length) is not int or max_length < 3):
        raise ValueError('max_length must be an integer >= 3')
    if max_cycles is not None and (type(max_cycles) is not int or max_cycles < 1):
        raise ValueError('max_cycles must be a positive integer')
    adjacency = {}
    for a, b in network.lines:
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    found = []
    complete = True
    stopped = False

    def visit(start, path):
        nonlocal complete, stopped
        for neighbor in sorted(adjacency[path[-1]]):
            if stopped:
                return
            if neighbor == start:
                if len(path) >= 3 and path[1] < path[-1]:
                    if max_cycles is not None and len(found) >= max_cycles:
                        complete, stopped = False, True
                        return
                    found.append(tuple(path))
            elif neighbor > start and neighbor not in path:
                if max_length is not None and len(path) >= max_length:
                    complete = False
                else:
                    visit(start, path + [neighbor])

    for start in sorted(adjacency):
        if stopped:
            break
        visit(start, [start])
    return CycleEnumeration(tuple(found), complete)


@dataclass(frozen=True)
class OptimizationResult:
    moves: tuple
    complete: bool
    termination: str
    debt_before: int
    debt_after: int


def optimize(network, policy='best', max_steps=10000, max_length=None, max_cycles=None, seed=0):
    """Repeatedly exercise first/best/random improving cycles in current state.

    Random shuffles the scan each step and accepts its first improving cycle.

    Complete means an exhaustive cycle scan found no strict improvement.
    Reaching a step, length, or enumeration bound is explicitly incomplete.
    Topology and approved limits are fixed during a call; zero lines remain.
    """
    if policy not in ('first', 'best', 'random'):
        raise ValueError('policy must be first, best, or random')
    if type(max_steps) is not int or max_steps < 0:
        raise ValueError('max_steps must be a nonnegative integer')
    enumeration = enumerate_cycles(network, max_length, max_cycles)
    initial = network.debt()
    moves = []
    rng = random.Random(seed)
    cycles = list(enumeration.cycles)
    while True:
        best = None
        if policy == 'random':
            rng.shuffle(cycles)
        for cycle in cycles:
            candidate = best_cycle_move(network, cycle)
            if candidate.reduction > 0 and (best is None or candidate.reduction > best.reduction):
                best = candidate
                if policy in ('first', 'random'):
                    break
        if best is None:
            return OptimizationResult(tuple(moves), enumeration.complete,
                                      'exhausted' if enumeration.complete else 'cycle_bound',
                                      initial, network.debt())
        if len(moves) >= max_steps:
            return OptimizationResult(tuple(moves), False, 'step_bound', initial, network.debt())
        apply_move(network, best)
        moves.append(best)
