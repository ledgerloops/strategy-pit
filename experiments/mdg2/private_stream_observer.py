"""Offline quote-consistent reconstruction of private protocol evidence.

This is an observer, never a participant input. A local receipt is not an atomic
whole-loop commit. An operation enters this shadow ledger only after all its
endpoint evidence agrees AND its quoted before-states match the shadow ledger.
Concurrent, nonserializable dependencies remain pending, even at end of run.
Balance quotes can repeat (ABA); without local application ordinals they do not
prove actual causal order. The legacy ``causal_fully_applied_gross`` field name
is retained for schema compatibility and denotes this consistent shadow only.
The no-clearing reference replays exactly the incorporated external payments.
Neither curve replaces measured endpoint debt, mirror gaps, or reservations.

Evidence authenticity/actual DB application relies on the isolated honest-process
journal. Hash and accounting checks are not signatures or Byzantine consensus.
"""
from copy import deepcopy

from private_stream_audit import verify_local_receipt


def _integer(value):
    if type(value) is not int:
        raise ValueError('Expected integer balance or amount')
    return value


def _quote(node, peer, before, after):
    node, peer = str(node), str(peer)
    if node == peer:
        raise ValueError('Self edge')
    before, after = _integer(before), _integer(after)
    edge = tuple(sorted((node, peer)))
    return edge, (before, after) if node == edge[0] else (-before, -after)


class Observer:
    """Consume trusted local application journals in observation order.

    initial_edges: iterable (node, peer, signed balance at node, ...). Additional
    preference fields are ignored. No method returns data to protocol actors.
    time/message_count describe when evidence was observed, not when a request
    started. Multiple reconstructed applications can share one transport count.
    """

    def __init__(self, initial_edges):
        self.ledger = {}
        for item in initial_edges:
            edge, (balance, _) = _quote(item[0], item[1], item[2], item[2])
            if edge in self.ledger:
                raise ValueError('Duplicate initial edge')
            self.ledger[edge] = balance
        self.reference = dict(self.ledger)
        self.groups = {'clearing': {}, 'obligation': {}}
        self.ready = {}
        self.applied = set()
        self.incorporated = {kind: 0 for kind in self.groups}
        self.cumulative_clearing_gross_reduction = 0
        self.application_order = []
        self.trace = []
        self.time = 0
        self.message_count = 0
        self.snapshot()

    def _clock(self, time, message_count):
        if time is not None:
            if time < self.time:
                raise ValueError('Observation time moved backwards')
            self.time = time
        if message_count is not None:
            if type(message_count) is not int or message_count < self.message_count:
                raise ValueError('Transport count moved backwards')
            self.message_count = message_count

    def _store(self, kind, ident, node, value):
        group = self.groups[kind].setdefault(ident, {})
        old = group.get(node)
        if old is None and ((kind, ident) in self.ready or (kind, ident) in self.applied):
            raise ValueError('New endpoint reuses an already closed operation id')
        if old is not None:
            # Applied obligation status can progress committing -> committed;
            # economic terms and applied_at cannot change.
            if kind == 'obligation':
                keys = ('id', 'peer', 'amount', 'direction', 'description', 'before',
                        'after', 'digest', 'origin', 'applied_at', 'unit')
                if any(old.get(k) != value.get(k) for k in keys):
                    raise ValueError('Conflicting repeated obligation evidence')
            elif old != value:
                raise ValueError('Conflicting repeated receipt evidence')
            return
        group[node] = deepcopy(value)

    def observe_receipt(self, node, receipt, *, time=None, message_count=None):
        self._clock(time, message_count)
        node = str(node)
        verify_local_receipt(receipt)
        if receipt['node'] != node:
            raise ValueError('Receipt journal node mismatch')
        for change in receipt['changes']:
            edge, _ = _quote(node, change['peer'], change['before'], change['after'])
            self._known(edge)
        self._store('clearing', receipt['id'], node, receipt)
        self._complete_clearing(receipt['id'])
        return self._drain()

    def _complete_clearing(self, ident):
        key = ('clearing', ident)
        if key in self.applied or key in self.ready:
            return
        group = self.groups['clearing'][ident]
        participants = set(group)
        for receipt in group.values():
            participants.update(change['peer'] for change in receipt['changes'])
        if participants != set(group):
            return
        if len(group) < 3:
            raise ValueError('A clearing operation needs at least three identities')
        quotes, endpoints = {}, {}
        shared = None
        adjacency = {}
        for node, receipt in group.items():
            context = tuple(receipt.get(k) for k in ('condition', 'preimage', 'amount',
                            'protocol', 'hashlock_scheme', 'clearing_mode', 'policy', 'direction'))
            if shared is not None and context != shared:
                raise ValueError('Whole-operation hashlock context mismatch')
            shared = context
            adjacency[node] = set()
            for change in receipt['changes']:
                peer = change['peer']
                edge, quote = _quote(node, peer, change['before'], change['after'])
                self._known(edge)
                if edge in quotes and quotes[edge] != quote:
                    raise ValueError('Clearing endpoint quotes disagree')
                quotes[edge] = quote
                endpoints.setdefault(edge, set()).add(node)
                adjacency[node].add(peer)
        if any(len(nodes) != 2 for nodes in endpoints.values()):
            raise ValueError('Clearing edge lacks mirrored endpoint evidence')
        seen, todo = set(), [next(iter(group))]
        while todo:
            node = todo.pop()
            if node not in seen:
                seen.add(node)
                todo.extend(adjacency[node] - seen)
        if seen != participants:
            raise ValueError('Disconnected cycles reuse one operation id')
        if receipt.get('policy') == 'private-local-nonexpansion-v1':
            if sum(abs(before)-abs(after) for before, after in quotes.values()) <= 0:
                raise ValueError('Research clearing policy must strictly reduce whole-operation gross')
        self.ready[key] = quotes

    def observe_obligation(self, node, obligation, *, time=None, message_count=None):
        self._clock(time, message_count)
        node = str(node)
        # Proposed/approved/rejected entries do not constitute application.
        if obligation.get('applied_at') is None:
            return self.snapshot()
        if obligation.get('status') not in ('committing', 'committed'):
            raise ValueError('Applied obligation has unexpected protocol status')
        if obligation.get('unit') != 'TEST':
            raise ValueError('Unsupported obligation unit')
        amount = _integer(obligation['amount'])
        if amount <= 0 or type(obligation.get('origin')) is not bool:
            raise ValueError('Invalid applied obligation terms')
        edge, (before, after) = _quote(node, obligation['peer'], obligation['before'], obligation['after'])
        self._known(edge)
        expected = {'i_owe': -amount, 'peer_owes': amount}.get(obligation.get('direction'))
        if obligation['after'] - obligation['before'] != expected:
            raise ValueError('Obligation amount/direction mismatch')
        self._store('obligation', obligation['id'], node, obligation)
        key = ('obligation', obligation['id'])
        group = self.groups['obligation'][obligation['id']]
        if len(group) > 2:
            raise ValueError('An obligation must have exactly two endpoints')
        if len(group) == 2 and key not in self.applied:
            (a, first), (b, second) = list(group.items())
            if first['peer'] != b or second['peer'] != a or first['origin'] == second['origin']:
                raise ValueError('Obligation endpoint identities disagree')
            for field in ('id', 'amount', 'description', 'digest', 'unit'):
                if first.get(field) != second.get(field):
                    raise ValueError('Obligation authorization terms disagree')
            e1, q1 = _quote(a, b, first['before'], first['after'])
            e2, q2 = _quote(b, a, second['before'], second['after'])
            if e1 != e2 or q1 != q2:
                raise ValueError('Obligation endpoint quotes disagree')
            self.ready[key] = {e1: q1}
        return self._drain()

    def _known(self, edge):
        if edge not in self.ledger:
            raise ValueError('Application references an unknown original trustline')

    def _drain(self):
        progressed = True
        while progressed:
            progressed = False
            for key, quotes in list(self.ready.items()):
                if not all(self.ledger[edge] == quote[0] for edge, quote in quotes.items()):
                    continue
                for edge, (before, after) in quotes.items():
                    self.ledger[edge] = after
                    if key[0] == 'obligation':
                        self.reference[edge] += after - before
                    else:
                        self.cumulative_clearing_gross_reduction += abs(before)-abs(after)
                self.applied.add(key)
                self.incorporated[key[0]] += 1
                self.application_order.append(dict(kind=key[0], id=key[1], time=self.time,
                                                   message_count=self.message_count))
                del self.ready[key]
                progressed = True
        return self.snapshot()

    def snapshot(self):
        actual = sum(abs(value) for value in self.ledger.values())
        reference = sum(abs(value) for value in self.reference.values())
        counts = dict(self.incorporated)
        pending = {kind: len(groups)-counts[kind] for kind, groups in self.groups.items()}
        row = dict(time=self.time, message_count=self.message_count,
                   causal_fully_applied_gross=actual, same_posted_no_clearing_gross=reference,
                   gross_saving=reference-actual, incorporated=counts, pending=pending,
                   cumulative_clearing_gross_reduction=self.cumulative_clearing_gross_reduction,
                   fully_observed_dependency_blocked=len(self.ready))
        self.trace.append(row)
        return deepcopy(row)

    def observe_event(self, event, *, message_count=None):
        """Replay one adapter journal event; no actor/global-counter coupling."""
        self._clock(event.get('time'), message_count)
        for item in event.get('local_receipts', []):
            self.observe_receipt(item['node'], item['receipt'])
        for item in event.get('local_obligations', []):
            self.observe_obligation(item['node'], item['obligation'])
        return self.snapshot()

    def result(self):
        return dict(final=self.snapshot(), trace=deepcopy(self.trace),
                    application_order=deepcopy(self.application_order),
                    canonical_balances=[dict(nodes=list(edge), balance=value)
                                        for edge, value in sorted(self.ledger.items())],
                    dependency_blocked=[dict(kind=kind, id=ident) for kind, ident in self.ready])
