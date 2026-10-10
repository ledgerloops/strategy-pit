"""Headroom Clearing: bounded, node-local residual-cycle search.

Every original obligation has immutable cap B and current value 0 <= x <= B.
Forward traversal reduces x; reverse traversal restores x. A cycle may settle
only if its decreases outnumber its increases, preserving every signed net
position while strictly reducing total debt. Original bounds are local consent;
this does NOT promise each participant a reduction in gross exposure.

Research assumptions: honest nodes, reliable FIFO exactly-once neighbor messages,
no crashes, serialized searches/settlements, static caps. The simulator serializes
initiators, not graph decisions. A token exposes its path to visited neighbors.
Prepare/commit is non-atomic in flight; audits apply at completed settlements.
Bounded simple-path search is heuristic and makes no optimality claim. Exhaustive
negative-cycle cancellation would attain the original bounded MCF objective.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
import random


@dataclass
class Token:
    path: list
    arcs: list = field(default_factory=list)
    tried: list = field(default_factory=lambda: [set()])
    hops: int = 0


@dataclass
class Settlement:
    nodes: list
    arcs: list  # (source, destination, +1 decrease / -1 restore, observed capacity)
    amount: int
    cursor: int = 0


class HeadroomNode:
    def __init__(self, name, transport):
        self.name = name
        self.transport = transport
        self.owned = {}  # creditor -> [original cap, current debt]
        self.incoming = {}  # debtor -> advertised [cap, current debt]

    def residual(self, neighbor, direction):
        if direction == 1:
            return self.owned.get(neighbor, (0, 0))[1]
        cap, balance = self.incoming.get(neighbor, (0, 0))
        return cap - balance

    def receive(self, sender, kind, payload):
        if kind == 'advertise':
            self.incoming[sender] = list(payload)
            return
        if kind == 'search':
            return self.search(payload)
        tx = payload
        i = tx.cursor
        outgoing = tx.arcs[i]
        incoming = tx.arcs[(i - 1) % len(tx.arcs)]
        if kind == 'prepare':
            # This node consents to both local incidences. Reverse incidences
            # are checked by the actual obligation owner as well as its peer.
            capacities = [self.residual(outgoing[1], outgoing[2])]
            if incoming[2] == 1:
                capacities.append(self.incoming[incoming[0]][1])
            else:
                cap, value = self.owned[incoming[0]]
                capacities.append(cap - value)
            tx.amount = min(tx.amount, *capacities)
            if tx.amount <= 0:
                self.transport.metrics['aborts'] += 1
                return  # No reservation needed with serialized transactions.
            tx.cursor = (i + 1) % len(tx.nodes)
            next_kind = 'commit' if tx.cursor == 0 else 'prepare'
            self.transport.send(self.name, outgoing[1], next_kind, tx)
            return
        if kind != 'commit':
            raise ValueError('unknown message kind')
        if outgoing[2] == 1:
            self.owned[outgoing[1]][1] -= tx.amount
        else:
            self.incoming[outgoing[1]][1] += tx.amount
        if incoming[2] == 1:
            self.incoming[incoming[0]][1] -= tx.amount
        else:
            self.owned[incoming[0]][1] += tx.amount
        tx.cursor = (i + 1) % len(tx.nodes)
        if tx.cursor:
            self.transport.send(self.name, outgoing[1], 'commit', tx)
        else:
            self.transport.records.append({
                'nodes': list(tx.nodes), 'amount': tx.amount,
                'directions': [arc[2] for arc in tx.arcs],
                'debt_reduction': tx.amount * sum(a[2] for a in tx.arcs),
            })
            self.transport.metrics['settlements'] += 1

    def search(self, token):
        if token.hops >= self.transport.search_budget:
            self.transport.metrics['budget_exhaustions'] += 1
            return
        candidates = [(n, 1) for n in self.owned]
        candidates += [(n, -1) for n in self.incoming]
        candidates = [(n, d) for n, d in candidates
                      if (n, d) not in token.tried[-1] and self.residual(n, d) > 0]
        self.transport.rng.shuffle(candidates)
        # Local capacity preference, with decrease preferred at equal capacity.
        candidates.sort(key=lambda nd: (self.residual(*nd), nd[1]), reverse=True)
        for neighbor, direction in candidates:
            token.tried[-1].add((neighbor, direction))
            arc = (self.name, neighbor, direction, self.residual(neighbor, direction))
            if neighbor in token.path:
                start = token.path.index(neighbor)
                cycle = token.arcs[start:] + [arc]
                if sum(a[2] for a in cycle) <= 0:
                    continue
                tx = Settlement(token.path[start:], cycle, min(a[3] for a in cycle))
                self.transport.metrics['proposals'] += 1
                self.transport.send(self.name, neighbor, 'prepare', tx)
                return
            if len(token.path) >= self.transport.max_hops:
                continue
            token.path.append(neighbor)
            token.arcs.append(arc)
            token.tried.append(set())
            token.hops += 1
            self.transport.send(self.name, neighbor, 'search', token)
            return
        if len(token.path) > 1:
            token.path.pop()
            token.arcs.pop()
            token.tried.pop()
            token.hops += 1
            self.transport.send(self.name, token.path[-1], 'search', token)
        else:
            self.transport.metrics['exhausted_searches'] += 1


class Headroom:
    """Transport/scheduler; graph snapshots are reporting/auditing only.

    ``caps`` is the original directed ledger. Optional ``balances`` is a supplied
    post-clearing snapshot with the SAME net positions. Benchmarks must disclose
    how that snapshot was produced; seeding with centralized DFS is not a wholly
    node-local pipeline. Default starts directly from the original ledger.
    """
    def __init__(self, caps, balances=None, *, seed=1, search_budget=1000, max_hops=64):
        if search_budget < 1 or max_hops < 2:
            raise ValueError('positive search budget and max_hops >= 2 required')
        self.search_budget, self.max_hops = search_budget, max_hops
        self.rng = random.Random(seed)
        self.nodes, self.events, self.records = {}, deque(), []
        self.metrics = Counter()
        balances = caps if balances is None else balances
        if set(balances) - set(caps):
            raise ValueError('snapshot contains an obligation outside original caps')
        for (a, b), cap in caps.items():
            value = balances.get((a, b), 0)
            if a == b or type(cap) is not int or type(value) is not int or not 0 <= value <= cap:
                raise ValueError('distinct peers and integer balances within original bounds required')
            for name in (a, b):
                self.nodes.setdefault(name, HeadroomNode(name, self))
            self.nodes[a].owned[b] = [cap, value]
        if self.net_positions(caps) != self.net_positions(balances):
            raise ValueError('snapshot must preserve original signed net positions')
        for node in self.nodes.values():
            for neighbor, pair in node.owned.items():
                self.send(node.name, neighbor, 'advertise', tuple(pair))
        self.drain()
        self.initial_debt = sum(balances.values())
        self.original_debt = sum(caps.values())
        self.original_net = self.net_positions(caps)

    def send(self, sender, receiver, kind, payload):
        # Transport enforces direct-neighbor delivery, without choosing routes.
        node = self.nodes[sender]
        if receiver not in node.owned and receiver not in node.incoming:
            raise ValueError('message to a non-neighbor')
        self.events.append((sender, receiver, kind, payload))
        self.metrics['messages'] += 1
        self.metrics['messages_' + kind] += 1

    def drain(self):
        while self.events:
            sender, receiver, kind, payload = self.events.popleft()
            self.nodes[receiver].receive(sender, kind, payload)

    def run(self, rounds=1):
        for _ in range(rounds):
            roots = list(self.nodes)
            self.rng.shuffle(roots)
            for root in roots:
                self.metrics['searches'] += 1
                self.nodes[root].receive(root, 'search', Token([root]))
                self.drain()
        self.audit()
        return self.snapshot()

    def snapshot(self):
        return {(node.name, peer): pair[1] for node in self.nodes.values()
                for peer, pair in node.owned.items()}

    @staticmethod
    def net_positions(graph):
        result = Counter()
        for (a, b), value in graph.items():
            result[a] -= value
            result[b] += value
        return {node: value for node, value in result.items() if value}

    def audit(self):
        if self.events:
            raise AssertionError('audit requires completed settlement')
        snapshot = self.snapshot()
        assert self.net_positions(snapshot) == self.original_net
        assert self.initial_debt - sum(snapshot.values()) == sum(r['debt_reduction'] for r in self.records)
        for record in self.records:
            assert record['debt_reduction'] > 0
        for node in self.nodes.values():
            for peer, pair in node.owned.items():
                assert 0 <= pair[1] <= pair[0]
                assert self.nodes[peer].incoming[node.name] == pair
