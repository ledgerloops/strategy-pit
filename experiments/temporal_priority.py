"""Prospective settlement-priority queue for genuine neighbour turn endpoints.

Only not-yet-sent application messages are reordered. Wire sequence numbers,
grants, ACKs and retransmissions are untouched. Each endpoint chooses using its
own queue alone: commit/abort/finish/prepare precede exploration, with at most
four such messages before a waiting exploration message. This does not promise
better clearing: it trades search latency for earlier release of reservations.
"""
from collections import deque
from temporal_turns import TurnTemporalProtocol


class PriorityOutbox:
    def __init__(self, burst=4):
        if burst < 1:
            raise ValueError('positive burst required')
        self.urgent, self.exploration = deque(), deque()
        self.burst, self.streak = burst, 0
        self.priority_pops = 0

    def append(self, payload):
        queue = self.exploration if payload[0] == 'step' else self.urgent
        queue.append(payload)

    def popleft(self):
        if self.urgent and (not self.exploration or self.streak < self.burst):
            if self.exploration:
                self.priority_pops += 1
            self.streak += 1
            return self.urgent.popleft()
        self.streak = 0
        return self.exploration.popleft()

    def __len__(self):
        return len(self.urgent) + len(self.exploration)


class PriorityTurnTemporalProtocol(TurnTemporalProtocol):
    def __init__(self, *args, priority_burst=4, **kwargs):
        if priority_burst < 1:
            raise ValueError('positive priority_burst required')
        self.priority_burst = priority_burst
        super().__init__(*args,**kwargs)

    def _endpoint(self,node,peer):
        endpoint = super()._endpoint(node,peer)
        if not isinstance(endpoint.outbox,PriorityOutbox):
            assert not endpoint.outbox
            endpoint.outbox = PriorityOutbox(self.priority_burst)
        return endpoint
