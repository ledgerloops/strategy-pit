"""One isolated local ordering experiment for comfort-as-headroom research.

Perform the original neighbour shuffle, then stably prefer eligible links whose
unit move reduces absolute local debt. Helping links remain eligible and are
tried when no debt-reducing untried choice remains. The wrapper reads only its
actor's own links and preserves shuffle RNG consumption and within-class order.

The underlying actors, bilateral checks, strictly gross-decreasing cycle rule,
serialized messages and prepare/commit/cleanup are unchanged. Cancellation-only
choices all reduce debt, so its ordering is exactly unchanged. This static serial
research variant makes no privacy, distributed atomicity or production claim.
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comfort_headroom import Network

VARIANT = 'comfort-headroom-local-decrease-first-v1'


class DecreaseFirstShuffle:
    def __init__(self, rng, own_links):
        self.rng = rng
        self.own_links = own_links

    def shuffle(self, peers):
        self.rng.shuffle(peers)
        # Python's sort is stable: preserve every shuffled tie and introduce no
        # extra random draw, rejection, capacity change, or external observation.
        peers.sort(key=lambda peer: abs(self.own_links[peer][0]+1)-abs(self.own_links[peer][0]))


class DecreaseFirstNetwork(Network):
    def __init__(self, edges, seed=0):
        super().__init__(edges,seed)
        for actor in self.actors.values():
            actor.rng = DecreaseFirstShuffle(actor.rng,actor.links)
