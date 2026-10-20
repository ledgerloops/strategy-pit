"""Prospective heavier-arrival fixtures, separate from all prior evidence."""
import hashlib
import json
from pathlib import Path
import random

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    plan = json.loads((HERE / 'exact-headroom-plan.json').read_text())
    cases = []
    for seed in plan['seeds']:
        rng = random.Random(seed)
        n = plan['nodes']
        pairs = {tuple(sorted((i, (i + 1) % n))) for i in range(n)}
        while len(pairs) < plan['trustlines']:
            pairs.add(tuple(sorted(rng.sample(range(n), 2))))
        pairs = sorted(pairs)
        balances = [(a, b, rng.randint(-6, 6)) for a, b in pairs]
        stream = random.Random(seed + 1_000_003)
        at = 0
        arrivals = []
        for _ in range(plan['arrivals']['count']):
            at += stream.expovariate(plan['arrivals']['rate'])
            a, b = stream.choice(pairs)
            arrivals.append(dict(time=at, a=a, b=b,
                                 amount=stream.choice(plan['arrivals']['signed_amounts'])))
        assert sum(abs(v) for _, _, v in balances) + sum(abs(e['amount']) for e in arrivals) < 10000
        for profile in plan['profiles']:
            pref_rng = random.Random(seed + 2_000_003)

            def preference():
                width = 10000 if profile == 'broad' else pref_rng.choice([1, 3, 6])
                return dict(credit_limit=10000, comfort_min=-width,
                            comfort_max=width, auto_adjust=True)

            case = dict(name=f'medium32-{profile}-seed{seed}', family='medium32',
                        profile=profile, seed=seed, nodes=list(range(n)),
                        edges=[dict(a=a, b=b, balance=v, own=preference(), peer=preference())
                               for a, b, v in balances], arrivals=arrivals)
            case['sha256'] = hashlib.sha256(json.dumps(
                case, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            cases.append(case)
    return dict(plan_sha256=sha(HERE / 'exact-headroom-plan.json'), cases=cases)


if __name__ == '__main__':
    output = HERE / 'exact-headroom-workloads.json'
    if output.exists():
        raise SystemExit('Refusing to overwrite saved fixtures')
    output.write_text(json.dumps(build(), indent=2) + '\n')
    print(output)
