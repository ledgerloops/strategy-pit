"""Reproducible, integer-capacity experiments; no runtime dependencies except optional MCF.

The graph is a static, bilaterally netted debt snapshot. This is NOT a distributed
protocol or an online transaction replay. Search pruning never deletes real debt.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import platform
import random
import subprocess
import time

SCALE = 1000
PINNED_REF = '06c6a2fb5702c7066ded7cf14672ba07ed5098c4'
Graph = dict[tuple[str, str], int]
Cycle = tuple[list[str], int]


def units(value: str) -> int:
    amount = Decimal(value) * SCALE
    if not amount.is_finite() or amount != amount.to_integral_value() or amount <= 0:
        raise ValueError(f'Expected positive amount with at most three decimals: {value}')
    return int(amount)


def read_graph(text: str) -> Graph:
    graph: Graph = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        a, b, amount = line.split()
        if a == b:
            raise ValueError('Self obligations are not supported')
        graph[a, b] = graph.get((a, b), 0) + units(amount)
    if any((b, a) in graph for a, b in graph):
        raise ValueError('Input must be bilaterally netted first')
    return graph


def read_cycles(text: str) -> list[Cycle]:
    cycles = []
    for line in text.splitlines():
        if line.strip():
            *nodes, amount = line.split()
            cycles.append((nodes, units(amount)))
    return cycles


def positions(graph: Graph) -> dict[str, int]:
    result = defaultdict(int)
    for (a, b), amount in graph.items():
        result[a] += amount
        result[b] -= amount
    return {node: amount for node, amount in result.items() if amount}


def replay(graph: Graph, cycles: list[Cycle]) -> Graph:
    """Independent strict validation; reject invalid cycles instead of skipping them."""
    remaining = dict(graph)
    for nodes, amount in cycles:
        if len(nodes) < 3 or len(set(nodes)) != len(nodes):
            raise ValueError('A cycle must have at least three distinct nodes')
        if not isinstance(amount, int) or amount <= 0:
            raise ValueError('Cycle amount must be a positive scaled integer')
        edges = list(zip(nodes, nodes[1:] + nodes[:1]))
        if any(remaining.get(edge, 0) < amount for edge in edges):
            raise ValueError('Cycle exceeds a balance or uses an absent edge')
        for edge in edges:
            remaining[edge] -= amount
    if positions(remaining) != positions(graph):
        raise ValueError('Net positions changed')
    return {edge: amount for edge, amount in remaining.items() if amount}


def node_key(node: str) -> tuple:
    # Match JavaScript Object.keys array-index order for the original Sarafu IDs.
    if node.isdecimal() and str(int(node)) == node and int(node) < 2**32 - 1:
        return (0, int(node))
    return (1, node)


def clear_dfs(graph: Graph, policy: str = 'numeric', seed: int = 0) -> list[Cycle]:
    """Greedy cycle cancellation. 'relabel' applies a shared random node ranking.

    Largest/smallest select by CURRENT capacity, breaking ties by numeric node ID.
    'largest-relabel' randomizes roots and capacity ties using a shared node rank.
    A separate search graph permits pruning dead ends without erasing obligations.
    """
    if policy not in ('numeric', 'relabel', 'largest', 'smallest', 'largest-relabel'):
        raise ValueError(f'Unknown policy {policy}')
    nodes = sorted({n for edge in graph for n in edge}, key=node_key)
    if policy in ('relabel', 'largest-relabel'):
        random.Random(seed).shuffle(nodes)
    rank = {node: i for i, node in enumerate(nodes)}
    active = {node: {} for node in nodes}
    for (a, b), amount in sorted(graph.items(), key=lambda pair: rank[pair[0][1]]):
        if not isinstance(amount, int) or amount <= 0 or a == b:
            raise ValueError('Invalid graph capacity or self edge')
        active[a][b] = amount
    if any((b, a) in graph for a, b in graph):
        raise ValueError('Input must be bilaterally netted first')
    path: list[str] = []
    path_pos: dict[str, int] = {}
    root = 0
    cycles: list[Cycle] = []
    while True:
        if not path:
            while root < len(nodes) and not active[nodes[root]]:
                root += 1
            if root == len(nodes):
                return cycles
            path = [nodes[root]]
            path_pos[path[0]] = 0
        u = path[-1]
        if not active[u]:
            path.pop()
            del path_pos[u]
            if path:
                active[path[-1]].pop(u, None)
            continue
        if policy in ('largest', 'largest-relabel'):
            v = min(active[u], key=lambda n: (-active[u][n], rank[n]))
        elif policy == 'smallest':
            v = min(active[u], key=lambda n: (active[u][n], rank[n]))
        else:
            v = next(iter(active[u]))
        if v not in path_pos:
            path_pos[v] = len(path)
            path.append(v)
            continue
        start = path_pos[v]
        cycle = path[start:]
        edges = list(zip(cycle, cycle[1:] + cycle[:1]))
        amount = min(active[a][b] for a, b in edges)
        for a, b in edges:
            active[a][b] -= amount
            if not active[a][b]:
                del active[a][b]
        cycles.append((cycle, amount))
        for node in cycle:
            del path_pos[node]
        del path[start:]


def mcf_reference(graph: Graph) -> list[Cycle]:
    """Minimize retained debt subject to capacities and unchanged net positions.

    The removed flow is a circulation. DFS only decomposes this circulation into
    executable cycles; it does not improve the optimizer's objective.
    """
    from ortools.graph.python import min_cost_flow
    nodes = sorted({n for edge in graph for n in edge}, key=node_key)
    index = {n: i for i, n in enumerate(nodes)}
    solver = min_cost_flow.SimpleMinCostFlow()
    edges = list(graph)
    for a, b in edges:
        solver.add_arc_with_capacity_and_unit_cost(index[a], index[b], graph[a, b], 1)
    net = positions(graph)
    for n in nodes:
        solver.set_node_supply(index[n], net.get(n, 0))
    status = solver.solve()
    if status != solver.OPTIMAL:
        raise RuntimeError(f'MCF failed with status {status}')
    circulation = {edge: graph[edge] - solver.flow(i) for i, edge in enumerate(edges)
                   if graph[edge] > solver.flow(i)}
    cycles = clear_dfs(circulation)
    if replay(circulation, cycles):
        raise AssertionError('Could not decompose the full MCF circulation')
    remaining = replay(graph, cycles)
    if sum(remaining.values()) != solver.optimal_cost():
        raise AssertionError('Reference objective mismatch')
    return cycles


def describe(graph: Graph, cycles: list[Cycle]) -> dict:
    remaining = replay(graph, cycles)
    total = sum(graph.values())
    cleared = total - sum(remaining.values())
    counts = Counter()
    weights = Counter()
    for nodes, amount in cycles:
        counts[len(nodes)] += 1
        weights[len(nodes)] += len(nodes) * amount
    # Remaining acyclic graph certifies maximality, not maximum clearing.
    adjacency = defaultdict(list)
    indegree = Counter()
    for a, b in remaining:
        adjacency[a].append(b)
        indegree[b] += 1
        indegree[a] += 0
    queue = [n for n in indegree if indegree[n] == 0]
    visited = 0
    while queue:
        n = queue.pop()
        visited += 1
        for other in adjacency[n]:
            indegree[other] -= 1
            if indegree[other] == 0:
                queue.append(other)
    return {
        'cleared_scaled': cleared,
        'cleared_percent': 100 * cleared / total if total else 0,
        'cycles': len(cycles),
        'cycle_hops': sum(length * count for length, count in counts.items()),
        'max_cycle_length': max(counts, default=0),
        'residual_is_acyclic': visited == len(indegree),
        'by_length': {str(k): {'cycles': counts[k], 'cleared_scaled': weights[k]}
                      for k in sorted(counts)},
        'cleared_share_in_loops_up_to': {
            str(limit): sum(v for k, v in weights.items() if k <= limit) / cleared
            if cleared else 0 for limit in (3, 5, 10, 20, 50)
        },
    }


def pinned_text(repo: Path, ref: str, name: str) -> str:
    return subprocess.check_output(['git', '-C', str(repo), 'show', f'{ref}:{name}'], text=True)


def benchmark(repo: Path, output: Path, seeds: int, include_mcf: bool) -> None:
    if seeds < 1:
        raise ValueError('At least one seed is required')
    ref = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', PINNED_REF], text=True).strip()
    debt = pinned_text(repo, ref, 'debt.csv')
    graph = read_graph(debt)
    results = {
        'dataset_commit': ref, 'dataset_sha256': hashlib.sha256(debt.encode()).hexdigest(),
        'scale': SCALE, 'input_edges': len(graph), 'input_total_scaled': sum(graph.values()),
        'python': platform.python_version(), 'platform': platform.platform(),
        'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'note': 'Static graph experiment. Timings are single runs, not cross-language comparisons. '
                'cycle_hops is a structural proxy, not measured network messages.',
        'saved_solutions': {}, 'runs': [], 'complete': False,
        'expected_runs': 3 + 2 * seeds + int(include_mcf),
    }
    if include_mcf:
        from importlib.metadata import version
        results['ortools'] = version('ortools')
    for name in ('dfs.csv', 'mcf-dfs.csv'):
        text = pinned_text(repo, ref, name)
        results['saved_solutions'][name] = {
            'sha256': hashlib.sha256(text.encode()).hexdigest(),
            **describe(graph, read_cycles(text)),
        }
    configs = [('numeric', 0), ('largest', 0), ('smallest', 0)]
    configs += [(policy, seed) for policy in ('relabel', 'largest-relabel') for seed in range(seeds)]
    if include_mcf:
        configs += [('mcf', 0)]
    for policy, seed in configs:
        started = time.perf_counter()
        cycles = mcf_reference(graph) if policy == 'mcf' else clear_dfs(graph, policy, seed)
        seconds = time.perf_counter() - started
        report = describe(graph, cycles)
        if not report['residual_is_acyclic']:
            raise AssertionError(f'{policy}/{seed} did not finish clearing')
        results['runs'].append({'policy': policy, 'seed': seed, 'seconds': seconds, **report})
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, indent=2) + '\n')
        print(f'{policy}/{seed}: {report["cleared_percent"]:.4f}% '
              f'{report["cycles"]} cycles {seconds:.3f}s', flush=True)
    numeric = results['runs'][0]
    saved = results['saved_solutions']['dfs.csv']
    if numeric['cleared_scaled'] != saved['cleared_scaled'] or numeric['by_length'] != saved['by_length']:
        raise AssertionError('Numeric policy does not reproduce the historical DFS result')
    results['complete'] = True
    output.write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, default=Path('experiments/results/sarafu.json'))
    parser.add_argument('--seeds', type=int, default=20)
    parser.add_argument('--mcf', action='store_true', help='Requires ortools==9.14.6206')
    args = parser.parse_args()
    benchmark(args.repo, args.output, args.seeds, args.mcf)
