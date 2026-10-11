"""Strict economic episodes on the existing debtor-owned temporal substrate.

Pair state installation is the same atomic bilateral adapter used for external
posting, not distributed replicated agreement. Routing/admission reads only the
receiving endpoint's episode copy. Old transport identities are tombstones, not
permission to search. Reliable transport and staged commits remain unchanged.
"""
from dataclasses import dataclass
from copy import deepcopy
from temporal_protocol import TemporalProtocol, TemporalDFSNode, TemporalNumbatNode


@dataclass
class Episode:
    number: int = 0
    revision: int = 0
    balance: int = 0  # positive means this endpoint owes its peer
    ceiling: int = 0
    live: bool = False


@dataclass
class EpisodeMessage:
    source: object
    episode: int
    revision: int
    payload: object


class EpisodeNode:
    def __init__(self, name, sim):
        super().__init__(name, sim)
        self.episodes = {}
        self.admitted_tokens = set()

    def reject_prepare(self, tx):
        self.sim.metrics['aborted'] += 1
        if tx.prepared:
            self.sim.send(self.name, tx.prepared[-1], 'abort', tx)
        else:
            self.finish_from_cycle(tx)

    def receive(self, kind, payload):
        if isinstance(payload, EpisodeMessage):
            message, payload = payload, payload.payload
            token = payload.token if hasattr(payload, 'token') else payload
            ident = token.ident
            episode = self.episodes.get(message.source, Episode())
            if kind in ('step', 'prepare'):
                if (not episode.live or episode.number != message.episode or
                        episode.revision != message.revision):
                    self.sim.metrics['stale_episode_rejections'] += 1
                    if kind == 'step':
                        self.finish(payload)
                    else:
                        self.reject_prepare(payload)
                    return
                self.admitted_tokens.add(ident)
            elif kind == 'commit':
                if ident in self.committed:
                    self.sim.metrics['duplicate_commit_receipts'] += 1
                    return
                # Authority is the still-held local reservation, never an old
                # packet or a newly reopened relationship with the same peer.
                if ident not in self.reservations and ident not in self.committed:
                    self.sim.metrics['unknown_control_rejections'] += 1
                    return
            elif ident not in self.admitted_tokens:
                self.sim.metrics['unknown_control_rejections'] += 1
                return
        if kind == 'step':
            self.admitted_tokens.add(payload.ident)
        if kind == 'prepare':
            tx = payload
            neighbor = tx.nodes[(tx.nodes.index(self.name) + 1) % len(tx.nodes)]
            episode = self.episodes.get(neighbor, Episode())
            quote = getattr(tx.token, 'episode_quotes', {}).get((self.name, neighbor))
            if not episode.live or quote is None or quote != (episode.number, episode.revision):
                self.sim.metrics['stale_episode_rejections'] += 1
                self.reject_prepare(tx)
                return
        super().receive(kind, payload)


class EpisodeDFSNode(EpisodeNode, TemporalDFSNode):
    pass


class EpisodeNumbatNode(EpisodeNode, TemporalNumbatNode):
    pass


class EpisodeTemporalProtocol(TemporalProtocol):
    """Drop-in temporal baseline; all algorithms use identical episode admission."""
    def _post(self, a, b, amount, requested):
        # Install endpoint actors before the frozen base's posting routine.
        for name in (a, b):
            if name not in self.nodes:
                cls = EpisodeNumbatNode if self.algorithm == 'numbat' else EpisodeDFSNode
                self.nodes[name] = cls(name, self)
                if self.searches_enabled:
                    self.schedule(self.time + self.random.randrange(self.retry_interval), name, 'wake', None)
        super()._post(a, b, amount, requested)

    def record_ledger(self, kind, source, target, delta, txid=None):
        super().record_ledger(kind, source, target, delta, txid)
        # Pair-local economic write adapter. This uses no other pair, route,
        # snapshot or global counter to decide episode boundaries or consent.
        left, right = self.nodes[source], self.nodes[target]
        old = left.episodes.get(target, Episode())
        signed = left.outgoing.get(target, 0) - right.outgoing.get(source, 0)
        closing = old.live and (not signed or signed * old.balance < 0)
        opening = bool(signed) and (not old.live or closing)
        if closing:
            self.metrics['episode_closures'] += 1
        if opening:
            self.metrics['episode_openings'] += 1
            self.metrics['episode_reopenings'] += old.number > 0
        number = old.number + opening
        ceiling = (abs(signed) if opening else
                   (0 if not signed else old.ceiling +
                    (abs(signed) - abs(old.balance) if kind == 'transfer' else 0)))
        revision = 0 if opening else old.revision + 1
        left.episodes[target] = Episode(number, revision, signed, ceiling, bool(signed))
        right.episodes[source] = Episode(number, revision, -signed, ceiling, bool(signed))

    def send(self, source, dest, kind, payload):
        actor = self.nodes[source]
        episode = actor.episodes.get(dest, Episode())
        token = payload.token if hasattr(payload, 'token') else payload
        actor.admitted_tokens.add(token.ident)
        if kind in ('step', 'prepare'):
            if not hasattr(token, 'episode_quotes'):
                token.episode_quotes = {}
            # Backtracking must not overwrite an earlier directed observation.
            if actor.outgoing.get(dest, 0) > 0:
                token.episode_quotes[(source, dest)] = (episode.number, episode.revision)
        message = EpisodeMessage(source, episode.number, episode.revision, deepcopy(payload))
        super().send(source, dest, kind, message)
