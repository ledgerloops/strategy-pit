"""Exact unlimited-neighbor-credit comparison on the pinned Sarafu debt graph.

Input edges are debtor -> creditor with positive scaled integer amounts, as in
Strategy Pit. Conserving outgoing minus incoming conserves each node's net debt
(and equivalently the opposite signed net asset position in trustlines.py).
No new neighbor pairs are introduced unless extra_neighbors is explicitly passed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import time

from dfs_benchmark import PINNED_REF, SCALE, pinned_text, positions, read_graph


def solve(graph, *, unlimited=False, extra_neighbors=()):
    from ortools.graph.python import min_cost_flow
    if any(type(amount) is not int or amount <= 0 or a == b
           for (a, b), amount in graph.items()):
        raise ValueError('Positive integer non-self debts required')
    if any((b, a) in graph for a, b in graph):
        raise ValueError('Input must be bilaterally netted')
    neighbors = {tuple(sorted(pair)) for pair in graph}
    for pair in extra_neighbors:
        if len(pair) != 2 or pair[0] == pair[1]:
            raise ValueError('Neighbor pair requires two distinct nodes')
        neighbors.add(tuple(sorted(pair)))
    nodes = sorted({n for pair in neighbors for n in pair})
    index = {n: i for i, n in enumerate(nodes)}
    net = positions(graph)
    supply = sum(value for value in net.values() if value > 0)
    # Every positive-cost optimal flow can be cycle-free and decomposed into
    # source/sink paths. No edge then carries more than TOTAL positive supply.
    # This exact finite bound represents infinity for the objective, rather than
    # an arbitrary large constant. It need not contain the initial cyclic flow.
    capacity = supply
    if unlimited:
        arcs = [(a, b, capacity) for a, b in sorted(neighbors)]
        arcs += [(b, a, capacity) for a, b in sorted(neighbors)]
    else:
        arcs = [(a, b, value) for (a, b), value in sorted(graph.items())]
    solver = min_cost_flow.SimpleMinCostFlow()
    for a, b, limit in arcs:
        solver.add_arc_with_capacity_and_unit_cost(index[a], index[b], limit, 1)
    for n in nodes:
        solver.set_node_supply(index[n], net.get(n, 0))
    start = time.perf_counter()
    if solver.solve() != solver.OPTIMAL:
        raise RuntimeError('Min-cost flow did not return OPTIMAL')
    seconds = time.perf_counter() - start
    remaining = {(a, b): solver.flow(i) for i, (a, b, _) in enumerate(arcs)
                 if solver.flow(i)}
    if positions(remaining) != net:
        raise AssertionError('A node net position changed')
    if any((b, a) in remaining for a, b in remaining):
        raise AssertionError('Unnecessary opposing flows in positive-cost optimum')
    if any(tuple(sorted(edge)) not in neighbors for edge in remaining):
        raise AssertionError('New unauthorized neighbor pair')
    if not unlimited and any(amount > graph.get(edge, 0) for edge, amount in remaining.items()):
        raise AssertionError('Cancellation-only optimum increases a debt')
    final_total = sum(remaining.values())
    if final_total != solver.optimal_cost() or final_total > sum(graph.values()):
        raise AssertionError('Invalid objective')
    grown = {e: amount for e, amount in remaining.items() if amount > graph.get(e, 0)}
    reversed_edges = {e: amount for e, amount in remaining.items() if (e[1], e[0]) in graph}
    return {
        'unlimited': unlimited, 'solver_status': 'OPTIMAL', 'seconds': seconds,
        'original_total_scaled': sum(graph.values()), 'remaining_scaled': final_total,
        'cleared_scaled': sum(graph.values()) - final_total,
        'cleared_percent': 100 * (sum(graph.values()) - final_total) / sum(graph.values()) if graph else 0,
        'net_internal_debt_scaled': supply,
        'mean_hops_per_net_unit': final_total / supply if supply else 0,
        'positive_final_edges': len(remaining), 'nodes': len(nodes), 'neighbor_pairs': len(neighbors),
        'increased_or_new_direction_edges': len(grown),
        'increased_existing_direction_edges': sum(e in graph for e in grown),
        'reversed_original_edges': len(reversed_edges),
        'total_reversed_amount_scaled': sum(reversed_edges.values()),
        'total_increase_over_original_direction_scaled': sum(amount - graph.get(e, 0) for e, amount in grown.items()),
        'net_positions_preserved': True, 'neighbor_pairs_preserved': True,
        'infinity_replaced_by_proven_supply_bound': capacity if unlimited else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('experiments/results/unlimited-credit.json'))
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    text = pinned_text(repo, PINNED_REF, 'debt.csv')
    graph = read_graph(text)
    results = {'complete': False, 'dataset_commit': PINNED_REF,
               'dataset_sha256': hashlib.sha256(text.encode()).hexdigest(), 'scale': SCALE,
               'source_sha256': {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                 for name in ('unlimited_credit.py', 'dfs_benchmark.py')},
               'python': platform.python_version(), 'ortools': importlib.metadata.version('ortools'),
               'assumption': 'Neighbors are the unordered nonzero pairs in the pinned debt.csv; '
                             'no original zero-net historical pairs are recovered, no new pairs added. '
                             'All existing neighbor relationships permit unbounded signed credit. '
                             'No per-node absolute-exposure or gross-payable preservation condition.',
               'runs': []}
    for unlimited in (False, True):
        result = solve(graph, unlimited=unlimited)
        results['runs'].append(result)
        print(json.dumps(result), flush=True)
    results['complete'] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    main()
