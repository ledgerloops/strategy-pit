"""True neighbour turn protocol layered over TemporalProtocol reliable delivery.

Pair epochs survive zero-balance closure: historical transport grace preserves
these identities for old packets and future reopening. The scheduler dispatches
wire messages; each LocalTurn alone decides requests, grants and payload release.
All wire controls bypass the gate, otherwise a waiting request could deadlock.
"""
from copy import deepcopy

from local_turns import LocalTurn
from temporal_protocol import TemporalProtocol


class TurnTemporalProtocol(TemporalProtocol):
    def __init__(self, *args, turn_batch=8, **kwargs):
        transport = kwargs.pop('transport', 'local_turns')
        if transport != 'local_turns':
            raise ValueError('TurnTemporalProtocol requires transport=local_turns')
        if turn_batch < 1:
            raise ValueError('positive turn_batch required')
        self.turn_batch = turn_batch
        self.turn_endpoints = {}
        # Underlying reliability is concurrent. Only endpoint gates own turns.
        super().__init__(*args, transport='concurrent', **kwargs)

    def _endpoint(self, node, peer):
        key = node, peer
        if key not in self.turn_endpoints:
            def emit(message):
                if message.kind != 'data':
                    self.metrics['turn_controls'] += 1
                # Reliability ACKs and retries never pass through LocalTurn.
                TemporalProtocol.send(self, node, peer, 'turn_' + message.kind, message)

            def deliver(payload):
                kind, value = payload
                self.metrics['application_deliveries'] += 1
                self.nodes[node].receive(kind, deepcopy(value))

            self.turn_endpoints[key] = LocalTurn(node, peer, emit, deliver,
                                                 max_batch=self.turn_batch)
        return self.turn_endpoints[key]

    @staticmethod
    def _drive(endpoint):
        # These are immediate local scheduling opportunities, not a global
        # ownership decision. Incoming request processing still bounds handoff.
        while endpoint.owns_turn and endpoint.outbox:
            endpoint.pump()

    def send(self, source, dest, kind, payload):
        assert frozenset((source, dest)) in self.channels, 'Non-neighbour message'
        self.metrics['application_messages'] += 1
        self.metrics['application_messages_' + kind] += 1
        endpoint = self._endpoint(source, dest)
        endpoint.enqueue((kind, deepcopy(payload)))
        self._drive(endpoint)

    def _delivery(self, ident):
        env = self.pending.get(ident)
        if env is None:
            return
        if self.awake_at(env.dest, self.time) > self.time:
            self.metrics['sleep_dropped'] += 1
            return
        if ident not in self.seen:
            self.seen.add(ident)
            self.metrics['wire_deliveries'] += 1
            endpoint = self._endpoint(env.dest, env.source)
            endpoint.receive(deepcopy(env.payload))
            self._drive(endpoint)
        else:
            self.metrics['duplicates_suppressed'] += 1
        self.metrics['ack_attempts'] += 1
        if self.random.random() < self.ack_loss:
            self.metrics['ack_dropped'] += 1
        else:
            self.schedule(self.time + self.random.randint(1, self.max_delay),
                          None, 'ack', ident)

    def drain(self, max_events=1000000):
        result = super().drain(max_events)
        assert not any(endpoint.outbox or endpoint.pending_grant
                       for endpoint in self.turn_endpoints.values())
        assert self.metrics['application_messages'] == self.metrics['application_deliveries']
        assert self.metrics['messages'] == self.metrics['wire_deliveries']
        return result
