"""Offline optimistic final-debt bound for temporal cancellation-only clearing.

Unlike final-batch MCF, this retains BOTH directions of gross arrival totals.
Chronology, mandatory early bilateral netting, and protocol budgets are ignored.
No node-local protocol uses this graph-wide reference to make decisions.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import time

from temporal_sarafu import load_sarafu, net_graph


def gross_graph(events):
    graph = Counter()
    for event in events:
        if event.source != event.target and event.amount:
            graph[event.source, event.target] += event.amount
    return dict(graph)


def positions(graph):
    balances = Counter()
    for (source, target), amount in graph.items():
        balances[source] += amount
        balances[target] -= amount
    return {node: amount for node, amount in balances.items() if amount}


def min_residual(graph):
    """Minimize retained directed debt with gross capacities and fixed positions.

    The complement of the returned residual is a nonnegative circulation; its
    cycle decomposition is allowed to include bilateral two-cycles. That relaxed
    cancellation schedule need not respect the input transfer chronology.
    """
    from ortools.graph.python import min_cost_flow

    if any(a == b or type(amount) is not int or amount <= 0
           for (a, b), amount in graph.items()):
        raise ValueError('Positive integer amounts on distinct endpoints required')
    nodes = sorted({node for edge in graph for node in edge})
    if not nodes:
        return {'status': 'OPTIMAL', 'minimum_final_debt_scaled': 0,
                'removed_scaled': 0, 'input_edges': 0, 'residual_edges': 0,
                'primal_verified': True, 'residual': []}
    indexes = {node: i for i, node in enumerate(nodes)}
    edges = sorted(graph)
    solver = min_cost_flow.SimpleMinCostFlow()
    for source, target in edges:
        solver.add_arc_with_capacity_and_unit_cost(
            indexes[source], indexes[target], graph[source, target], 1)
    before = positions(graph)
    for node in nodes:
        solver.set_node_supply(indexes[node], before.get(node, 0))
    status = solver.solve()
    if status != solver.OPTIMAL:
        raise RuntimeError(f'Min-cost flow did not return OPTIMAL: {status}')
    retained, removed = {}, {}
    for index, edge in enumerate(edges):
        amount = solver.flow(index)
        if not 0 <= amount <= graph[edge]:
            raise AssertionError('Residual violates an arc capacity')
        if amount:
            retained[edge] = amount
        if graph[edge] > amount:
            removed[edge] = graph[edge] - amount
    if positions(retained) != before or positions(removed):
        raise AssertionError('Residual positions or circulation conservation failed')
    objective = sum(retained.values())
    if objective != solver.optimal_cost():
        raise AssertionError('Residual objective differs from solver cost')
    if any((b, a) in retained for a, b in retained):
        raise AssertionError('Optimal positive-cost residual contains a two-cycle')
    return {'status': 'OPTIMAL', 'minimum_final_debt_scaled': objective,
            'removed_scaled': sum(removed.values()), 'input_edges': len(graph),
            'residual_edges': len(retained), 'primal_verified': True,
            'residual': [[a, b, amount] for (a, b), amount in sorted(retained.items())]}


def benchmark(csv_path):
    import ortools

    fixture = load_sarafu(csv_path, tick_microseconds=1)
    gross = gross_graph(fixture.events)
    net = net_graph(fixture.events)
    root = Path(__file__).parent
    sources = {name: hashlib.sha256((root/name).read_bytes()).hexdigest()
               for name in ('temporal_reference.py', 'temporal_sarafu.py')}
    started = time.monotonic()
    gross_reference, static_reference = min_residual(gross), min_residual(net)
    base = sum(net.values())
    lower = gross_reference['minimum_final_debt_scaled']
    static_lower = static_reference['minimum_final_debt_scaled']
    if positions(gross) != positions(net) or lower > static_lower:
        raise AssertionError('Gross relaxation does not contain the static problem')
    return {
        'complete': True, 'amount_scale': fixture.metadata['amount_scale'],
        'source_sha256': sources, 'fixture_metadata': fixture.metadata,
        'solver': {'library': 'ortools', 'version': ortools.__version__,
                   'python': platform.python_version(), 'algorithm': 'SimpleMinCostFlow'},
        'interpretation': 'Gross reference is an optimistic LOWER BOUND on final debt, '
                          'not an attainable temporal optimum; chronology and protocol budgets ignored.',
        'gross_transfer_scaled': sum(gross.values()),
        'no_clearing_final_debt_scaled': base,
        'gross_reference': gross_reference, 'static_final_batch_reference': static_reference,
        'temporal_final_debt_improvement_upper_bound_pct': 100*(base-lower)/base if base else 0.,
        'static_final_batch_clearing_pct': 100*(base-static_lower)/base if base else 0.,
        'elapsed_seconds': time.monotonic()-started,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = benchmark(args.csv)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(report, indent=2)+'\n')
    temporary.replace(path)
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ('fixture_metadata', 'gross_reference',
                                     'static_final_batch_reference', 'source_sha256')}, indent=2))


if __name__ == '__main__':
    main()
