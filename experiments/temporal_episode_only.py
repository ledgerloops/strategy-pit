"""Cancellation-only admission by live economic episode, not ledger revision.

No credit restoration and no Headroom authority. Current owned capacity and
reservations are checked by the unchanged settlement implementation.
"""
from temporal_episodes import (Episode, EpisodeMessage, EpisodeNode,
    EpisodeDFSNode, EpisodeNumbatNode, EpisodeTemporalProtocol)


class EpisodeOnlyAdmission:
    def receive(self, kind, payload):
        if isinstance(payload, EpisodeMessage):
            message, payload = payload, payload.payload
            token = payload.token if hasattr(payload, 'token') else payload
            ident = token.ident
            episode = self.episodes.get(message.source, Episode())
            if kind in ('step', 'prepare'):
                if not episode.live or episode.number != message.episode:
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
                if ident not in self.reservations:
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
            if not episode.live or quote is None or quote[0] != episode.number:
                self.sim.metrics['stale_episode_rejections'] += 1
                self.reject_prepare(tx)
                return
        # Explicitly skip only strict EpisodeNode admission. Its initialization,
        # rejection helper and the frozen temporal ledger/DFS layers stay intact.
        return super(EpisodeNode, self).receive(kind, payload)


class EpisodeOnlyDFSNode(EpisodeOnlyAdmission, EpisodeDFSNode):
    pass


class EpisodeOnlyNumbatNode(EpisodeOnlyAdmission, EpisodeNumbatNode):
    pass


class EpisodeOnlyTemporalProtocol(EpisodeTemporalProtocol):
    def _post(self, a, b, amount, requested):
        for name in (a,b):
            if name not in self.nodes:
                cls=EpisodeOnlyNumbatNode if self.algorithm=='numbat' else EpisodeOnlyDFSNode
                self.nodes[name]=cls(name,self)
                if self.searches_enabled:
                    self.schedule(self.time+self.random.randrange(self.retry_interval),name,'wake',None)
        super()._post(a,b,amount,requested)
