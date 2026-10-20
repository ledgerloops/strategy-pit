"""Generate the prospectively specified follow-up graphs, without running actors."""
import hashlib
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parent


def build():
    plan = json.loads((ROOT / 'improvement-plan.json').read_text())
    cases = []
    for split, key in [('development', 'development_seeds'), ('heldout', 'heldout_seeds')]:
        for family in plan['families']:
            for seed in plan[key]:
                rng = random.Random(seed)
                nodes = [f'n{i:04d}' for i in range(family['nodes'])]
                edges = {(nodes[i], nodes[(i+1) % len(nodes)]) for i in range(len(nodes))}
                while len(edges) < family['edges']:
                    a, b = rng.sample(nodes, 2)
                    if (b, a) not in edges:
                        edges.add((a, b))
                amounts = [dict(source=a, target=b, amount=rng.randint(1, 100))
                           for a, b in sorted(edges)]
                case = dict(name=f'{family["name"]}-seed{seed}', family=family['name'],
                            seed=seed, split=split, nodes=nodes, edges=amounts)
                case['sha256'] = hashlib.sha256(json.dumps(
                    case, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                cases.append(case)
    return dict(schema_version=1, plan_sha256=hashlib.sha256(
        (ROOT / 'improvement-plan.json').read_bytes()).hexdigest(), cases=cases)


if __name__ == '__main__':
    out = ROOT / 'improvement-workloads.json'
    if out.exists():
        raise SystemExit('Refusing to replace frozen workloads')
    out.write_text(json.dumps(build(), indent=2) + '\n')
    print(out)
