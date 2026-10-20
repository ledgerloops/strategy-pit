#!/usr/bin/env python3
"""Offline independent ledger/optimality audit; never imports benchmark helpers.

Run only after the campaign has completed:
  python3 artifacts/mdg2-improvement-2026-10-20/audit-independent.py
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics

DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def edges(items):
    result = {}
    for item in items:
        pair = (item['source'], item['target'])
        assert pair[0] != pair[1] and pair not in result
        assert type(item['amount']) is int and item['amount'] > 0
        result[pair] = item['amount']
    return result


def net_positions(graph):
    net = defaultdict(int)
    for (source, target), amount in graph.items():
        net[source] += amount
        net[target] -= amount
    return {node: amount for node, amount in net.items() if amount}


def replay_cycles(capacity, cycles):
    remaining = dict(capacity)
    for cycle in cycles:
        nodes, amount = cycle['nodes'], cycle['amount']
        assert len(nodes) >= 3 and len(set(nodes)) == len(nodes)
        assert type(amount) is int and amount > 0
        for source, target in zip(nodes, nodes[1:] + nodes[:1]):
            pair = (source, target)
            assert remaining.get(pair, 0) >= amount
            remaining[pair] -= amount
    return {pair: amount for pair, amount in remaining.items() if amount}


def certificate(nodes, capacity, remaining):
    """Own Bellman–Ford implementation yields feasible min-cost dual potentials.

    Retaining another unit on an original arc costs +1; undoing one retained
    unit costs -1. Conserved feasible flow is globally minimal if every residual
    arc has nonnegative reduced cost for some vertex potentials.
    """
    residual = []
    for (source, target), maximum in capacity.items():
        flow = remaining.get((source, target), 0)
        assert 0 <= flow <= maximum
        if flow < maximum:
            residual.append((source, target, 1))
        if flow:
            residual.append((target, source, -1))
    distance = {node: 0 for node in nodes}
    for iteration in range(len(nodes)):
        changed = False
        for source, target, cost in residual:
            proposed = distance[source] + cost
            if distance[target] > proposed:
                distance[target] = proposed
                changed = True
        if not changed:
            break
    else:
        raise AssertionError('A negative-cost residual cycle disproves optimality')
    minimum = min((cost + distance[source] - distance[target]
                   for source, target, cost in residual), default=0)
    assert minimum >= 0
    return dict(potentials=distance, residual_arcs=len(residual),
                minimum_reduced_cost=minimum, relaxation_rounds=iteration + 1)


def main():
    result_file = DIRECTORY / 'results.json'
    report = json.loads(result_file.read_text())
    assert report['complete'] is True, 'Campaign still running; do not audit concurrently'
    plan_file = ROOT / 'experiments/mdg2/improvement-plan.json'
    input_file = ROOT / 'experiments/mdg2/improvement-workloads.json'
    plan = json.loads(plan_file.read_text())
    inputs = json.loads(input_file.read_text())
    assert report['plan'] == plan
    assert digest(plan_file) == report['plan_sha256'] == inputs['plan_sha256']
    assert digest(input_file) == report['input_sha256']
    for name, expected in report['source_sha256'].items():
        if name == 'upstream_solver':
            source = Path('/workspace/cycles-overview/utils/graph_max_flow_solvers.py')
        else:
            source = ROOT / 'experiments' / name
            if not source.is_file():
                source = ROOT / 'experiments/mdg2' / name
        assert digest(source) == expected, f'Source guard failed: {name}'
    assert digest(ROOT / 'experiments/mdg2/improved_numbat.py') == plan['candidate_sha256']
    cases = {case['name']: case for case in inputs['cases']}
    assert len(cases) == len(inputs['cases']) == 24
    for case in cases.values():
        unsigned = {key: value for key, value in case.items() if key != 'sha256'}
        actual = hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        assert actual == case['sha256']
        expected_seeds = plan['development_seeds'] if case['split'] == 'development' else plan['heldout_seeds']
        assert case['seed'] in expected_seeds
    methods = plan['methods']
    grouped = defaultdict(list)
    assert len(report['runs']) == report['expected_runs'] == len(cases)*len(methods)*plan['timing_repeats']
    for run in report['runs']:
        assert run['case'] in cases and run['method'] in methods
        assert run['source_sha256'] == report['source_sha256']
        case = cases[run['case']]
        assert (run['family'], run['split'], run['seed']) == (case['family'], case['split'], case['seed'])
        assert run['complete'] and run['pending_reservations'] == run['pending_events'] == 0
        assert run['protocol_metrics'].get('live_reservations', 0) == 0
        for key, value in run['parameters'].items():
            assert plan['parameters'][key] == value
        communication = run['communication']
        assert run['protocol_metrics']['messages'] == communication['data_attempts'] == communication['application_deliveries'] == communication['logical_messages_created']
        assert sum(communication['logical_messages_by_kind'].values()) == communication['data_attempts']
        assert sum(communication['serialized_json_bytes_by_kind'].values()) == communication['serialized_json_bytes']
        grouped[run['case'], run['method']].append(run)
    unique = {}
    for key, runs in grouped.items():
        assert len(runs) == plan['timing_repeats']
        assert sorted(run['repeat'] for run in runs) == list(range(plan['timing_repeats']))
        first = runs[0]
        for run in runs[1:]:
            for field in ('cycles', 'remaining_edges', 'amount_cleared', 'protocol_metrics', 'communication', 'cutoff_tick', 'drain_tick'):
                assert run[field] == first[field], (key, field)
        capacity = edges(cases[key[0]]['edges'])
        remaining = replay_cycles(capacity, first['cycles'])
        assert remaining == edges(first['remaining_edges'])
        assert net_positions(remaining) == net_positions(capacity)
        assert all(amount <= capacity[pair] for pair, amount in remaining.items())
        initial, final = sum(capacity.values()), sum(remaining.values())
        assert initial == first['initial_debt'] and final == first['remaining_debt']
        assert initial - final == first['amount_cleared']
        assert first['cycles_count'] == len(first['cycles'])
        unique[key] = dict(run=first, median_runtime=statistics.median(run['runtime_seconds'] for run in runs))
    assert len(unique) == len(cases)*len(methods)
    optima, certificates = {}, {}
    assert len(report['oracle_cases']) == len(cases)
    for oracle in report['oracle_cases']:
        name = oracle['name']
        assert name not in optima and name in cases
        case = cases[name]
        assert oracle['case_sha256'] == case['sha256']
        capacity = edges(case['edges'])
        assert len(oracle['runs']) == plan['timing_repeats']
        known_solutions = {}
        for run in oracle['runs']:
            remaining, removed = edges(run['remaining_edges']), edges(run['cleared_edges'])
            assert set(remaining) <= set(capacity) and set(removed) <= set(capacity)
            assert all(remaining.get(pair, 0) + removed.get(pair, 0) == amount for pair, amount in capacity.items())
            assert net_positions(removed) == {}
            assert net_positions(remaining) == net_positions(capacity)
            assert sum(removed.values()) == run['cleared_amount'] == oracle['cleared_amount']
            assert sum(remaining.values()) == run['remaining_amount'] == oracle['remaining_amount']
            solution = tuple(sorted(remaining.items()))
            if solution not in known_solutions:
                known_solutions[solution] = certificate(case['nodes'], capacity, remaining)
        certificates[name] = list(known_solutions.values())
        optima[name] = oracle['cleared_amount']
        assert all(unique[name, method]['run']['amount_cleared'] <= optima[name] for method in methods)

    def summarize(names, method):
        records = [unique[name, method] for name in names]
        initial = sum(record['run']['initial_debt'] for record in records)
        cleared = sum(record['run']['amount_cleared'] for record in records)
        optimum = sum(optima[name] for name in names)
        return dict(graphs=len(names), initial_debt=initial, cleared=cleared, optimum_cancellable=optimum,
                    percent_initial=100*cleared/initial, percent_optimum=100*cleared/optimum,
                    messages=sum(record['run']['communication']['data_attempts'] for record in records),
                    json_bytes=sum(record['run']['communication']['serialized_json_bytes'] for record in records),
                    sum_median_runtime_seconds=sum(record['median_runtime'] for record in records),
                    proposals=sum(record['run']['protocol_metrics'].get('proposals', 0) for record in records),
                    aborted=sum(record['run']['protocol_metrics'].get('aborted', 0) for record in records))

    statistics_by_split = {}
    for split in ('development', 'heldout'):
        names = [name for name, case in cases.items() if case['split'] == split]
        statistics_by_split[split] = {'pooled': {method: summarize(names, method) for method in methods}}
        for family in plan['families']:
            members = [name for name in names if cases[name]['family'] == family['name']]
            statistics_by_split[split][family['name']] = {method: summarize(members, method) for method in methods}
    heldout = statistics_by_split['heldout']
    baseline = heldout['pooled']['numbat']
    gates = {}
    for method in methods:
        if method == 'numbat':
            continue
        candidate = heldout['pooled'][method]
        ratios = {field: candidate[field]/baseline[field] if baseline[field] else None for field in
                  ('cleared', 'messages', 'json_bytes', 'sum_median_runtime_seconds')}
        family_ratios = {family['name']: (heldout[family['name']][method]['cleared']/heldout[family['name']]['numbat']['cleared']
                         if heldout[family['name']]['numbat']['cleared'] else None)
                         for family in plan['families']}
        checks = dict(clearing=candidate['cleared'] >= 1.05*baseline['cleared'],
                      messages=candidate['messages'] <= 1.25*baseline['messages'],
                      json_bytes=candidate['json_bytes'] <= 1.25*baseline['json_bytes'],
                      runtime=candidate['sum_median_runtime_seconds'] <= 1.25*baseline['sum_median_runtime_seconds'],
                      families=all(heldout[family['name']][method]['cleared'] >= .95*heldout[family['name']]['numbat']['cleared']
                                   for family in plan['families']), ledger_audits=True)
        gates[method] = dict(passes_all=all(checks.values()), checks=checks, ratios=ratios, family_clearing_ratios=family_ratios)
    result = dict(independent_audit_passed=True, campaign_sha256=digest(result_file), plan_sha256=digest(plan_file),
                  workload_sha256=digest(input_file), auditor_sha256=digest(Path(__file__)),
                  timing_runs_checked=len(report['runs']), unique_local_ledgers_replayed=len(unique),
                  unique_graphs=len(cases), oracle_optima_certified=len(optima),
                  certificate='Independent Bellman–Ford vertex potentials with nonnegative reduced residual costs; no solver or benchmark audit helpers imported.',
                  statistics=statistics_by_split, promotion_gates=gates, oracle_dual_certificates=certificates)
    output = DIRECTORY / 'independent-audit.json'
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({key: result[key] for key in ('independent_audit_passed', 'timing_runs_checked',
          'unique_local_ledgers_replayed', 'oracle_optima_certified', 'promotion_gates')}, indent=2))


if __name__ == '__main__':
    main()
