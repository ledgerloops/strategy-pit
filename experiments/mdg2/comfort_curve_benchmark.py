"""Fixed-budget static and random-arrival curves for comfort headroom."""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import networkx as nx

from comfort_headroom import Network

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLAN = HERE/'comfort-curve-plan.json'
WORKLOAD = HERE/'comfort-curve-workloads.json'


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources():
    paths = [Path(__file__),HERE/'comfort_headroom.py',HERE/'make_comfort_curve_workloads.py',
             ROOT/'app/comfort.py']
    return {str(p.relative_to(ROOT)):fingerprint(p) for p in paths}


def net_positions(ledger):
    result = Counter()
    for (a,b),value in ledger.items():
        result[a] += value
        result[b] -= value
    return dict(result)


def reference(case, mode):
    ledger = {(e['a'],e['b']):e['balance'] for e in case['edges']}
    for event in case['arrivals'] if mode == 'arrivals' else []:
        ledger[event['a'],event['b']] += event['amount']
    return ledger


def oracle(case, mode):
    """Global offline scoring reference; no actor can read this object."""
    ledger = reference(case, mode)
    nets = net_positions(ledger)
    graph = nx.DiGraph()
    graph.add_nodes_from((n,dict(demand=nets.get(n,0))) for n in case['nodes'])
    for edge in case['edges']:
        a,b = edge['a'],edge['b']
        assert -edge['peer']['credit_limit'] <= ledger[a,b] <= edge['own']['credit_limit']
        # A positive canonical balance means b owes a.
        graph.add_edge(b,a,capacity=edge['own']['credit_limit'],weight=1)
        graph.add_edge(a,b,capacity=edge['peer']['credit_limit'],weight=1)
    cost, flow = nx.network_simplex(graph)
    solution = {(e['a'],e['b']):flow[e['b']][e['a']]-flow[e['a']][e['b']] for e in case['edges']}
    assert net_positions(solution) == nets
    assert sum(abs(v) for v in solution.values()) == cost
    assert all(not (flow[a][b] and flow[b][a]) for a,b in ledger)
    gross = sum(abs(v) for v in ledger.values())
    return dict(case=case['name'],mode=mode,reference_gross=gross,minimum_gross=cost,potential=gross-cost,
                reference=[dict(source=a,target=b,balance=v) for (a,b),v in ledger.items()],
                optimum=[dict(source=a,target=b,balance=v) for (a,b),v in solution.items()],
                directed_flows=[dict(source=a,target=b,amount=v) for a,peers in flow.items()
                                for b,v in peers.items() if v])


def run_case(case, mode, policy, per_line, benchmark_plan):
    edges = [(e['a'],e['b'],e['balance'],e['own'],e['peer']) for e in case['edges']]
    total_budget = per_line*len(edges)
    audit_events = []
    service = []
    started = time.perf_counter()
    network = Network(edges,seed=case['seed'])
    seen_receipts = 0

    def serve(at, allowance):
        nonlocal seen_receipts
        before = network.messages
        # Repeated random searches use the same admitted budget, including
        # searches that find no improving cycle. Zero-message calls terminate.
        while network.messages < allowance:
            old = network.messages
            network.clear(policy,budget=allowance-old,max_hops=len(case['nodes']))
            if network.messages == old:
                break
        for receipt in network.receipts[seen_receipts:]:
            audit_events.append(dict(kind='settlement',time=at,receipt=receipt))
        seen_receipts = len(network.receipts)
        service.append(dict(time=at,earned_allowance=allowance,messages=network.messages,
                            used=network.messages-before,score=network.score()))

    accepted = blocked = accepted_value = blocked_value = 0
    if mode == 'arrivals':
        end = benchmark_plan['arrivals']['end_time']
        for event in case['arrivals']:
            serve(event['time'],int(total_budget*event['time']/end))
            admitted = network.transfer(event['a'],event['b'],event['amount'])
            audit_events.append(dict(kind='transfer',**event,accepted=admitted))
            if admitted:
                accepted += 1
                accepted_value += abs(event['amount'])
            else:
                blocked += 1
                blocked_value += abs(event['amount'])
        serve(end,total_budget)
    else:
        serve(0,total_budget)
    finished = time.perf_counter()
    final = network.score()
    snapshot = network.snapshot()
    expected = reference(case,mode)
    actual = {(e['source'],e['target']):e['balance'] for e in snapshot}
    assert net_positions(actual) == net_positions(expected)
    offered = len(case['arrivals']) if mode == 'arrivals' else 0
    assert accepted == offered and blocked == blocked_value == 0
    assert final['messages'] <= total_budget and final['messages'] == final['delivered_messages']
    assert not network.queue and not any(a.reservations for a in network.actors.values())
    assert final['message_bytes'] == sum(final['bytes_by_kind'].values())
    assert final['messages'] == sum(final['messages_by_kind'].values())
    return dict(case=case['name'],family=case['family'],profile=case['profile'],seed=case['seed'],
                mode=mode,policy=policy,nodes=len(case['nodes']),trustlines=len(edges),
                budget_per_trustline=per_line,message_budget=total_budget,
                actual_messages_per_trustline=final['messages']/len(edges),
                unused_budget=total_budget-final['messages'],final=final,snapshot=snapshot,
                offered=offered,accepted=accepted,blocked=blocked,accepted_value=accepted_value,
                blocked_value=blocked_value,runtime_seconds=finished-started,
                service=service,audit_events=audit_events,pending_messages=0,pending_reservations=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a new result path; existing evidence is never overwritten')
    plan = json.loads(PLAN.read_text())
    workloads = json.loads(WORKLOAD.read_text())
    if workloads['plan_sha256'] != fingerprint(PLAN) or nx.__version__ != '3.5':
        raise AssertionError('Plan or NetworkX version mismatch')
    freeze = json.loads((HERE/'comfort-curve-freeze.json').read_text())
    if freeze != dict(sources=sources(),plan_sha256=fingerprint(PLAN),workload_sha256=fingerprint(WORKLOAD)):
        raise AssertionError('Source, plan or workload differs from prospective freeze')
    report = dict(complete=False,expected_runs=plan['expected_runs'],plan=plan,freeze=freeze,
                  python=platform.python_version(),networkx=nx.__version__,platform=platform.platform(),
                  oracles=[],runs=[])
    args.output.parent.mkdir(parents=True,exist_ok=True)

    def save():
        tmp = args.output.with_suffix('.tmp')
        tmp.write_text(json.dumps(report,separators=(',',':'))+'\n')
        tmp.replace(args.output)

    def check():
        assert freeze == dict(sources=sources(),plan_sha256=fingerprint(PLAN),workload_sha256=fingerprint(WORKLOAD))

    save()
    lookup = {}
    for case in workloads['cases']:
        for mode in plan['modes']:
            check()
            result = oracle(case,mode)
            lookup[case['name'],mode] = result
            report['oracles'].append(result)
    save()
    for budget in plan['message_budgets_per_original_trustline']:
        for case_index,case in enumerate(workloads['cases']):
            for mode_index,mode in enumerate(plan['modes']):
                order = plan['policies'] if (case_index+mode_index)%2 == 0 else list(reversed(plan['policies']))
                for policy in order:
                    check()
                    result = run_case(case,mode,policy,budget,plan)
                    ref = lookup[case['name'],mode]
                    savings = ref['reference_gross']-result['final']['gross_debt']
                    assert result['final']['gross_debt'] >= ref['minimum_gross']
                    result.update(reference_gross=ref['reference_gross'],oracle_minimum_gross=ref['minimum_gross'],
                                  clearing_potential=ref['potential'],snapshot_savings=savings,
                                  clearing_potential_achieved_percent=100*savings/ref['potential'] if ref['potential'] else None)
                    report['runs'].append(result)
                    save()
                    print(f'{len(report["runs"])}/{report["expected_runs"]} {case["name"]} {mode} {policy} '
                          f'budget/line={budget} actual/line={result["actual_messages_per_trustline"]:.2f} '
                          f'potential={result["clearing_potential_achieved_percent"]} '
                          f'helpers={result["final"]["assisted_moves"]}',flush=True)
    check()
    assert len(report['runs']) == report['expected_runs']
    report['complete'] = True
    save()
    print('COMPLETE',flush=True)


if __name__ == '__main__':
    main()
