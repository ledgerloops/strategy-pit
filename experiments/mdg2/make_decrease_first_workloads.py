"""Prospectively frozen descriptive and fresh held-out follow-up workloads."""
import hashlib
import json
from pathlib import Path
import random

HERE=Path(__file__).resolve().parent
PLAN=HERE/'decrease-first-plan.json'
BASE_PLAN=HERE/'comfort-curve-plan.json'
ORIGINAL=HERE/'comfort-curve-workloads.json'
OUTPUT=HERE/'decrease-first-workloads.json'


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cases_for(plan,seeds,families):
    # Exact frozen original generator construction, unchanged RNGs and order.
    cases=[]
    for family in families:
        for seed in seeds:
            rng=random.Random(seed);n=family['nodes']
            pairs={tuple(sorted((a,(a+1)%n))) for a in range(n)}
            while len(pairs)<family['trustlines']:
                pairs.add(tuple(sorted(rng.sample(range(n),2))))
            balances=[(a,b,rng.randint(-6,6)) for a,b in sorted(pairs)]
            stream_rng=random.Random(seed+1_000_003);time=0;arrivals=[]
            while True:
                time+=stream_rng.expovariate(plan['arrivals']['rate'])
                if time>plan['arrivals']['end_time']:break
                a,b=stream_rng.choice(sorted(pairs))
                arrivals.append(dict(time=time,a=a,b=b,amount=stream_rng.choice(plan['arrivals']['signed_amounts'])))
            assert sum(abs(v) for _,_,v in balances)+sum(abs(e['amount']) for e in arrivals)<plan['hard_credit_grant_each_endpoint']
            for profile in plan['profiles']:
                pref_rng=random.Random(seed+2_000_003)
                def preference():
                    width=10000 if profile=='broad' else pref_rng.choice([1,3,6])
                    return dict(credit_limit=10000,comfort_min=-width,comfort_max=width,auto_adjust=True)
                edges=[dict(a=a,b=b,balance=v,own=preference(),peer=preference()) for a,b,v in balances]
                case=dict(name=f'{family["name"]}-{profile}-seed{seed}',family=family['name'],profile=profile,
                          seed=seed,nodes=list(range(n)),edges=edges,arrivals=arrivals)
                case['sha256']=hashlib.sha256(json.dumps(case,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                cases.append(case)
    return cases


def build():
    follow=json.loads(PLAN.read_text());base=json.loads(BASE_PLAN.read_text());original=json.loads(ORIGINAL.read_text())
    assert original['plan_sha256']==fingerprint(BASE_PLAN)
    assert cases_for(base,base['seeds'],base['families'])==original['cases'], 'Generator differs from original fixture construction'
    heldout=cases_for(base,follow['heldout']['seeds'],[follow['heldout']['family']])
    assert len(original['cases'])==12 and len(heldout)==6
    assert {c['seed'] for c in original['cases']}.isdisjoint(c['seed'] for c in heldout)
    return dict(plan_sha256=fingerprint(PLAN),base_plan_sha256=fingerprint(BASE_PLAN),
                original_workloads_sha256=fingerprint(ORIGINAL),extension_cases=original['cases'],heldout_cases=heldout)


if __name__=='__main__':
    if OUTPUT.exists():raise SystemExit('Refusing to overwrite frozen follow-up workloads')
    OUTPUT.write_text(json.dumps(build(),indent=2)+'\n')
    print(OUTPUT)
