"""Frozen synthetic cancellation-only workloads for the MDG2 comparison."""
import hashlib
import json
from pathlib import Path
import random


def build():
    cases = []
    for family, n, m in [('ring32', 32, 32), ('sparse64', 64, 256), ('medium256', 256, 1536)]:
        for seed in (0, 1, 2):
            rng = random.Random(seed)
            nodes = [f'n{i:04d}' for i in range(n)]
            edges = {(nodes[i], nodes[(i+1) % n]) for i in range(n)}
            while len(edges) < m:
                a, b = rng.sample(nodes, 2)
                if (b, a) not in edges:
                    edges.add((a, b))
            amounts = [dict(source=a, target=b, amount=rng.randint(1, 100)) for a, b in sorted(edges)]
            case = dict(name=f'{family}-seed{seed}', family=family, seed=seed, nodes=nodes, edges=amounts)
            encoded = json.dumps(case, sort_keys=True, separators=(',', ':')).encode()
            case['sha256'] = hashlib.sha256(encoded).hexdigest()
            cases.append(case)
    return dict(schema_version=1, purpose='MDG2 2026-10-25: prospective frozen comparison',
                source_commit='1e0e87d4859e470d87b430b488c64db3c08df6ae',
                objective='Maximize sum of debt reductions on original arcs; preserve every node net position; no added credit.',
                unit='synthetic integer units, not currency',
                input_policy='Strongly connected directed base ring plus seeded random arcs; no self or opposite arcs; weights 1..100.',
                repeats=3, ledgerloops_config=dict(search_horizon=500, message_cutoff=250000,
                  max_delay=5, retry_interval=50, max_hops=100, search_budget=256, max_events=5000000),
                timing='Warm imports; fresh algorithm state each repeat; include graph/engine construction and clearing; exclude input loading and audit. Run implementations sequentially.',
                limits=['Exactly-once reliable messages; no losses, crashes, arrivals or hostile participants.',
                        'Message cap stops new search admission, then drains in-flight work; report overshoot.',
                        'Communication bytes are compact JSON application envelopes, not TCP/TLS/HTTP or real network traffic.',
                        'Cycles public educational solver is a centralized reference, not a hosted production benchmark.'],
                cases=cases)


if __name__ == '__main__':
    out = Path(__file__).with_name('workloads.json')
    out.write_text(json.dumps(build(), indent=2) + '\n')
    print(out)
