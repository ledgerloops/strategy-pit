"""Neighbor-message DFS research simulator (standard library only).

Each node owns its outgoing obligations; creditors do not hold replicated ledgers.
Concurrent DFS tokens carry their path and discovered nodes, exposing that path to
participants. A cycle uses fail-fast reservations followed by an irrevocable commit
lap. Reliable eventual exactly-once delivery, honest nodes and no crashes are assumed.
Duplicate delivery is not supported (the local committed set alone does not make
the complete protocol idempotent). Commit
is NOT instantaneously atomic: inspect conservation after draining transactions.
Control messages travel both ways along persistent acquaintance channels created
by obligations. Channels remain usable after the associated debt is cleared.
Local periodic retries invalidate old search knowledge, including after new links.
Cycles require at least three nodes, matching the bilaterally netted benchmark.
Reciprocal edges are accepted as separate obligations, but two-node cycles are not
cleared. Bounded searches and finite retry windows do not guarantee maximality.
This is a simulator of a protocol, not a deployable payment/consensus protocol.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import heapq
import random


@dataclass
class Token:
    ident: tuple[str, int]
    path: list[str]
    visited: set[str]
    hops: int = 0


@dataclass
class Transaction:
    token: Token
    nodes: list[str]
    amount: int
    prepared: list[str] = field(default_factory=list)
    proposed_at: int = 0


class Node:
    def __init__(self, name, sim):
        self.name, self.sim = name, sim
        self.outgoing = {}
        self.reservations = {}  # transaction ID -> (neighbor, amount)
        self.committed = set()
        self.active = False
        self.sequence = 0

    def available(self, neighbor):
        return self.outgoing.get(neighbor, 0) - sum(
            amount for dest, amount in self.reservations.values() if dest == neighbor)

    def receive(self, kind, payload):
        if kind == 'wake':
            if not self.sim.searches_enabled:
                return
            self.sim.schedule(self.sim.time + self.sim.retry_interval +
                              self.sim.random.randrange(self.sim.retry_interval),
                              self.name, 'wake', None)
            if self.active or not any(self.available(n) for n in self.outgoing):
                return
            self.active = True
            self.sequence += 1
            self.sim.metrics['searches'] += 1
            self.receive('step', Token((self.name, self.sequence), [self.name], {self.name}))
        elif kind == 'step':
            token = payload
            if token.hops >= self.sim.search_budget:
                self.finish(token)
                return
            candidates = [n for n in self.outgoing if self.available(n) > 0 and
                          (n not in token.visited or
                           (n in token.path and len(token.path) - token.path.index(n) >= 3))]
            self.sim.random.shuffle(candidates)
            if self.sim.policy == 'largest':
                candidates.sort(key=self.available, reverse=True)
            for neighbor in candidates:
                if neighbor in token.path:
                    # Capacity information is collected by the reservation lap;
                    # this node knows only its own closing edge capacity.
                    nodes = token.path[token.path.index(neighbor):]
                    tx = Transaction(token, nodes, self.available(neighbor), proposed_at=self.sim.time)
                    self.sim.metrics['proposals'] += 1
                    self.sim.send(self.name, neighbor, 'prepare', tx)
                    return
                if len(token.path) < self.sim.max_hops:
                    token.path.append(neighbor)
                    token.visited.add(neighbor)
                    token.hops += 1
                    self.sim.send(self.name, neighbor, 'step', token)
                    return
            if len(token.path) > 1:
                token.path.pop()
                token.hops += 1
                self.sim.send(self.name, token.path[-1], 'step', token)
            else:
                self.active = False
                self.sim.metrics['exhausted_searches'] += 1
        elif kind == 'prepare':
            tx = payload
            index = tx.nodes.index(self.name)
            neighbor = tx.nodes[(index + 1) % len(tx.nodes)]
            available = self.available(neighbor)
            if available <= 0:
                self.sim.metrics['aborted'] += 1
                if tx.prepared:
                    self.sim.send(self.name, tx.prepared[-1], 'abort', tx)
                else:
                    self.finish_from_cycle(tx)
                return
            # Later participants can lower the final amount. Earlier reservations
            # may temporarily exceed it; commit releases the unused remainder.
            tx.amount = min(tx.amount, available)
            self.reservations[tx.token.ident] = (neighbor, tx.amount)
            tx.prepared.append(self.name)
            self.sim.metrics['live_reservations'] += 1
            self.sim.metrics['max_reservations'] = max(
                self.sim.metrics['max_reservations'], self.sim.metrics['live_reservations'])
            self.sim.send(self.name, neighbor,
                          'commit' if len(tx.prepared) == len(tx.nodes) else 'prepare', tx)
        elif kind == 'abort':
            tx = payload
            if self.reservations.pop(tx.token.ident, None) is not None:
                self.sim.metrics['live_reservations'] -= 1
            assert tx.prepared.pop() == self.name
            if tx.prepared:
                self.sim.send(self.name, tx.prepared[-1], 'abort', tx)
            else:
                self.finish_from_cycle(tx)
        elif kind == 'commit':
            tx = payload
            index = tx.nodes.index(self.name)
            neighbor = tx.nodes[(index + 1) % len(tx.nodes)]
            if tx.token.ident not in self.committed:
                dest, amount = self.reservations.pop(tx.token.ident)
                self.sim.metrics['live_reservations'] -= 1
                assert dest == neighbor and amount >= tx.amount
                assert self.outgoing[neighbor] >= tx.amount
                self.outgoing[neighbor] -= tx.amount
                self.committed.add(tx.token.ident)
            if index + 1 < len(tx.nodes):
                self.sim.send(self.name, neighbor, 'commit', tx)
            else:
                self.sim.cycles.append((list(tx.nodes), tx.amount))
                self.sim.cycle_records.append(dict(nodes=list(tx.nodes), amount=tx.amount,
                                                   time=self.sim.time, proposed_at=tx.proposed_at,
                                                   duration=self.sim.time - tx.proposed_at))
                self.sim.metrics['cycles'] += 1
                self.sim.metrics['cleared'] += len(tx.nodes) * tx.amount
                self.finish(tx.token)
        elif kind == 'finish':
            self.finish(payload)
        else:
            raise ValueError(kind)

    def finish_from_cycle(self, tx):
        # The first cycle node is adjacent to the last (closing obligation).
        self.sim.send(self.name, tx.token.path[-1], 'finish', tx.token)

    def finish(self, token):
        assert token.path[-1] == self.name
        if len(token.path) > 1:
            token.path.pop()
            self.sim.send(self.name, token.path[-1], 'finish', token)
        else:
            self.active = False


class DistributedDFS:
    """Event-driven simulator. run(until) is inclusive and can be called repeatedly.

    Stop local retries with stop_searches(), then drain() before conservation or
    residual-graph comparisons. Adding links after stopping does not resume retries.
    Nodes use only local state plus received messages; scheduler owns instrumentation.
    """
    def __init__(self, graph=None, *, seed=0, max_delay=5, retry_interval=50,
                 max_hops=100, search_budget=1000, policy='random'):
        if max_delay < 1 or retry_interval < 1 or max_hops < 3 or search_budget < 1:
            raise ValueError('Invalid scheduler or search bounds')
        if policy not in ('random', 'largest'):
            raise ValueError('Unknown local traversal policy')
        self.policy = policy
        self.random = random.Random(seed)
        self.max_delay, self.retry_interval = max_delay, retry_interval
        self.max_hops, self.search_budget = max_hops, search_budget
        self.nodes, self.channels = {}, set()
        self.events, self.cycles, self.cycle_records = [], [], []
        self.metrics = Counter()
        self.time = self.serial = 0
        self.searches_enabled = True
        self.message_log = []
        for (a, b), amount in (graph or {}).items():
            self.add_edge(a, b, amount)

    def schedule(self, at, dest, kind, payload):
        self.serial += 1
        heapq.heappush(self.events, (at, self.serial, dest, kind, payload))

    def send(self, source, dest, kind, payload):
        assert frozenset((source, dest)) in self.channels, 'Non-neighbor message'
        delay = self.random.randint(1, self.max_delay)
        self.metrics['messages'] += 1
        self.metrics['messages_' + kind] += 1
        token = payload.token if isinstance(payload, Transaction) else payload
        # Exact node-ID occurrence count in logical payloads, not encoded bytes.
        count = 1 + len(token.path) + len(token.visited)
        if isinstance(payload, Transaction):
            count += len(payload.nodes) + len(payload.prepared)
        self.metrics['message_node_ids'] += count
        self.metrics['max_message_node_ids'] = max(self.metrics['max_message_node_ids'], count)
        # Retain a bounded audit sample; unbounded traces distort large benchmarks.
        if len(self.message_log) < 10000:
            self.message_log.append((self.time, source, dest, kind))
        self.schedule(self.time + delay, dest, kind, payload)

    def add_edge(self, a, b, amount, at=None):
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0 or a == b:
            raise ValueError('Positive integer non-self obligations required')
        if at is not None:
            if at < self.time:
                raise ValueError('Cannot add obligations in the past')
            self.schedule(at, None, 'add', (a, b, amount))
            return
        for name in (a, b):
            if name not in self.nodes:
                self.nodes[name] = Node(name, self)
                if self.searches_enabled:
                    self.schedule(self.time + self.random.randrange(self.retry_interval),
                                  name, 'wake', None)
        self.channels.add(frozenset((a, b)))
        owner = self.nodes[a]
        owner.outgoing[b] = owner.outgoing.get(b, 0) + amount
        self.metrics['added'] += amount

    def run(self, until, max_events=1000000):
        if until < self.time:
            raise ValueError('Cannot run backwards')
        processed = 0
        while self.events and self.events[0][0] <= until:
            if processed >= max_events:
                raise RuntimeError('Event budget exhausted; simulation not complete')
            self.time, _, dest, kind, payload = heapq.heappop(self.events)
            if kind == 'add':
                self.add_edge(*payload)
            else:
                self.nodes[dest].receive(kind, payload)
            processed += 1
            self.metrics['events'] += 1
        self.time = until
        return dict(self.metrics)

    def stop_searches(self):
        self.searches_enabled = False

    def drain(self, max_events=1000000):
        """Stop new searches and deliver all remaining events (including future adds)."""
        self.stop_searches()
        before = self.metrics['events']
        while self.events:
            left = max_events - (self.metrics['events'] - before)
            if left <= 0:
                raise RuntimeError('Drain budget exhausted')
            self.run(self.events[0][0], max_events=left)
        assert self.pending_reservations == 0
        assert not any(node.active for node in self.nodes.values())
        return dict(self.metrics)

    @property
    def pending_reservations(self):
        return sum(len(node.reservations) for node in self.nodes.values())

    def graph_snapshot(self):
        return {(name, dest): amount for name, node in self.nodes.items()
                for dest, amount in node.outgoing.items() if amount}
