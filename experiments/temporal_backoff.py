"""Local reservation-specific instrumentation and fixed initiation backoff.

Routing, episode admission and settlement are unchanged. Metrics are write-only
observations. Only an actor's own capacity/reservations and received packet are
used to trigger backoff; the simulator factory names only transfer endpoints.
"""
from temporal_episodes import (Episode, EpisodeMessage, EpisodeTemporalProtocol,
                               EpisodeDFSNode, EpisodeNumbatNode)


class BackoffNode:
    def __init__(self, name, sim):
        super().__init__(name, sim)
        self.backoff_level = 0
        self.resume_at = 0

    def prepare_reason(self, packet):
        tx = packet.payload if isinstance(packet, EpisodeMessage) else packet
        if isinstance(packet, EpisodeMessage):
            incoming = self.episodes.get(packet.source, Episode())
            if not incoming.live or incoming.number != packet.episode or incoming.revision != packet.revision:
                return 'episode'
        neighbor = tx.nodes[(tx.nodes.index(self.name) + 1) % len(tx.nodes)]
        episode = self.episodes.get(neighbor, Episode())
        quote = getattr(tx.token, 'episode_quotes', {}).get((self.name, neighbor))
        if not episode.live or quote is None or quote != (episode.number, episode.revision):
            return 'episode'
        if self.available(neighbor) <= 0:
            return 'reserved' if self.outgoing.get(neighbor, 0) > 0 else 'depleted'
        return 'available'

    def receive(self, kind, payload):
        if kind == 'wake' and self.sim.searches_enabled and self.sim.backoff_enabled and self.sim.time < self.resume_at:
            # Same periodic clock/jitter as the base actor; no new random draws.
            self.sim.schedule(self.sim.time + self.sim.retry_interval +
                              self.sim.random.randrange(self.sim.retry_interval),
                              self.name, 'wake', None)
            self.sim.metrics['backoff_suppressed_wakes'] += 1
            return
        if kind == 'prepare':
            reason = self.prepare_reason(payload)
            self.sim.metrics['prepare_local_' + reason] += 1
            if reason == 'reserved' and self.sim.backoff_enabled:
                self.backoff_level = min(3, self.backoff_level + 1)
                self.resume_at = self.sim.time + self.sim.retry_interval * 2**self.backoff_level
                self.sim.metrics['backoff_triggers'] += 1
        tx = payload.payload if isinstance(payload, EpisodeMessage) else payload
        actual_commit = kind == 'commit' and tx.token.ident in self.reservations and tx.token.ident not in self.committed
        super().receive(kind, payload)
        if actual_commit and tx.token.ident in self.committed:
            self.backoff_level = max(0, self.backoff_level - 1)


class BackoffDFSNode(BackoffNode, EpisodeDFSNode):
    pass


class BackoffNumbatNode(BackoffNode, EpisodeNumbatNode):
    pass


class BackoffTemporalProtocol(EpisodeTemporalProtocol):
    def __init__(self, *args, backoff_enabled=True, **kwargs):
        self.backoff_enabled = backoff_enabled
        super().__init__(*args, **kwargs)

    def _post(self, a, b, amount, requested):
        for name in (a, b):
            if name not in self.nodes:
                cls = BackoffNumbatNode if self.algorithm == 'numbat' else BackoffDFSNode
                self.nodes[name] = cls(name, self)
                if self.searches_enabled:
                    self.schedule(self.time + self.random.randrange(self.retry_interval), name, 'wake', None)
        super()._post(a, b, amount, requested)
