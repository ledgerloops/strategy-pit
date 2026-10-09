"""Small, centralized signed-trustline experiments, with independently audited moves.

The exhaustive cycle search and exact oracle require a bird's-eye view. These are
objective/feasibility experiments, not a distributed protocol or consent mechanism.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import random

from dfs_benchmark import clear_dfs, mcf_reference, replay
from trustlines import (Trustline, TrustlineNetwork, apply_move, best_cycle_move,
                        enumerate_cycles)


def line(a, b, balance, lower, upper):
    """Accept a source-view balance and bounds; store canonical endpoint order."""
    return (Trustline(a, b, balance, lower, upper) if a < b else
            Trustline(b, a, -balance, -upper, -lower))


def snapshot(network):
    return [asdict(value) for _, value in sorted(network.lines.items())]


def independent_positions(balances):
    result = defaultdict(int)
    for (a, b), balance in balances.items():
        result[a] += balance
        result[b] -= balance
    return dict(result)


def audit(initial, moves, expected=None):
    """Replay raw updates without the implementation's quote/apply/audit helpers."""
    balances = {edge: value.balance for edge, value in initial.lines.items()}
    bounds = {edge: (value.lower, value.upper) for edge, value in initial.lines.items()}
    positions = independent_positions(balances)
    debt_trace = [sum(abs(value) for value in balances.values())]
    moved_away = 0
    for move in moves:
        cycle, delta = list(move.cycle), move.delta
        if len(cycle) < 3 or len(set(cycle)) != len(cycle):
            raise ValueError('Cycle must contain at least three distinct nodes')
        if type(delta) is not int or delta == 0:
            raise ValueError('Expected a nonzero integer cycle increment')
        before = dict(balances)
        if any(tuple(sorted((a, b))) not in balances
               for a, b in zip(cycle, cycle[1:] + cycle[:1])):
            raise ValueError('Cycle uses an absent trustline')
        source_before = tuple(before[tuple(sorted((a, b)))] * (1 if a < b else -1)
                              for a, b in zip(cycle, cycle[1:] + cycle[:1]))
        if source_before != move.balances_before:
            raise ValueError('Recorded source-view balances differ from replay')
        for a, b in zip(cycle, cycle[1:] + cycle[:1]):
            edge = tuple(sorted((a, b)))
            if edge not in balances:
                raise ValueError('Cycle uses an absent trustline')
            balances[edge] += delta if a < b else -delta
            lower, upper = bounds[edge]
            if not lower <= balances[edge] <= upper:
                raise ValueError('Cycle exceeds a trustline limit')
            moved_away += int(abs(balances[edge]) > abs(before[edge]))
        if independent_positions(balances) != positions:
            raise ValueError('Net positions changed')
        debt = sum(abs(value) for value in balances.values())
        if debt >= debt_trace[-1]:
            raise ValueError('Move does not strictly reduce gross debt')
        if move.debt_before != debt_trace[-1] or move.debt_after != debt:
            raise ValueError('Recorded objective differs from independent replay')
        debt_trace.append(debt)
    if expected is not None and balances != {edge: value.balance for edge, value in expected.lines.items()}:
        raise ValueError('Recorded final balances differ from replay')
    return {'bounds_ok': True, 'positions_preserved': True,
            'strict_debt_reduction': True, 'debt_trace': debt_trace,
            'edge_updates_away_from_zero': moved_away}


def exact_reference(network):
    """Integer convex-flow oracle for bounds containing zero; returns final debt."""
    from ortools.graph.python import min_cost_flow
    solver = min_cost_flow.SimpleMinCostFlow()
    balances = {edge: value.balance for edge, value in network.lines.items()}
    positions = independent_positions(balances)
    nodes = {name: index for index, name in enumerate(sorted(positions))}
    for (a, b), value in sorted(network.lines.items()):
        solver.add_arc_with_capacity_and_unit_cost(nodes[a], nodes[b], value.upper, 1)
        solver.add_arc_with_capacity_and_unit_cost(nodes[b], nodes[a], -value.lower, 1)
    for node, position in positions.items():
        solver.set_node_supply(nodes[node], position)
    if solver.solve() != solver.OPTIMAL:
        raise RuntimeError('Exact trustline oracle failed')
    final = {}
    for index, (edge, value) in enumerate(sorted(network.lines.items())):
        balance = solver.flow(2 * index) - solver.flow(2 * index + 1)
        if not value.lower <= balance <= value.upper:
            raise AssertionError('Oracle exceeds limits')
        final[edge] = balance
    if independent_positions(final) != positions:
        raise AssertionError('Oracle changes net positions')
    debt = sum(abs(value) for value in final.values())
    if debt != solver.optimal_cost():
        raise AssertionError('Oracle has offsetting unnecessary gross flows')
    return debt


def old_model(network, include_mcf=True):
    graph = {}
    for (a, b), value in network.lines.items():
        if value.balance:
            graph[(a, b) if value.balance < 0 else (b, a)] = abs(value.balance)
    result = {'dfs_final_debt': sum(replay(graph, clear_dfs(graph)).values())}
    if include_mcf:
        result['optimal_final_debt'] = sum(replay(graph, mcf_reference(graph)).values())
    return result


def run_policy(initial, policy, seed=0, max_length=None):
    if policy not in ('first', 'best', 'random'):
        raise ValueError('Unknown policy')
    network = initial.copy()
    cycles = enumerate_cycles(network, max_length=max_length)
    rng = random.Random(seed)
    moves = []
    for _ in range(10000):
        candidates = [best_cycle_move(network, cycle) for cycle in cycles.cycles]
        candidates = [move for move in candidates if move.debt_after < move.debt_before]
        if not candidates:
            break
        if policy == 'first':
            move = candidates[0]
        elif policy == 'best':
            move = max(candidates, key=lambda value: value.debt_before - value.debt_after)
        else:
            move = rng.choice(candidates)
        apply_move(network, move)
        moves.append(move)
    else:
        raise RuntimeError('Cycle iteration budget exhausted')
    checked = audit(initial, moves, network)
    checked.update({'policy': policy, 'seed': seed, 'max_cycle_length': max_length,
                    'candidate_cycles': len(cycles.cycles), 'moves': len(moves),
                    'cycle_hops': sum(len(move.cycle) for move in moves),
                    'initial_debt': initial.debt(), 'final_debt': network.debt(),
                    'cycle_enumeration_complete': cycles.complete})
    return checked


def ratchet_fixture():
    return TrustlineNetwork([line('A', 'B', 0, -1, 1)] +
                            [line(a, b, -3, -3, 3) for a, b in
                             [('B', 'C'), ('C', 'A'), ('A', 'D'), ('D', 'B')]])


def rerouting_fixture():
    return TrustlineNetwork([line('A', 'B', -3, -3, 0),
                            line('B', 'C', -3, -3, 0),
                            line('A', 'C', 0, -3, 3)])


def fixtures(include_mcf=True):
    initial = ratchet_fixture()
    network = initial.copy()
    moves, trace = [], []
    for cycle in [('A', 'B', 'C'), ('B', 'A', 'D')] * 2:
        move = best_cycle_move(network, cycle)
        apply_move(network, move)
        moves.append(move)
        trace.append({'cycle': list(cycle), 'delta': move.delta,
                      'shared_A_view_B': network.lines['A', 'B'].balance,
                      'gross_debt': network.debt()})
    result = {
        'ratchet': {'input': snapshot(initial), 'trace': trace,
                    'audit': audit(initial, moves, network),
                    'old_model': old_model(initial, include_mcf),
                    'interpretation': 'Triangle scheduling demonstrates alternating shared capacity. '
                                      'An ordinary outer four-cycle also clears all 12 in the old model; '
                                      'this fixture does not establish an unrestricted optimum improvement.'},
        'rerouting': {'input': snapshot(rerouting_fixture()),
                      'old_model': old_model(rerouting_fixture(), include_mcf),
                      'trustline': run_policy(rerouting_fixture(), 'best'),
                      'interpretation': 'Credit on the initially zero AC link replaces two debts with one; '
                                        'gross debt falls 6 to 3 while all net positions are unchanged.'}}
    if include_mcf:
        for name, graph in [('ratchet', initial), ('rerouting', rerouting_fixture())]:
            result[name]['exact_final_debt'] = exact_reference(graph)
    return result


def seeded_graph(seed, headroom, density=.5, nodes=6):
    """Same initial signed balances at every headroom; only limits change."""
    if nodes < 3 or headroom < 0:
        raise ValueError('Need at least three nodes and nonnegative headroom')
    rng = random.Random(seed)
    lines = []
    for a in range(nodes):
        for b in range(a + 1, nodes):
            if b == a + 1 or (a == 0 and b == nodes - 1) or rng.random() < density:
                balance = rng.randint(-5, 5)
                lines.append(line(str(a), str(b), balance,
                                  min(0, balance) - headroom, max(0, balance) + headroom))
    return TrustlineNetwork(lines)


def run_suite(seeds=10, nodes=6, include_mcf=True):
    cases = []
    for seed in range(seeds):
        for density in (.15, .65):
            for headroom in (0, 1, 5):
                network = seeded_graph(seed, headroom, density, nodes)
                record = {'seed': seed, 'density': density, 'headroom': headroom,
                          'input': snapshot(network), 'old_model': old_model(network, include_mcf),
                          'runs': [run_policy(network, policy, seed, max_length)
                                   for max_length in (3, None)
                                   for policy in ('first', 'best', 'random')]}
                if include_mcf:
                    optimum = exact_reference(network)
                    record['exact_final_debt'] = optimum
                    for run in record['runs']:
                        run['gap_to_exact'] = run['final_debt'] - optimum
                        if run['gap_to_exact'] < 0:
                            raise AssertionError('Cycle solution exceeds exact optimum')
                        if run['max_cycle_length'] is None and run['gap_to_exact']:
                            raise AssertionError('Exhaustive improving-cycle search failed exact oracle')
                    if headroom == 0 and optimum != record['old_model']['optimal_final_debt']:
                        raise AssertionError('Zero headroom differs from old-model exact feasible set')
                cases.append(record)
    root = Path(__file__).parent
    return {'schema': 1, 'python': platform.python_version(),
            'ortools': importlib.metadata.version('ortools') if include_mcf else None,
            'source_sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                              for name in ('trustlines.py', 'trustline_experiments.py', 'dfs_benchmark.py')},
            'parameters': {'seeds': seeds, 'nodes': nodes, 'headrooms': [0, 1, 5],
                           'densities': [.15, .65], 'max_cycle_lengths': [3, None]},
            'scope': 'Centralized synthetic integer-credit simulations, all simple cycles in both '
                     'signed directions. Cycle hops are a structural count, not network messages. '
                     'No crash, privacy, consent, atomic distributed settlement, or new-link arrivals modeled here.',
            'objective': 'sum(abs(canonical pair balance)); gross bilateral debt, not net node debt',
            'fixtures': fixtures(include_mcf), 'cases': cases,
            'expected_cases': seeds * 6, 'expected_runs': seeds * 36,
            'complete': len(cases) == seeds * 6}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', type=int, default=10)
    parser.add_argument('--nodes', type=int, default=6)
    parser.add_argument('--without-mcf', action='store_true')
    parser.add_argument('--output', type=Path, default=Path(__file__).parent / 'results/trustlines.json')
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error('--seeds must be positive')
    output = run_suite(args.seeds, args.nodes, not args.without_mcf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps({'output': str(args.output), 'cases': len(output['cases']),
                      'runs': sum(len(case['runs']) for case in output['cases']),
                      'complete': output['complete']}))


if __name__ == '__main__':
    main()
