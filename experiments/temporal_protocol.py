"""Dynamic neighbour-local clearing over lossy reliable transport.

Search/settlement is existing DFS/Numbat. The scheduler only delivers messages,
external bilateral transfers and sleep events; it never chooses loops. Ledger
ownership is debtor-local, not replicated. External transfers atomically net the
two endpoints and wait while either endpoint has a reservation on that pair.
This models delayed bilateral posting, NOT consensus or crash recovery.

Zero balances are ineligible for new forward searches. Historical pair identities
remain solely for completing already-started search/settlement control traffic;
this explicit transport grace can outlive economic channel closure. Reliable
transport retains envelopes, retries data and ACKs, and deduplicates application
handling. Sleep preserves durable state. Unbounded loss/sleep can leave pending
work; an event budget raises instead of declaring completion. Commit is staged,
so conservation is checked after draining, not during partially delivered laps.

stop_wait is a scheduler reference half-duplex pair queue, NOT an implementation
of the historical decentralized turn-negotiation protocol. concurrent is default.
"""
from __future__ import annotations
from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass
import heapq
from distributed import DistributedDFS, Node
from numbat import NumbatNode


class LedgerObserver:
    """Observational edge records only; no search decisions use the audit log."""
    def receive(self, kind, payload):
        if kind == 'commit':
            tx = payload
            neighbor = tx.nodes[(tx.nodes.index(self.name) + 1) % len(tx.nodes)]
            before = self.outgoing.get(neighbor, 0)
            super().receive(kind, payload)
            delta = self.outgoing.get(neighbor, 0) - before
            if delta:
                self.sim.record_ledger('commit', self.name, neighbor, delta, tx.token.ident)
        else:
            super().receive(kind, payload)


class TemporalDFSNode(LedgerObserver, Node):
    pass


class TemporalNumbatNode(LedgerObserver, NumbatNode):
    pass


@dataclass
class Envelope:
    source: object
    dest: object
    kind: str
    payload: object
    attempts: int = 0


class TemporalProtocol(DistributedDFS):
    def __init__(self, graph=None, *, algorithm='numbat', loss=0., ack_loss=None,
                 retransmit=20, transport='concurrent', capacity_power=4., **kwargs):
        if algorithm not in ('numbat', 'random', 'largest'):
            raise ValueError('Unknown algorithm')
        if transport not in ('concurrent', 'stop_wait'):
            raise ValueError('Unknown transport')
        if not 0 <= loss <= 1 or (ack_loss is not None and not 0 <= ack_loss <= 1) or retransmit < 1:
            raise ValueError('Invalid loss/retransmit')
        self.algorithm, self.loss = algorithm, loss
        self.ack_loss = loss if ack_loss is None else ack_loss
        self.retransmit, self.transport = retransmit, transport
        self.capacity_power, self.snapshot_capacity, self.close_first = capacity_power, True, False
        self.pending, self.seen, self.sleep_intervals = {}, set(), defaultdict(list)
        self.pair_queues, self.envelope_sequence = defaultdict(deque), 0
        self.transfer_records = []
        self.ledger_records = []
        self.transfer_queues = defaultdict(deque)
        super().__init__(None, policy='largest' if algorithm == 'largest' else 'random', **kwargs)
        for (a, b), amount in (graph or {}).items():
            self.add_transfer(a, b, amount)

    def record_ledger(self, kind, source, target, delta, txid=None):
        self.ledger_records.append(dict(time=self.time, order=len(self.ledger_records),
                                       kind=kind, source=source, target=target,
                                       delta=delta, txid=txid))

    def awake_at(self, node, at):
        # Merge overlapping intervals by moving until no interval contains at.
        while True:
            ends = [end for start, end in self.sleep_intervals[node] if start <= at < end]
            if not ends:
                return at
            at = max(ends)

    def add_sleep(self, node, start, duration):
        if start < self.time or duration < 0:
            raise ValueError('Sleep must start now or later')
        self.sleep_intervals[node].append((start, start + duration))

    def add_transfer(self, a, b, amount, at=None):
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0 or a == b:
            raise ValueError('Positive integer non-self transfers required')
        when = self.time if at is None else at
        if when < self.time:
            raise ValueError('Cannot add past transfers')
        self.schedule(when, None, 'transfer', (a, b, amount, when))

    def _post(self, a, b, amount, requested):
        for name in (a, b):
            if name not in self.nodes:
                self.nodes[name] = (TemporalNumbatNode if self.algorithm == 'numbat' else TemporalDFSNode)(name, self)
                if self.searches_enabled:
                    self.schedule(self.time + self.random.randrange(self.retry_interval), name, 'wake', None)
        if any(dest == peer for name, peer in ((a,b), (b,a))
               for dest, _ in self.nodes[name].reservations.values()):
            self.metrics['transfer_deferrals'] += 1
            self.schedule(self.time + self.retransmit, None, 'post', (a,b,amount,requested))
            return
        awake = max(self.awake_at(a, self.time), self.awake_at(b, self.time))
        if awake > self.time:
            self.schedule(awake, None, 'post', (a,b,amount,requested))
            return
        old = self.nodes[a].outgoing.get(b, 0) - self.nodes[b].outgoing.get(a, 0)
        new = old + amount
        self.nodes[a].outgoing[b] = max(new, 0)
        self.nodes[b].outgoing[a] = max(-new, 0)
        self.channels.add(frozenset((a,b)))
        self.metrics['added'] += amount
        self.metrics['bilateral_netting'] += abs(old) + amount - abs(new)
        self.metrics['transfers'] += 1
        self.metrics['transfer_delay'] += self.time - requested
        self.transfer_records.append((self.time, a, b, amount))
        self.record_ledger('transfer', a, b, amount)
        queue = self.transfer_queues[frozenset((a,b))]
        queue.popleft()
        if queue:
            self.schedule(self.time, None, 'post', queue[0])

    def send(self, source, dest, kind, payload):
        assert frozenset((source,dest)) in self.channels, 'Non-neighbour message'
        self.envelope_sequence += 1
        ident = self.envelope_sequence
        self.pending[ident] = Envelope(source, dest, kind, deepcopy(payload))
        self.metrics['messages'] += 1
        self.metrics['messages_' + kind] += 1
        if len(self.message_log) < 10000:
            self.message_log.append((self.time, source, dest, kind))
        if self.transport == 'stop_wait':
            queue = self.pair_queues[frozenset((source,dest))]
            queue.append(ident)
            if len(queue) > 1:
                return
        self.schedule(self.time, None, 'attempt', ident)

    def _attempt(self, ident):
        env = self.pending.get(ident)
        if env is None:
            return
        awake = self.awake_at(env.source, self.time)
        if awake > self.time:
            self.schedule(awake, None, 'attempt', ident)
            return
        env.attempts += 1
        self.metrics['data_attempts'] += 1
        self.metrics['retransmissions'] += env.attempts > 1
        self.metrics['payload_repr_bytes'] += len(repr(env.payload).encode())
        if self.random.random() < self.loss:
            self.metrics['data_dropped'] += 1
        else:
            self.schedule(self.time + self.random.randint(1,self.max_delay), None, 'delivery', ident)
        self.schedule(self.time + self.retransmit, None, 'attempt', ident)

    def _delivery(self, ident):
        env = self.pending.get(ident)
        if env is None:
            return
        if self.awake_at(env.dest, self.time) > self.time:
            self.metrics['sleep_dropped'] += 1
            return
        if ident not in self.seen:
            self.seen.add(ident)
            self.metrics['application_deliveries'] += 1
            self.nodes[env.dest].receive(env.kind, deepcopy(env.payload))
        else:
            self.metrics['duplicates_suppressed'] += 1
        self.metrics['ack_attempts'] += 1
        if self.random.random() < self.ack_loss:
            self.metrics['ack_dropped'] += 1
        else:
            self.schedule(self.time + self.random.randint(1,self.max_delay), None, 'ack', ident)

    def _ack(self, ident):
        env = self.pending.get(ident)
        if env is None:
            return
        if self.awake_at(env.source,self.time) > self.time:
            self.metrics['ack_sleep_dropped'] += 1
            return
        del self.pending[ident]
        if self.transport == 'stop_wait':
            queue = self.pair_queues[frozenset((env.source,env.dest))]
            assert queue.popleft() == ident
            if queue:
                self.schedule(self.time,None,'attempt',queue[0])

    def run(self, until, max_events=1000000):
        if until < self.time:
            raise ValueError('Cannot run backwards')
        processed = 0
        while self.events and self.events[0][0] <= until:
            if processed >= max_events:
                raise RuntimeError('Event budget exhausted; simulation incomplete')
            self.time, _, dest, kind, payload = heapq.heappop(self.events)
            if kind == 'transfer':
                queue = self.transfer_queues[frozenset(payload[:2])]
                queue.append(payload)
                if len(queue) == 1:
                    self.schedule(self.time, None, 'post', payload)
            elif kind == 'post':
                self._post(*payload)
            elif kind == 'attempt':
                self._attempt(payload)
            elif kind == 'delivery':
                self._delivery(payload)
            elif kind == 'ack':
                self._ack(payload)
            else:
                awake = self.awake_at(dest,self.time)
                if awake > self.time:
                    self.schedule(awake,dest,kind,payload)
                else:
                    self.nodes[dest].receive(kind,payload)
            processed += 1
            self.metrics['events'] += 1
        self.time = until
        return dict(self.metrics)

    @property
    def open_channels(self):
        return {frozenset((a,b)) for (a,b), amount in self.graph_snapshot().items() if amount}

    def drain(self, max_events=1000000):
        result = super().drain(max_events)
        assert not self.pending
        return result
