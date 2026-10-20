#!/usr/bin/env python3
"""Run the pinned official Cycles notebook core on frozen obligation snapshots.

This is a local algorithm benchmark, not the hosted Cycles product or protocol.
The upstream solver is imported without modification. Audit time is excluded.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

import networkx as nx

CYCLES_COMMIT = '32dc873c45041accb365e73a8ef35bee10a80f1d'
SOLVER_HASH = 'a426bc1425715285c6334f7ea4975711d16bc773a6ede052c87581b483422de2'
WORKLOAD_HASH = 'e029697e8f2fc93c9867d1b85a586f5f7d139bc13876ce70fce440a976c8e345'


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def positions(edges):
    result = Counter()
    for edge in edges:
        result[edge['source']] -= edge['amount']
        result[edge['target']] += edge['amount']
    return {node: value for node, value in result.items() if value}


def validate_case(case):
    nodes = set(case['nodes'])
    capacities = {}
    for edge in case['edges']:
        a, b, amount = edge['source'], edge['target'], edge['amount']
        if (a == b or a not in nodes or b not in nodes or type(amount) is not int
                or amount <= 0 or (a, b) in capacities or (b, a) in capacities):
            raise ValueError('Require positive integer, bilaterally netted distinct-endpoint obligations')
        capacities[a, b] = amount
    if {'source', 'target'} & nodes:
        raise ValueError('Upstream solver reserves source/target node labels')
    return capacities


def audit(case, capacities, cleared):
    """Check feasible clearing and absence of improving min-cost residual cycles.

    Unit-cost retained-flow residual graph has forward cost+1 when original
    capacity remains and backward cost-1 when retained flow may be undone.
    No negative cycle certifies minimum retained debt at fixed net positions.
    """
    cleared_edges = []
    for a, b, data in cleared.edges(data=True):
        amount = data['capacity']
        if type(amount) is not int or not 0 < amount <= capacities.get((a, b), 0):
            raise AssertionError('Upstream returned an invalid set-off')
        cleared_edges.append(dict(source=a, target=b, amount=amount))
    cleared_edges.sort(key=lambda edge: (edge['source'], edge['target']))
    if positions(cleared_edges):
        raise AssertionError('Set-offs do not conserve every participant net position')
    reduction = {(edge['source'], edge['target']): edge['amount'] for edge in cleared_edges}
    remaining = [dict(source=a, target=b, amount=capacity - reduction.get((a, b), 0))
                 for (a, b), capacity in sorted(capacities.items()) if capacity - reduction.get((a, b), 0)]
    if positions(remaining) != positions(case['edges']):
        raise AssertionError('Remaining ledger changes participant net positions')
    residual = nx.DiGraph()
    residual.add_nodes_from(case['nodes'])
    retained = {(edge['source'], edge['target']): edge['amount'] for edge in remaining}
    for (a, b), capacity in capacities.items():
        flow = retained.get((a, b), 0)
        if flow < capacity:
            residual.add_edge(a, b, weight=1)
        if flow > 0:
            residual.add_edge(b, a, weight=-1)
    if nx.negative_edge_cycle(residual, weight='weight'):
        raise AssertionError('Remaining ledger is not minimum-cost: improving cycle exists')
    return remaining, cleared_edges


def solve_case(case, solver, repeats):
    capacities = validate_case(case)
    initial = sum(capacities.values())
    runs = []
    for repeat in range(repeats):
        started = time.perf_counter_ns()
        cpu_started = time.process_time_ns()
        graph = nx.DiGraph()
        graph.add_nodes_from(case['nodes'])
        for edge in case['edges']:
            graph.add_edge(edge['source'], edge['target'], capacity=edge['amount'], weight=1)
        built = time.perf_counter_ns()
        cleared = solver(graph)
        finished = time.perf_counter_ns()
        cpu_finished = time.process_time_ns()
        # Post-run auditing and output serialization do not enter core timings.
        remaining, cleared_edges = audit(case, capacities, cleared)
        removed = sum(edge['amount'] for edge in cleared_edges)
        remaining_amount = sum(edge['amount'] for edge in remaining)
        if initial != removed + remaining_amount:
            raise AssertionError('Debt accounting does not reconcile')
        runs.append(dict(repeat=repeat, elapsed_ns=finished-started,
                         graph_build_ns=built-started, solver_only_ns=finished-built,
                         cpu_ns=cpu_finished-cpu_started, initial_amount=initial,
                         cleared_amount=removed, remaining_amount=remaining_amount,
                         cleared_edges=cleared_edges, remaining_edges=remaining,
                         input_json_payload_bytes=len(compact(case['edges'])),
                         setoffs_json_payload_bytes=len(compact(cleared_edges)),
                         audits=dict(bounded=True, net_positions_preserved=True,
                                     minimum_retained_debt_negative_cycle_certificate=True)))
    if len({run['cleared_amount'] for run in runs}) != 1:
        raise AssertionError('Repeated solver output changed clearing volume')
    return dict(name=case['name'], family=case.get('family'), seed=case.get('seed'),
                case_sha256=case['sha256'], nodes=len(case['nodes']), edges=len(case['edges']),
                initial_amount=initial, cleared_amount=runs[0]['cleared_amount'],
                cleared_percent=100*runs[0]['cleared_amount']/initial if initial else 0,
                remaining_amount=runs[0]['remaining_amount'],
                median_elapsed_ns=statistics.median(run['elapsed_ns'] for run in runs),
                min_elapsed_ns=min(run['elapsed_ns'] for run in runs),
                max_elapsed_ns=max(run['elapsed_ns'] for run in runs),
                communication_overhead=dict(peer_messages=None, wire_bytes=None,
                    scope='No Cycles transport/protocol is implemented in this notebook; input/output payload sizes are separate fields, not network overhead.'),
                runs=runs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cycles-repo', type=Path, default=Path('/workspace/cycles-overview'))
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--preflight', action='store_true', help='Only solve tiny built-in validation graphs; no campaign')
    args = parser.parse_args()
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=args.cycles_repo, text=True).strip()
    source = args.cycles_repo/'utils/graph_max_flow_solvers.py'
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if revision != CYCLES_COMMIT or source_hash != SOLVER_HASH or nx.__version__ != '3.5':
        raise RuntimeError('Pinned upstream source or NetworkX version mismatch')
    spec = importlib.util.spec_from_file_location('cycles_pinned_notebook_solver', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw = args.input.read_bytes()
    input_hash = hashlib.sha256(raw).hexdigest()
    if input_hash != WORKLOAD_HASH:
        raise RuntimeError('Workload manifest differs from prospectively frozen input')
    manifest = json.loads(raw)
    if not 1 <= args.repeats <= 20:
        raise ValueError('Repeat count must be from1 to20')
    if args.preflight:
        examples = [
            dict(name='triangle', nodes=['a','b','c'], edges=[dict(source='a',target='b',amount=7), dict(source='b',target='c',amount=3),dict(source='c',target='a',amount=5)],sha256='preflight'),
            dict(name='acyclic', nodes=['a','b','c'], edges=[dict(source='a',target='b',amount=7), dict(source='b',target='c',amount=3)],sha256='preflight')]
        outcomes = [solve_case(case,module.max_flow_solver,1) for case in examples]
        assert [case['cleared_amount'] for case in outcomes] == [9,0]
        print('PASS Cycles core triangle and acyclic preflight, bounds, conservation and min-cost residual certificates')
        return
    results = [solve_case(case,module.max_flow_solver,args.repeats) for case in manifest['cases']]
    output = dict(label='Cycles official public notebook core (local run)',
        repository='https://github.com/informalsystems/cycles-overview',commit_sha=revision,
        source_file='utils/graph_max_flow_solvers.py',source_sha256=source_hash,
        workload_sha256=input_hash,wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        python=platform.python_version(),networkx=nx.__version__,platform=platform.platform(),
        repeats=args.repeats,timing_scope='Fresh NetworkX DiGraph construction + unmodified max_flow_solver; warmed imports; excludes JSON parse, audit and serialization; no warmup solve.',
        algorithm='Upstream default max_flow_min_cost (NetworkX)',
        scope_limits=['Not hosted Cycles production','No encryption/TEE/ZK proving/chain settlement/finality or protocol transport','Fixed cancellation-only snapshots; no external liquidity/credit acceptance'],
        cases=results)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps([dict(name=case['name'],cleared=case['cleared_amount'],elapsed_ms=case['median_elapsed_ns']/1e6) for case in results]))


if __name__ == '__main__':
    main()
