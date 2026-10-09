"""Seeded SYNTHETIC obligation streams; event time is abstract simulator ticks.

No claims about Sarafu transaction timing are made. All algorithms see the same
additions. Hindsight MCF/DFS can wait for the entire stream, so their final clearing
is a quality reference, not a comparison of responsiveness or information access.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import importlib.metadata
import json
from pathlib import Path
import random
import platform

from dfs_benchmark import clear_dfs, describe, mcf_reference, positions, replay


@dataclass(frozen=True, order=True)
class Addition:
    time: int
    source: str
    target: str
    amount: int


def aggregate(additions):
    graph = defaultdict(int)
    for event in additions:
        graph[event.source, event.target] += event.amount
    return dict(graph)


def scenario(kind, seed=0, nodes=24, duration=500):
    """Static, steady and burst arrivals on sparse/dense/community/disconnected graphs.

    A fixed orientation per unordered pair avoids introducing a separate bilateral
    netting policy. Repeated arrivals increase an existing obligation; many first
    arrivals introduce new links. Ring edges guarantee potential circulation.
    """
    if nodes < 6 or duration < 1:
        raise ValueError('Need at least six nodes and a positive duration')
    topology, mode = kind.split('-')
    if topology not in ('sparse', 'dense', 'community', 'disconnected'):
        raise ValueError('Unknown topology')
    if mode not in ('static', 'steady', 'burst'):
        raise ValueError('Unknown arrival mode')
    rng = random.Random(seed)
    arrival_rng = random.Random(seed ^ 0x57EA)
    jitter_rng = random.Random(seed ^ 0xB0757)
    groups = [list(range(nodes))]
    if topology in ('community', 'disconnected'):
        groups = [list(range(nodes // 2)), list(range(nodes // 2, nodes))]
    edges = {}
    for group in groups:
        for a, b in zip(group, group[1:] + group[:1]):
            edges[frozenset((a, b))] = (a, b)
    for a in range(nodes):
        for b in range(a + 1, nodes):
            cross = (a < nodes // 2) != (b < nodes // 2)
            probability = {'sparse': .06, 'dense': .5,
                           'community': .03 if cross else .35,
                           'disconnected': 0 if cross else .2}[topology]
            if frozenset((a, b)) not in edges and rng.random() < probability:
                edges[frozenset((a, b))] = (a, b) if rng.random() < .5 else (b, a)
    additions = []
    for a, b in edges.values():
        for _ in range(rng.randint(1, 4)):
            time = 0 if mode == 'static' else arrival_rng.randint(0, duration)
            if mode == 'burst':
                time = min(duration, (time // max(1, duration // 4)) * max(1, duration // 4) + jitter_rng.randint(0, 5))
            additions.append(Addition(time, str(a), str(b), rng.randint(1, 50)))
    return sorted(additions)


def periodic_dfs(additions, interval=50, until=None, policy='numeric'):
    """Centralized online baseline: snapshot all current debt every interval ticks."""
    if interval < 1:
        raise ValueError('Interval must be positive')
    additions = sorted(additions)
    until = until if until is not None else additions[-1].time + interval
    graph = defaultdict(int)
    records, cursor = [], 0
    for time in range(0, until + 1, interval):
        while cursor < len(additions) and additions[cursor].time <= time:
            event = additions[cursor]
            graph[event.source, event.target] += event.amount
            cursor += 1
        cycles = clear_dfs(dict(graph), policy=policy)
        graph = defaultdict(int, replay(dict(graph), cycles))
        records.extend({'time': time, 'nodes': ns, 'amount': amount} for ns, amount in cycles)
    return records


def audit(additions, records, horizon):
    """Independently replay complete settlements against obligations available then.

    Debt-area measures integrated unsettled edge amount, in amount*ticks. The
    normalized area includes unpaid obligations at horizon (right-censored), and
    is NOT the mean settlement latency of the cleared subset.
    """
    if any(e.time > horizon for e in additions):
        raise ValueError('Horizon precedes an addition')
    events = [(e.time, 0, i, e) for i, e in enumerate(additions)]
    events += [(r['time'], 1, i, r) for i, r in enumerate(records)]
    balances = defaultdict(int)
    area = 0
    previous = 0
    for time, kind, _, event in sorted(events):
        if time < previous or time > horizon:
            raise ValueError('Settlement outside observation horizon')
        area += sum(balances.values()) * (time - previous)
        previous = time
        if kind == 0:
            if event.amount <= 0:
                raise ValueError('Nonpositive addition')
            balances[event.source, event.target] += event.amount
        else:
            balances = defaultdict(int, replay(dict(balances), [(event['nodes'], event['amount'])]))
    area += sum(balances.values()) * (horizon - previous)
    total = aggregate(additions)
    if positions(total) != positions(balances):
        raise AssertionError('Net positions changed')
    cycles = [(r['nodes'], r['amount']) for r in records]
    result = describe(total, cycles)
    result.update({'conservation_ok': True, 'nonnegative_balances': True,
                   'settlements_respect_arrival_times': True,
                   'debt_amount_ticks': area,
                   'mean_observed_outstanding_ticks': area / sum(total.values()) if total else 0,
                   'last_settlement_tick': max((r['time'] for r in records), default=None),
                   'residual_greedy_clearable': sum(len(ns) * amount for ns, amount in clear_dfs(dict(balances)))})
    return result, {edge: value for edge, value in balances.items() if value}


def run_case(kind, seed, nodes, duration, delay, include_mcf=False):
    from distributed import DistributedDFS
    additions = scenario(kind, seed, nodes, duration)
    last_addition = max(e.time for e in additions)
    # Fair observation window includes a quiet suffix, reported separately from arrivals.
    search_horizon = last_addition + 1500
    final_horizon = search_horizon + 2000
    stream_json = json.dumps([e.__dict__ for e in additions], sort_keys=True)
    result = {'scenario': kind, 'seed': seed, 'nodes': nodes,
              'additions': len(additions), 'distinct_links': len(aggregate(additions)),
              'input_amount': sum(e.amount for e in additions),
              'last_addition_tick': last_addition,
              'search_horizon': search_horizon, 'observation_horizon': final_horizon,
              'stream_sha256': hashlib.sha256(stream_json.encode()).hexdigest(),
              'max_message_delay': delay, 'retry_interval': 50, 'max_hops': nodes,
              'search_budget': max(100, nodes * 8), 'periodic_interval': 50, 'methods': {}}
    total = aggregate(additions)
    for label, cycles in [('hindsight_dfs', clear_dfs(total)), ('hindsight_largest_dfs', clear_dfs(total, policy='largest'))] + (
            [('hindsight_mcf', mcf_reference(total))] if include_mcf else []):
        records = [{'time': last_addition, 'nodes': ns, 'amount': amount} for ns, amount in cycles]
        result['methods'][label] = audit(additions, records, final_horizon)[0]
    for policy in ('numeric', 'largest'):
        label = 'periodic_dfs' if policy == 'numeric' else 'periodic_largest_dfs'
        result['methods'][label] = audit(additions, periodic_dfs(additions, until=search_horizon, policy=policy), final_horizon)[0]
    for policy in ('random', 'largest'):
        simulation = DistributedDFS({}, seed=seed, max_delay=delay, retry_interval=50,
                                    max_hops=nodes, search_budget=max(100, nodes * 8), policy=policy)
        for event in additions:
            simulation.add_edge(event.source, event.target, event.amount, at=event.time)
        simulation.run(until=search_horizon, max_events=1000000)
        simulation.stop_searches()
        simulation.drain(max_events=1000000)
        if simulation.time > final_horizon:
            raise RuntimeError('Drain exceeded observation horizon; increase all method horizons')
        if simulation.events or simulation.pending_reservations:
            raise AssertionError('Incomplete drain')
        records = simulation.cycle_records
        measured, expected = audit(additions, records, final_horizon)
        if expected != simulation.graph_snapshot():
            raise AssertionError('Simulator state differs from independent settlement replay')
        measured['protocol'] = dict(simulation.metrics)
        measured['pending_events_after_drain'] = len(simulation.events)
        measured['pending_reservations_after_drain'] = simulation.pending_reservations
        measured['drain_completed_at'] = simulation.time
        measured['messages_per_cleared_unit'] = simulation.metrics.get('messages', 0) / measured['cleared_scaled'] if measured['cleared_scaled'] else None
        measured['transaction_duration_mean'] = sum(r['duration'] for r in records) / len(records) if records else None
        measured['transaction_duration_max'] = max((r['duration'] for r in records), default=None)
        result['methods']['distributed_dfs' if policy == 'random' else 'distributed_largest_dfs'] = measured
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', type=int, nargs='+', default=[0, 1, 2])
    parser.add_argument('--nodes', type=int, default=24)
    parser.add_argument('--duration', type=int, default=500)
    parser.add_argument('--delays', type=int, nargs='+', default=[1, 7])
    parser.add_argument('--scenarios', nargs='+', default=[f'{topology}-{mode}' for topology in ('sparse', 'dense', 'community', 'disconnected') for mode in ('static', 'steady', 'burst')])
    parser.add_argument('--mcf', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('experiments/results/distributed-synthetic.json'))
    args = parser.parse_args()
    cases = []
    for kind in args.scenarios:
        for seed in args.seeds:
            for delay in args.delays:
                cases.append(run_case(kind, seed, args.nodes, args.duration, delay, args.mcf))
                print(f'{kind} seed={seed} delay={delay}: {cases[-1]["methods"]["distributed_dfs"]["cleared_percent"]:.1f}%', flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'schema_version': 1, 'synthetic': True, 'complete': True,
        'expected_cases': len(args.scenarios) * len(args.seeds) * len(args.delays),
        'ortools_version': importlib.metadata.version('ortools') if args.mcf else None,
        'python_version': platform.python_version(),
        'source_sha256': {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                          for name in ('simulate.py', 'distributed.py', 'dfs_benchmark.py')},
        'assumptions': ['Reliable bounded-delay messages, no crashes or Byzantine behavior.',
                        'Neighbors communicate along either direction of an obligation link.',
                        'Amounts are synthetic integers; time is abstract ticks.',
                        'Hindsight references see the complete stream; online methods do not.',
                        'Acyclic residual means maximal cancellation, not globally maximum clearing.',
                        'Debt-area includes unpaid obligations through the observation horizon.',
                        'Periodic and distributed discovery stop at the search horizon; distributed in-flight work drains.',
                        'Message counts exclude payload sizes; search tokens disclose and carry discovered paths.'],
        'cases': cases}, indent=2) + '\n')


if __name__ == '__main__':
    main()
