"""Decrease-first Headroom: one local ordering change, same settlement protocol.

The frozen Headroom search is copied verbatim except candidate ordering: prefer
reducing a present debt, then higher capacity, with randomized exact ties. Reverse
residual arcs remain available after decreasing alternatives. This is bounded
heuristic search with serialized initiators, NOT an optimal or concurrent protocol.
The benchmark's MCF and record replay are offline references, never routing inputs.
"""
from headroom import Headroom, HeadroomNode, Settlement


class DecreaseFirstNode(HeadroomNode):
    def search(self, token):
        if token.hops >= self.transport.search_budget:
            self.transport.metrics['budget_exhaustions'] += 1
            return
        candidates = [(n, 1) for n in self.owned]
        candidates += [(n, -1) for n in self.incoming]
        candidates = [(n, d) for n, d in candidates
                      if (n, d) not in token.tried[-1] and self.residual(n, d) > 0]
        self.transport.rng.shuffle(candidates)
        # Prefer decreases before restorations, then higher local capacity.
        candidates.sort(key=lambda nd: (nd[1], self.residual(*nd)), reverse=True)
        for neighbor, direction in candidates:
            token.tried[-1].add((neighbor, direction))
            arc = (self.name, neighbor, direction, self.residual(neighbor, direction))
            if neighbor in token.path:
                start = token.path.index(neighbor)
                cycle = token.arcs[start:] + [arc]
                if sum(a[2] for a in cycle) <= 0:
                    continue
                tx = Settlement(token.path[start:], cycle, min(a[3] for a in cycle))
                self.transport.metrics['proposals'] += 1
                self.transport.send(self.name, neighbor, 'prepare', tx)
                return
            if len(token.path) >= self.transport.max_hops:
                continue
            token.path.append(neighbor)
            token.arcs.append(arc)
            token.tried.append(set())
            token.hops += 1
            self.transport.send(self.name, neighbor, 'search', token)
            return
        if len(token.path) > 1:
            token.path.pop()
            token.arcs.pop()
            token.tried.pop()
            token.hops += 1
            self.transport.send(self.name, token.path[-1], 'search', token)
        else:
            self.transport.metrics['exhausted_searches'] += 1


class DecreaseFirstHeadroom(Headroom):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for node in self.nodes.values():
            node.__class__ = DecreaseFirstNode


def main():
    import argparse
    import hashlib
    import json
    from pathlib import Path
    import platform
    import time
    from dfs_benchmark import read_graph, mcf_reference, replay
    from headroom_benchmark import ReductionOnlyNode, audit_records, fixtures
    from simulate import aggregate, scenario

    root = Path(__file__).parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, default=root / 'results/headroom-search.json')
    args = parser.parse_args()
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    sources = ('headroom.py', 'headroom_search.py', 'headroom_benchmark.py',
               'simulate.py', 'dfs_benchmark.py')
    report = dict(complete=False, python=platform.python_version(),
                  source_sha256={name: digest(root / name) for name in sources},
                  input_sha256=digest(args.input),
                  config=dict(search_budget=64, max_hops=64, rounds=2),
                  ordering_frozen_before_training=True, training_seeds=[101, 102],
                  sarafu_seeds=[0, 1], cases=[],
                  assumptions=['Serialized searches and settlements; node-local routing only.',
                    'Same per-search hop budget and initiator rounds, not equal messages or CPU.',
                    'Static original caps, reliable messages, honest peers, no crashes.',
                    'All setup advertisements included in message counts.',
                    'Offline MCF/auditor never influence routing.',
                    'No parameter tuning or variant selection based on training results.',
                    'Numbat postpass skipped: published pipeline result has no saved residual ledger.'],
                  baseline_reference=dict(file='headroom.json', sha256=digest(root / 'results/headroom.json')))

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')

    def run_case(label, caps, initial, seed, phase):
        total = sum(caps.values())
        optimum = total - sum(replay(caps, mcf_reference(caps)).values())
        entry = dict(name=label, phase=phase, seed=seed,
                     nodes=len({node for edge in caps for node in edge}), edges=len(caps),
                     graph_sha256=hashlib.sha256(json.dumps(sorted((a,b,v) for (a,b),v in caps.items())).encode()).hexdigest(),
                     initial_debt=total, starting_debt=sum(initial.values()),
                     mcf_cleared_percent=100 * optimum / total, methods={})
        for method in ('capacity-first', 'decrease-first', 'reduction-only'):
            started = time.monotonic()
            cls = DecreaseFirstHeadroom if method == 'decrease-first' else Headroom
            sim = cls(caps, initial, seed=seed, search_budget=64, max_hops=64)
            if method == 'reduction-only':
                for node in sim.nodes.values():
                    node.__class__ = ReductionOnlyNode
            final = sim.run(2)
            checked = audit_records(caps, initial, sim.records, final)
            entry['methods'][method] = dict(cleared_percent=100 * (total-sum(final.values()))/total,
                                           residual_debt=sum(final.values()), metrics=dict(sim.metrics),
                                           audit=checked, seconds_with_audit=time.monotonic()-started)
        report['cases'].append(entry)
        save()
        print(phase, label, seed, {k:round(v['cleared_percent'],5) for k,v in entry['methods'].items()}, flush=True)

    save()
    for name, caps, initial in fixtures():
        run_case(name, caps, initial, 101, 'regression')
    for count in (24, 72):
        for topology in ('sparse', 'dense', 'community', 'disconnected'):
            for seed in (101, 102):
                caps = aggregate(scenario(topology + '-static', seed, count))
                run_case(f'{topology}-{count}', caps, caps, seed, 'synthetic-training')
    caps = read_graph(args.input.read_text())
    for seed in (0, 1):
        run_case('sarafu-50k-cold', caps, caps, seed, 'sarafu-validation')
    report['complete'] = True
    save()


if __name__ == '__main__':
    main()
