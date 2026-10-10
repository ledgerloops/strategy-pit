"""Endpoint-local alternating turns, separate from clearing/settlement.

One instance belongs to one endpoint of ONE neighbour relationship. The lower
node ID initially holds the turn. Wire messages must travel over a reliable
retry adapter: loss is handled there, not by guessing that a silent peer died.
Delivery may reorder or duplicate messages. A grant carries a data barrier, so
it cannot take effect before the preceding turn's messages have arrived.

Call enqueue(payload), receive(wire_message), and pump() on local scheduling
opportunities. emit(message) sends only to this endpoint's direct neighbour;
deliver(payload) hands accepted data to the local application. Controls must be
counted in benchmark budgets. There is no topology access or global coordinator.

This is flow control, not atomic settlement. Never retain a turn while waiting
for another neighbour: payload delivery releases no external lock. Fairness
requires eventual delivery, awake endpoints, and local pump scheduling. Crashes
with lost state and malicious peers are outside this prototype's fault model.
"""
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class TurnMessage:
    kind: str
    epoch: int
    sequence: int = 0
    payload: Any = None


class LocalTurn:
    def __init__(self, node, peer, emit: Callable, deliver: Callable, *, max_batch=8):
        if node == peer or max_batch < 1:
            raise ValueError('distinct endpoints and positive max_batch required')
        self.node, self.peer = node, peer
        self.emit, self.deliver = emit, deliver
        self.max_batch = max_batch
        self.initial_owner = node < peer
        self.epoch = 0
        self.outbox = deque()
        self.sent = 0
        self.requested_epoch = -1
        self.remote_request = -1
        self.pending_grant = None
        self.received = {}  # epoch -> next expected sequence (duplicate frontier)
        self.buffer = {}  # (epoch, sequence) -> payload
        self.controls_sent = 0
        self.payloads_sent = 0

    @property
    def owns_turn(self):
        return self.initial_owner == (self.epoch % 2 == 0)

    def enqueue(self, payload):
        self.outbox.append(payload)
        self.pump()

    def _control(self, kind, epoch, sequence=0):
        self.controls_sent += 1
        self.emit(TurnMessage(kind, epoch, sequence))

    def pump(self):
        if not self.owns_turn:
            if self.outbox and self.requested_epoch < self.epoch + 1:
                self.requested_epoch = self.epoch + 1
                self._control('request', self.epoch + 1)
            return
        peer_waiting = self.remote_request >= self.epoch + 1
        # Once a peer asks, at most the remainder of this turn's batch is sent.
        allowance = max(0, self.max_batch - self.sent) if peer_waiting else self.max_batch
        for _ in range(min(len(self.outbox), allowance)):
            payload = self.outbox.popleft()
            sequence = self.sent
            self.sent += 1
            self.payloads_sent += 1
            self.emit(TurnMessage('data', self.epoch, sequence, payload))
        if peer_waiting:
            count = self.sent
            self._advance(self.epoch + 1)  # Relinquish BEFORE emitting the grant.
            self._control('grant', self.epoch, count)
            self.pump()  # Request a later turn if our queue is still nonempty.

    def receive(self, message):
        if message.kind == 'request':
            self.remote_request = max(self.remote_request, message.epoch)
        elif message.kind == 'grant':
            if message.epoch <= self.epoch:
                return  # An already applied grant cannot revive an old turn.
            if message.epoch != self.epoch + 1 or self.owns_turn:
                raise ValueError('grant inconsistent with local turn history')
            if self.pending_grant is not None and self.pending_grant != message:
                raise ValueError('conflicting grant')
            self.pending_grant = message
            self._accept_grant()
        elif message.kind == 'data':
            if message.epoch < self.epoch:
                return  # Grant barriers prove earlier epochs are already complete.
            # Peer's ownership parity is independent of locally observed grants.
            peer_owns = self.initial_owner != (message.epoch % 2 == 0)
            if not peer_owns or message.epoch > self.epoch or message.sequence < 0:
                raise ValueError('data inconsistent with peer turn')
            next_sequence = self.received.get(message.epoch, 0)
            if message.sequence < next_sequence:
                return
            self.buffer.setdefault((message.epoch, message.sequence), message.payload)
            while (message.epoch, next_sequence) in self.buffer:
                payload = self.buffer.pop((message.epoch, next_sequence))
                next_sequence += 1
                self.received[message.epoch] = next_sequence
                self.deliver(payload)
            self._accept_grant()
        else:
            raise ValueError('unknown turn message')
        self.pump()

    def _accept_grant(self):
        grant = self.pending_grant
        if grant is not None and self.received.get(self.epoch, 0) == grant.sequence:
            self._advance(grant.epoch)
            self.pending_grant = None

    def _advance(self, epoch):
        self.epoch = epoch
        self.sent = 0
        # Old epochs need no permanent duplicate-ID archive: barriers guarantee
        # their complete delivery, and receive rejects their delayed duplicates.
        self.received = {e: n for e, n in self.received.items() if e >= epoch}
        self.buffer = {key: value for key, value in self.buffer.items() if key[0] >= epoch}
