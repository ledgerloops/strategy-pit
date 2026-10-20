"""Frozen exact-completion experiment; existing finite-budget control retained."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time

import networkx as nx

from comfort_curve_benchmark import oracle
from comfort_decrease_first import DecreaseFirstNetwork
from exact_headroom import ExactNetwork
from exact_headroom_audit import audit_run

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLAN = HERE / 'exact-headroom-plan.json'
INPUT = HERE / 'exact-headroom-workloads.json'
FREEZE = HERE / 'exact-headroom-freeze.json'
OUT = ROOT / 'artifacts/mdg2-exact-headroom-2026-10-20'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest():
    names = ['exact_headroom.py', 'exact_headroom_benchmark.py',
             'exact_headroom_audit.py', 'make_exact_headroom_workloads.py',
             'comfort_headroom.py', 'comfort_decrease_first.py',
             'comfort_curve_benchmark.py', 'comfort_curve_audit.py']
    paths = [HERE / name for name in names] + [ROOT / 'app/comfort.py']
    return dict(sources={str(p.relative_to(ROOT)): sha(p) for p in paths},
                plan_sha256=sha(PLAN), workloads_sha256=sha(INPUT))


def run_case(case, method, mode, plan):
    edges = [(e['a'], e['b'], e['balance'], e['own'], e['peer']) for e in case['edges']]
    runtime = 0
    started = time.perf_counter()
    network = (ExactNetwork if method == 'exact' else DecreaseFirstNetwork)(edges, seed=case['seed'])
    runtime += time.perf_counter() - started
    events = []
    epochs = []
    seen = 0
    offered = case['arrivals'] if mode == 'arrivals' else []
    prefixes = [0] + (list(range(plan['arrivals']['epoch_size'], len(offered) + 1,
                                 plan['arrivals']['epoch_size'])) if offered else [])
    if offered and prefixes[-1] != len(offered):
        prefixes.append(len(offered))
    previous_prefix = 0
    accepted = blocked = 0
    cap = (plan['exact_total_message_safety_ceiling'] if method == 'exact' else
           plan['control_total_messages_per_trustline'] * len(edges))
    for index, prefix in enumerate(prefixes):
        for offer in offered[previous_prefix:prefix]:
            started = time.perf_counter()
            ok = network.transfer(offer['a'], offer['b'], offer['amount'])
            runtime += time.perf_counter() - started
            events.append(dict(kind='transfer', **offer, accepted=ok))
            accepted += int(ok)
            blocked += int(not ok)
        at = offered[prefix - 1]['time'] if prefix else 0
        allowance = cap if method == 'exact' else cap * (index + 1) // len(prefixes)
        before = network.messages
        started = time.perf_counter()
        if method == 'exact':
            cleared = network.clear_exact(policy='comfort_headroom',
                                          message_limit=max(0, allowance - network.messages))
        else:
            while network.messages < allowance:
                old = network.messages
                network.clear('comfort_headroom', budget=allowance - old,
                              max_hops=len(case['nodes']))
                if network.messages == old:
                    break
            cleared = dict(status='finite_budget_control', certified=False,
                           used_messages=network.messages - before)
        runtime += time.perf_counter() - started
        for receipt in network.receipts[seen:]:
            events.append(dict(kind='settlement', time=at, receipt=receipt))
        seen = len(network.receipts)
        # Offline oracle and snapshot recording are excluded from actor timing.
        ref = oracle(dict(case, arrivals=offered[:prefix]), 'arrivals' if prefix else 'static')
        score = network.score()
        savings = ref['reference_gross'] - score['gross_debt']
        epochs.append(dict(index=index, prefix_count=prefix, time=at,
                           event_end_index=len(events), snapshot=network.snapshot(),
                           score=score, clear_result=cleared, earned_allowance=allowance,
                           used_messages=network.messages - before, oracle=ref,
                           snapshot_savings=savings,
                           clearing_potential_achieved_percent=
                           100 * savings / ref['potential'] if ref['potential'] else None))
        previous_prefix = prefix
    assert accepted == len(offered) and blocked == 0
    assert network.messages <= cap and network.messages == network.delivered
    assert not network.queue and not any(a.reservations for a in network.actors.values())
    return dict(case=case['name'], case_sha256=case['sha256'], seed=case['seed'],
                profile=case['profile'], method=method, mode=mode,
                nodes=len(case['nodes']), trustlines=len(edges),
                offered=len(offered), accepted=accepted, blocked=blocked,
                touched_trustlines=len({(e['a'], e['b']) for e in offered}),
                runtime_seconds=runtime, message_safety_ceiling=cap,
                final=network.score(), snapshot=network.snapshot(),
                actual_messages_per_trustline=network.messages / len(edges),
                audit_events=events, epochs=epochs, pending_messages=0,
                pending_reservations=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--output', type=Path, default=OUT / 'results.json')
    args = parser.parse_args()
    plan = json.loads(PLAN.read_text())
    inputs = json.loads(INPUT.read_text())
    assert inputs['plan_sha256'] == sha(PLAN)
    assert nx.__version__ == '3.5'
    if args.freeze:
        if FREEZE.exists():
            raise SystemExit('Existing freeze is never overwritten')
        FREEZE.write_text(json.dumps(manifest(), indent=2) + '\n')
        print(FREEZE)
        return
    if args.output.exists():
        raise SystemExit('Existing evidence is never overwritten')
    frozen = json.loads(FREEZE.read_text())
    assert frozen == manifest()
    data = dict(complete=False, expected_runs=plan['expected_runs'], plan=plan,
                freeze=frozen, python=platform.python_version(), networkx=nx.__version__,
                platform=platform.platform(), runs=[])
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        temp = args.output.with_suffix('.tmp')
        temp.write_text(json.dumps(data, separators=(',', ':')) + '\n')
        temp.replace(args.output)

    save()
    for case in inputs['cases']:
        for mode in plan['exact_modes'][case['profile']]:
            methods = ['exact']
            if mode in plan['control_modes'].get(case['profile'], []):
                methods += ['decrease_first']
            if case['seed'] % 2:
                methods.reverse()
            for method in methods:
                assert frozen == manifest()
                run = run_case(case, method, mode, plan)
                run['independent_audit'] = audit_run(case, run, plan)
                data['runs'].append(run)
                save()
                last = run['epochs'][-1]
                print(f'{len(data["runs"])}/{data["expected_runs"]} {case["name"]} '
                      f'{mode} {method}: potential={last["clearing_potential_achieved_percent"]} '
                      f'messages={run["final"]["messages"]} '
                      f'status={last["clear_result"]["status"]}', flush=True)
    assert len(data['runs']) == data['expected_runs']
    assert frozen == manifest()
    data['complete'] = True
    save()
    print('COMPLETE', flush=True)


if __name__ == '__main__':
    main()
