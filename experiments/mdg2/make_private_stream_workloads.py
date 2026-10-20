"""Fixed transaction offers for actual private hashlock actors."""
import hashlib
import json
from pathlib import Path
import random

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    plan = json.loads((HERE / 'private-stream-plan.json').read_text())
    cases = []
    for seed in plan['seeds']:
        rng = random.Random(seed)
        nodes = [f'participant_{i:03d}' for i in range(plan['nodes'])]
        pairs = {tuple(sorted((i, (i + 1) % len(nodes)))) for i in range(len(nodes))}
        while len(pairs) < plan['trustlines']:
            pairs.add(tuple(sorted(rng.sample(range(len(nodes)), 2))))
        pairs = sorted(pairs)
        pref = dict(credit_limit=10000, comfort_min=-10000, comfort_max=10000,
                    auto_adjust=True)
        edges = [dict(a=nodes[a], b=nodes[b], balance=rng.randint(-3, 3),
                      own=dict(pref), peer=dict(pref)) for a, b in pairs]
        stream = random.Random(seed + 1_000_003)
        offers = []
        at = 0
        for i in range(plan['arrivals']['count']):
            at += stream.expovariate(plan['arrivals']['rate'])
            a, b = stream.choice(pairs)
            offers.append(dict(time=at, a=nodes[a], b=nodes[b],
                               amount=stream.choice(plan['arrivals']['signed_amounts']),
                               offer_id=f'offer-{i:04d}'))
        assert sum(abs(e['balance']) for e in edges) + sum(abs(o['amount']) for o in offers) < 10000
        case = dict(name=f'private32-seed{seed}', seed=seed, nodes=nodes,
                    edges=edges, offers=offers)
        case['sha256'] = hashlib.sha256(json.dumps(
            case, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        cases.append(case)
    return dict(plan_sha256=sha(HERE / 'private-stream-plan.json'), cases=cases)


if __name__ == '__main__':
    destination = HERE / 'private-stream-workloads.json'
    if destination.exists():
        raise SystemExit('Existing workloads are never overwritten')
    destination.write_text(json.dumps(build(), indent=2) + '\n')
    print(destination)
