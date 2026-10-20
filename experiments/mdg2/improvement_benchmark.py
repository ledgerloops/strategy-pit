#!/usr/bin/env python3
"""Prospectively fixed closure experiment; frozen baseline actor/transport unchanged.

run_case retains the original benchmark timing and replay/communication audit,
with method construction extended to the two preregistered alternatives.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import networkx as nx
from ledgerloops_benchmark import (JsonNumbat, graph_from_case, replay, positions,
    describe, PARAMETERS, HORIZON, fingerprint, source_hashes as baseline_hashes)
from improved_numbat import ImprovedNumbat
from cycles_benchmark import solve_case, CYCLES_COMMIT, SOLVER_HASH

ROOT = Path(__file__).resolve().parent
UPSTREAM = Path('/workspace/cycles-overview')

def source_hashes():
    return {**baseline_hashes(), **{str(p.relative_to(ROOT)): fingerprint(p) for p in
        [Path(__file__), ROOT/'improved_numbat.py', ROOT/'cycles_benchmark.py',
         ROOT/'make_improvement_workloads.py']},
         'upstream_solver': fingerprint(UPSTREAM/'utils/graph_max_flow_solvers.py')}

def run_case(case, method, repeat=0):
    serialize = True
    graph = graph_from_case(case)
    cls = ImprovedNumbat if method == 'objective_closure' else JsonNumbat
    extra = {'close_first': True} if method == 'close_first' else {}
    started = time.perf_counter()
    simulation = cls(graph, seed=case['seed'], **PARAMETERS, **extra)
    setup_done = time.perf_counter()
    simulation.run(HORIZON, max_events=5_000_000)
    simulation.drain(max_events=5_000_000)
    algorithm_done = time.perf_counter()
    # Auditing is deliberately outside the protocol timing and actor decisions.
    expected = replay(graph, simulation.cycles)
    if expected != simulation.graph_snapshot() or positions(expected) != positions(graph):
        raise AssertionError('Independent ledger or net-position audit failed')
    if simulation.events or simulation.pending_reservations or any(n.active for n in simulation.nodes.values()):
        raise AssertionError('Protocol failed to drain')
    measured = describe(graph, simulation.cycles)
    result = dict(case=case['name'], seed=case['seed'], repeat=repeat, method=method,
        complete=True, family=case['family'], split=case['split'], nodes=len(case['nodes']), input_edges=len(graph),
        initial_debt=sum(graph.values()), remaining_debt=sum(expected.values()),
        amount_cleared=measured['cleared_scaled'], cleared_percent=measured['cleared_percent'],
        cycles_count=len(simulation.cycles), cycle_hops=measured['cycle_hops'],
        residual_is_acyclic=measured['residual_is_acyclic'],
        source_sha256=source_hashes(), parameters=dict(PARAMETERS, horizon=HORIZON),
        runtime_seconds=algorithm_done-started, setup_seconds=setup_done-started,
        protocol_seconds=algorithm_done-setup_done, protocol_metrics=dict(simulation.metrics),
        cutoff_tick=simulation.cutoff_tick, drain_tick=simulation.time,
        message_overshoot=max(0, simulation.metrics['messages']-PARAMETERS['message_cutoff']),
        independent_replay_ok=True, conservation_ok=True, pending_reservations=0, pending_events=0,
        remaining_edges=[dict(source=a, target=b, amount=value) for (a,b),value in sorted(expected.items())],
        cycles=[dict(nodes=nodes, amount=amount) for nodes,amount in simulation.cycles])
    if serialize:
        if not (simulation.metrics['messages'] == simulation.communication['data_attempts'] ==
                simulation.communication['application_deliveries']):
            raise AssertionError('Created, encoded or delivered logical messages disagree')
        result['communication'] = dict(simulation.communication,
            logical_messages_by_kind={key.removeprefix('messages_'): value for key,value in simulation.metrics.items()
                                      if key.startswith('messages_')},
            serialized_json_bytes_by_kind=dict(simulation.bytes_by_kind),
            application_deliveries_by_kind=dict(simulation.deliveries_by_kind),
            ack_attempts=0, retransmissions=0,
            accounting='Exact compact JSON bytes actually encoded, queued and decoded by this simulator; '
                       'includes logical source/destination/kind/schema envelope and all token/transaction fields. '
                       'Excludes TCP/IP/TLS/HTTP headers and external distribution or replication of input. '
                       'Reliable exactly-once transport has no ACK messages or retransmission implementation.')
    deterministic = {key: result[key] for key in ('amount_cleared', 'remaining_edges', 'cycles',
        'protocol_metrics', 'cutoff_tick', 'drain_tick')}
    if serialize:
        deterministic['communication'] = result['communication']
    result['determinism_sha256'] = hashlib.sha256(json.dumps(deterministic, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()
    result['audit_seconds'] = time.perf_counter()-algorithm_done
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists')
    plan_file, input_file = ROOT/'improvement-plan.json', ROOT/'improvement-workloads.json'
    plan, workload = json.loads(plan_file.read_text()), json.loads(input_file.read_text())
    if workload['plan_sha256'] != fingerprint(plan_file):
        raise AssertionError('Workloads were generated against another plan')
    if fingerprint(ROOT/'improved_numbat.py') != plan['candidate_sha256']:
        raise AssertionError('Candidate differs from preregistered version')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != CYCLES_COMMIT or fingerprint(UPSTREAM/'utils/graph_max_flow_solvers.py') != SOLVER_HASH:
        raise AssertionError('Upstream source mismatch')
    if nx.__version__ != '3.5':
        raise AssertionError('NetworkX version mismatch')
    spec = importlib.util.spec_from_file_location('cycles_pinned', UPSTREAM/'utils/graph_max_flow_solvers.py')
    upstream = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(upstream)
    report = dict(schema_version=1, complete=False, plan=plan, plan_sha256=fingerprint(plan_file),
                  input_sha256=fingerprint(input_file), source_sha256=source_hashes(),
                  python=platform.python_version(), networkx=nx.__version__, platform=platform.platform(),
                  upstream_commit=revision, expected_runs=len(workload['cases'])*len(plan['methods'])*plan['timing_repeats'],
                  runs=[], oracle_cases=[])
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        temporary = args.output.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, indent=2)+'\n')
        temporary.replace(args.output)

    def check_frozen():
        if (source_hashes() != report['source_sha256'] or fingerprint(input_file) != report['input_sha256']
                or fingerprint(plan_file) != report['plan_sha256']):
            raise AssertionError('Source, input or plan changed during campaign')

    save()
    for split in ('development', 'heldout'):
        cases = [c for c in workload['cases'] if c['split'] == split]
        for repeat in range(plan['timing_repeats']):
            for index, case in enumerate(cases):
                methods = plan['methods']
                offset = (index+repeat) % len(methods)
                for method in methods[offset:]+methods[:offset]:
                    check_frozen()
                    result = run_case(case, method, repeat)
                    earlier = next((r for r in report['runs'] if r['case'] == result['case']
                                    and r['method'] == method), None)
                    if earlier and earlier['determinism_sha256'] != result['determinism_sha256']:
                        raise AssertionError('Timing repeat changed outcome')
                    report['runs'].append(result)
                    save()
                    print(f'{len(report["runs"])}/{report["expected_runs"]} {split} {case["name"]} '
                          f'{method} repeat{repeat}: cleared={result["amount_cleared"]} '
                          f'{result["runtime_seconds"]:.3f}s messages={result["communication"]["data_attempts"]}',
                          flush=True)
        # Offline reference is never provided to any actor or used to change policy.
        for case in cases:
            check_frozen()
            optimum = solve_case(case, upstream.max_flow_solver, plan['timing_repeats'])
            optimum['split'] = split
            report['oracle_cases'].append(optimum)
            if any(r['amount_cleared'] > optimum['cleared_amount'] for r in report['runs']
                   if r['case'] == case['name']):
                raise AssertionError('Local result exceeds certified optimum')
            save()
    check_frozen()
    report['complete'] = True
    save()
    print('COMPLETE', flush=True)


if __name__ == '__main__':
    main()

