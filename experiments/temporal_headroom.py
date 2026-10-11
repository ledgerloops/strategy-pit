"""Serial, reliable temporal Headroom experiment; not a concurrent protocol.

Discovery and acceptance inherit neighbour-only Headroom messages. The simulator
serializes each external posting and complete search/settlement. Closed pairs are
removed before another search; tombstone generations survive reopening. No loss,
sleep, retries, stale packets, or interleaved posting is claimed here.
"""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import random

from headroom import Headroom, HeadroomNode, Token


class EpisodeNode(HeadroomNode):
    def residual(self, neighbor, direction):
        if direction == 1:
            return super().residual(neighbor, direction)
        cap, balance = self.incoming.get(neighbor, (0, 0))
        return cap - balance if balance > 0 and self.transport.restoration else 0


class TemporalHeadroom(Headroom):
    def __init__(self, *, restoration=True, reset_caps=False, seed=0,
                 search_budget=64, max_hops=16):
        self.restoration, self.reset_caps = restoration, reset_caps
        self.journal, self.episodes, self.generations = [], {}, Counter()
        self.posted_net = Counter()
        super().__init__({}, seed=seed, search_budget=search_budget, max_hops=max_hops)

    def _node(self, name):
        if name not in self.nodes:
            self.nodes[name] = EpisodeNode(name, self)
        return self.nodes[name]

    @staticmethod
    def pair(a, b):
        return tuple(sorted((a, b)))

    def _close(self, a, b):
        del self.nodes[a].owned[b]
        del self.nodes[b].incoming[a]
        del self.episodes[self.pair(a, b)]
        self.metrics['closures'] += 1

    def transfer(self, a, b, amount, time=0):
        if a == b or type(amount) is not int or amount <= 0:
            raise ValueError('distinct peers and positive integer transfer required')
        if self.events:
            raise ValueError('posting requires drained serial settlement')
        previous_debt = sum(self.snapshot().values())
        left, right = self._node(a), self._node(b)
        key = self.pair(a, b)
        if b in left.owned:
            debtor, creditor, delta = a, b, amount
        elif a in right.owned:
            debtor, creditor, delta = b, a, -amount
        else:
            debtor, creditor, delta = a, b, amount
        old = self.nodes[debtor].owned.get(creditor)
        if old is None:
            cap = value = amount
            fresh = True
        else:
            cap, value = old[0] + delta, old[1] + delta
            fresh = False
            if value <= 0:
                self._close(debtor, creditor)
                if value < 0:
                    debtor, creditor = creditor, debtor
                    cap = value = -value
                    fresh = True
        if value > 0:
            if self.reset_caps:
                cap = value
            self.nodes[debtor].owned[creditor] = [cap, value]
            self.nodes[creditor].incoming[debtor] = [cap, value]
            if fresh:
                self.generations[key] += 1
                self.episodes[key] = [self.generations[key], 0]
                self.metrics['openings'] += 1
                self.metrics['reopenings'] += int(self.generations[key] > 1)
            else:
                self.episodes[key][1] += 1
        self.metrics['external_transfer_volume'] += amount
        self.metrics['external_bilateral_netting'] += previous_debt + amount - sum(self.snapshot().values())
        self.posted_net[a] -= amount
        self.posted_net[b] += amount
        self.journal.append({'kind': 'transfer', 'a': a, 'b': b,
                             'amount': amount, 'time': time})
        self.audit()

    def drain(self):
        start = len(self.records)
        super().drain()
        for record in self.records[start:]:
            self.journal.append({'kind': 'cycle', **record})
            self.metrics['restored_volume'] += record['amount'] * record['directions'].count(-1)
            self.metrics['mixed_cycles'] += int(-1 in record['directions'])
            for a, b in zip(record['nodes'], record['nodes'][1:] + record['nodes'][:1]):
                self.episodes[self.pair(a, b)][1] += 1
        for node in list(self.nodes.values()):
            for peer, (_, value) in list(node.owned.items()):
                if value == 0:
                    self._close(node.name, peer)

    def search_from(self, root):
        if root not in self.nodes:
            return
        self.metrics['searches'] += 1
        self.nodes[root].receive(root, 'search', Token([root]))
        self.drain()
        self.audit()

    def audit(self):
        assert not self.events
        assert self.net_positions(self.snapshot()) == {n: v for n, v in self.posted_net.items() if v}
        for node in self.nodes.values():
            for peer, (cap, value) in node.owned.items():
                assert 0 < value <= cap
                assert self.nodes[peer].incoming[node.name] == [cap, value]
                assert self.pair(node.name, peer) in self.episodes


def replay_audit(sim):
    """Independent ledger replay, separate from protocol's state transitions."""
    ledger, ceiling = {}, {}
    episodes, generations = {}, Counter()
    for event in sim.journal:
        if event['kind'] == 'transfer':
            a, b, amount = event['a'], event['b'], event['amount']
            pair = tuple(sorted((a, b)))
            old_direction = (a,b) if (a,b) in ledger else ((b,a) if (b,a) in ledger else None)
            if (b, a) in ledger:
                key = (b, a)
                value = ledger[key] - amount
                if value <= 0:
                    del ledger[key]
                    del ceiling[key]
                    if value < 0:
                        ledger[a, b] = ceiling[a, b] = -value
                else:
                    ledger[key] = value
                    ceiling[key] -= amount
            else:
                key = (a, b)
                ledger[key] = ledger.get(key, 0) + amount
                ceiling[key] = ceiling.get(key, 0) + amount
            if sim.reset_caps:
                for key in [(a, b), (b, a)]:
                    if key in ledger:
                        ceiling[key] = ledger[key]
            new_direction = (a,b) if (a,b) in ledger else ((b,a) if (b,a) in ledger else None)
            if new_direction is None:
                episodes.pop(pair, None)
            elif new_direction != old_direction:
                generations[pair] += 1
                episodes[pair] = [generations[pair], 0]
            else:
                episodes[pair][1] += 1
        else:
            before = Headroom.net_positions(ledger)
            nodes, amount = event['nodes'], event['amount']
            assert sum(event['directions']) > 0
            for a, b, direction in zip(nodes, nodes[1:] + nodes[:1], event['directions']):
                key = (a, b) if direction == 1 else (b, a)
                assert key in ledger, 'cannot restore a closed relationship'
                ledger[key] -= direction * amount
                assert 0 <= ledger[key] <= ceiling[key]
                pair = tuple(sorted(key))
                episodes[pair][1] += 1
                if not ledger[key]:
                    del ledger[key]
                    del ceiling[key]
                    del episodes[pair]
            assert Headroom.net_positions(ledger) == before
    assert ledger == sim.snapshot()
    assert episodes == sim.episodes
    assert generations == sim.generations
    assert ceiling == {(n.name, p): pair[0] for n in sim.nodes.values() for p, pair in n.owned.items()}
    return True


def benchmark():
    cases = []
    # Exploratory seeds fixed before comparison; no held-out claim.
    for seed in [101, 102, 103, 104]:
        rng = random.Random(seed)
        events = [(t, *rng.sample(range(16), 2), rng.randint(1, 20)) for t in range(240)]
        for treatment in ['cancellation', 'headroom', 'reset_caps']:
            sim = TemporalHeadroom(seed=seed, restoration=treatment != 'cancellation',
                                   reset_caps=treatment == 'reset_caps')
            area = 0
            for time, a, b, amount in events:
                sim.transfer(a, b, amount, time)
                sim.search_from(a)
                area += sum(sim.snapshot().values())
            replay_audit(sim)
            cases.append({'seed': seed, 'treatment': treatment,
                          'final_debt': sum(sim.snapshot().values()), 'debt_area': area,
                          'cycle_debt_reduction': sum(r['debt_reduction'] for r in sim.records),
                          'metrics': dict(sim.metrics), 'audit': True,
                          'input_sha256': hashlib.sha256(json.dumps(events).encode()).hexdigest(),
                          'pending_transfers': 0, 'unfinished_settlements': 0})
    return {'complete': True, 'model': 'serialized reliable strict-zero episodes',
            'config': {'nodes': 16, 'transfers': 240, 'searches_per_transfer': 1,
                       'search_budget': 64, 'max_hops': 16, 'seeds': [101,102,103,104]},
            'sources': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in [Path(__file__), Path(__file__).with_name('headroom.py')]},
            'cases': cases}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    Path(args.output).write_text(json.dumps(benchmark(), indent=2) + '\n')
