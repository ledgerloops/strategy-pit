"""Simulator-only copy/cache optimization; no changed protocol or RNG calls.

Never substitute into a running benchmark. Each adapter keeps the final transport
snapshot deepcopy and the receive-side deepcopy. Only the redundant pre-snapshot
copy is removed. Retry byte accounting caches repr length of that private immutable
snapshot, not actor-owned state. Requires ordinary protocol dataclasses with pure
repr/deepcopy (not custom side-effecting serialization objects).
"""
from temporal_protocol import TemporalProtocol
from temporal_episodes import Episode, EpisodeMessage, EpisodeTemporalProtocol
from concurrent_headroom import ConcurrentHeadroom


class CachedAttempt:
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
        if not hasattr(env, '_payload_repr_size'):
            env._payload_repr_size = len(repr(env.payload).encode())
        self.metrics['payload_repr_bytes'] += env._payload_repr_size
        if self.random.random() < self.loss:
            self.metrics['data_dropped'] += 1
        else:
            self.schedule(self.time + self.random.randint(1,self.max_delay), None, 'delivery', ident)
        self.schedule(self.time + self.retransmit, None, 'attempt', ident)


class FastEpisodeTemporalProtocol(CachedAttempt, EpisodeTemporalProtocol):
    def send(self, source, dest, kind, payload):
        actor = self.nodes[source]
        episode = actor.episodes.get(dest, Episode())
        token = payload.token if hasattr(payload, 'token') else payload
        actor.admitted_tokens.add(token.ident)
        if kind in ('step', 'prepare'):
            if not hasattr(token, 'episode_quotes'):
                token.episode_quotes = {}
            if actor.outgoing.get(dest, 0) > 0:
                token.episode_quotes[(source, dest)] = (episode.number, episode.revision)
        # TemporalProtocol.send still deepcopies this entire wrapper once.
        message = EpisodeMessage(source, episode.number, episode.revision, payload)
        TemporalProtocol.send(self, source, dest, kind, message)


class FastConcurrentHeadroom(CachedAttempt, ConcurrentHeadroom):
    def send(self, source, dest, kind, payload):
        actor = self.nodes[source]
        ep = actor.episodes.get(dest, Episode())
        token = payload.token if hasattr(payload, 'token') else payload
        actor.admitted_tokens.add(token.ident)
        TemporalProtocol.send(self,source,dest,kind,EpisodeMessage(source,ep.number,ep.revision,payload))
