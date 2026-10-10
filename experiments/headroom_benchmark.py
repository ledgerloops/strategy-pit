"""Reproducible Headroom diagnostics, with independent signed-record auditing.

MCF is an offline reference only. Supplied legacy cycle streams initialize
postpasses; they are not part of a wholly node-local pipeline. The cold-start
case starts with the original ledger. All Headroom runs serialize initiators.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import itertools
import json
from pathlib import Path
import platform
import time

from dfs_benchmark import mcf_reference, read_graph, replay
from headroom import Headroom, HeadroomNode

HERE = Path(__file__).resolve().parent


def net(graph):
    result = Counter()
    for (source, target), amount in graph.items():
        result[source] -= amount
        result[target] += amount
    return {node: value for node, value in result.items() if value}


def audit_records(caps, initial, records, final):
    """Replay every settlement without using simulator audit or mutation code."""
    balances = {edge: initial.get(edge, 0) for edge in caps}
    if set(initial) - set(caps) or net(balances) != net(caps):
        raise AssertionError('invalid initial ledger')
    if any(not 0 <= amount <= caps[edge] for edge, amount in balances.items()):
        raise AssertionError('initial balance exceeds original consent')
    restored = decreased = mixed = exposure_increase_events = 0
    target_net = net(caps)
    for record in records:
        nodes, directions, amount = record['nodes'], record['directions'], record['amount']
        if (len(nodes) < 2 or len(set(nodes)) != len(nodes)
                or len(nodes) != len(directions) or type(amount) is not int or amount <= 0
                or any(type(d) is not int or d not in (-1, 1) for d in directions)):
            raise AssertionError('invalid signed cycle')
        change = 0
        position_changes = Counter()
        participant_changes = Counter()
        for a, b, direction in zip(nodes, nodes[1:] + nodes[:1], directions):
            edge = (a, b) if direction == 1 else (b, a)
            if edge not in caps:
                raise AssertionError('cycle uses non-neighbor or absent obligation')
            old_balance = balances[edge]
            balances[edge] -= direction * amount
            debt_delta = balances[edge] - old_balance
            change -= debt_delta
            position_changes[edge[0]] -= debt_delta
            position_changes[edge[1]] += debt_delta
            if not 0 <= balances[edge] <= caps[edge]:
                raise AssertionError('cycle exceeds residual capacity')
            participant_changes[a] -= direction * amount
            participant_changes[b] -= direction * amount
            if direction == 1:
                decreased += amount
            else:
                restored += amount
        if change <= 0 or change != record['debt_reduction'] or any(position_changes.values()):
            raise AssertionError('non-improving cycle or changed net position')
        mixed += int(-1 in directions)
        exposure_increase_events += sum(value > 0 for value in participant_changes.values())
    if net(balances) != target_net:
        raise AssertionError('final net positions changed')
    if balances != {edge: final.get(edge, 0) for edge in caps} or set(final) - set(caps):
        raise AssertionError('replayed ledger differs from simulator')
    if decreased - restored != sum(initial.values()) - sum(final.values()):
        raise AssertionError('accounting mismatch')
    return {'settlements': len(records), 'mixed_settlements': mixed,
            'restored_scaled': restored, 'decreased_scaled': decreased,
            'participant_exposure_increase_events': exposure_increase_events,
            'every_settlement_preserved_net_positions': True,
            'every_settlement_strictly_reduced_total_debt': True,
            'every_balance_within_original_cap': True,
            'final_ledger_matches_independent_replay': True}


def load_legacy(caps, path, allow_invalid=False):
    """Retain the historical Jerboa valid-subset convention, explicitly labelled."""
    balances = dict(caps)
    accepted = rejected = 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        *nodes, value = line.split()
        scaled = Decimal(value) * 1000
        edges = list(zip(nodes, nodes[1:] + nodes[:1]))
        valid = (scaled.is_finite() and scaled == scaled.to_integral_value()
                 and scaled > 0 and len(nodes) >= 3 and len(nodes) == len(set(nodes))
                 and all(edge in balances and balances[edge] >= scaled for edge in edges))
        if not valid:
            if not allow_invalid:
                raise AssertionError('invalid legacy settlement')
            rejected += 1
            continue
        for edge in edges:
            balances[edge] -= int(scaled)
        accepted += 1
    assert net(balances) == net(caps)
    return balances, {'accepted_cycles': accepted, 'rejected_proposals': rejected,
                      'solution_sha256': sha(path), 'solution_file': str(path.relative_to(HERE))}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixtures():
    alice = {('A', 'B'): 7, ('A', 'C'): 5, ('D', 'A'): 5,
             ('C', 'D'): 5, ('B', 'C'): 3}
    alice_greedy = {('A', 'B'): 7, ('B', 'C'): 3}
    trap = {('0', '1'): 1, ('1', '2'): 1, ('2', '0'): 1,
            ('1', '3'): 1, ('3', '4'): 1, ('4', '0'): 1}
    trap_greedy = {('1', '3'): 1, ('3', '4'): 1, ('4', '0'): 1}
    return [('alice', alice, alice_greedy), ('shared-edge', trap, trap_greedy)]


def fixture_checks():
    results = []
    for name, caps, current in fixtures():
        target = net(caps)
        best = min(sum(values) for values in itertools.product(*(range(v + 1) for v in caps.values()))
                   if net(dict(zip(caps, values))) == target)
        mcf_final = replay(caps, mcf_reference(caps))
        sim = Headroom(caps, current, seed=1, search_budget=1000)
        final = sim.run(2)
        audit = audit_records(caps, current, sim.records, final)
        assert sum(final.values()) == sum(mcf_final.values()) == best
        results.append({'name': name, 'initial_debt': sum(caps.values()),
                        'greedy_debt': sum(current.values()), 'final_debt': sum(final.values()),
                        'brute_force_optimum': best, 'mcf_optimum': sum(mcf_final.values()),
                        'audit': audit})
    return results


class ReductionOnlyNode(HeadroomNode):
    """Ablation: identical scheduling/search, but never offer restoration."""
    def residual(self, neighbor, direction):
        return 0 if direction == -1 else super().residual(neighbor, direction)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=HERE / 'results/headroom.json')
    parser.add_argument('--budget', type=int, default=64)
    parser.add_argument('--rounds', type=int, default=2)
    parser.add_argument('--seeds', type=int, nargs='+', default=[0, 1])
    args = parser.parse_args()
    caps = read_graph(args.input.read_text())
    total = sum(caps.values())
    mcf_final = replay(caps, mcf_reference(caps))
    optimum = total - sum(mcf_final.values())
    cases = [('cold-start', caps, {'initialization': 'original ledger; all routing decisions node-local'}),
             ('cold-start-no-restoration-ablation', caps, {'initialization': 'original ledger; identical scheduler/search with restoration disabled'})]
    for name, path, skip in [
        ('jaribu-postpass', HERE / 'results/animal-comparison/jaribu/jaribu-50k-node22-s1-i10.cycles', False),
        ('jerboa-valid-subset-postpass', HERE / 'results/animal-comparison/jerboa/oct-fresh.solution', True),
    ]:
        state, metadata = load_legacy(caps, path, skip)
        metadata['initialization'] = ('shared-global-graph Jaribu; diagnostic postpass only' if name.startswith('jaribu')
                                      else 'historical central-semaphore Jerboa; invalid proposals skipped; diagnostic postpass only')
        cases.append((name, state, metadata))
    report = {
        'input_sha256': sha(args.input), 'input_basename': args.input.name,
        'source_sha256': {name: sha(HERE / name) for name in ['headroom.py', 'headroom_benchmark.py']},
        'python': platform.python_version(), 'nodes': len({n for e in caps for n in e}),
        'edges': len(caps), 'scale': 1000, 'initial_debt_scaled': total,
        'mcf_cleared_scaled': optimum, 'mcf_percent': 100 * optimum / total,
        'assumptions': ['static original caps', 'reliable exactly-once neighbor messages',
                        'honest nodes and no crashes', 'globally serialized initiators and settlements',
                        'token carries path and capacities; no routing decision uses complete graph',
                        'MCF and independent auditor are offline references only',
                        'all setup advertisements count as messages; each round starts one search per node',
                        'legacy initialization costs excluded from postpass message counts',
                        'node-local search does not constitute a concurrent decentralized scheduler'],
        'fixtures': fixture_checks(), 'runs': [],
    }
    for name, initial, metadata in cases:
        for seed in args.seeds:
            started = time.monotonic()
            sim = Headroom(caps, initial, seed=seed, search_budget=args.budget, max_hops=64)
            if name == 'cold-start-no-restoration-ablation':
                for node in sim.nodes.values():
                    node.__class__ = ReductionOnlyNode
            rounds = []
            for round_number in range(1, args.rounds + 1):
                final = sim.run(1)
                cleared = total - sum(final.values())
                audit_started = time.monotonic()
                audit = audit_records(caps, initial, sim.records, final)
                rounds.append({'round': round_number, 'cleared_scaled': cleared,
                               'cleared_percent': 100 * cleared / total,
                               'fraction_mcf_cleared': cleared / optimum,
                               'additional_cleared_scaled': sum(initial.values()) - sum(final.values()),
                               'metrics': dict(sim.metrics), 'audit': audit,
                               'independent_audit_seconds': time.monotonic() - audit_started})
                print(name, seed, round_number, rounds[-1]['cleared_percent'], 'messages', sim.metrics['messages'], flush=True)
            report['runs'].append({'case': name, 'seed': seed, 'search_budget': args.budget,
                                   'max_hops': 64, 'initialization': metadata,
                                   'starting_cleared_percent': 100 * (total - sum(initial.values())) / total,
                                   'seconds_including_independent_audits': time.monotonic() - started,
                                   'rounds': rounds})
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(str(args.output), flush=True)


if __name__ == '__main__':
    main()
