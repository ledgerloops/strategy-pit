"""Exhaustive, offline counterexample to current private-policy convergence.

No participants, transport, workload or optimizer is run.  Seven signed integer
balances each range over [-1, 1].  The actual app's pure bilateral comfort rule
is checked separately from the research policy's two-edge consent restriction.
Run from any directory: python experiments/mdg2/check_convergence_counterexample.py
"""
import argparse
import hashlib
from itertools import product
import json
from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[2] / 'app'
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))
from comfort import comfort_move

# A negative entry denotes debt from the first endpoint to the second.
EDGES = (('A', 'B'), ('B', 'C'), ('C', 'D'), ('D', 'A'),
         ('C', 'E'), ('E', 'F'), ('F', 'A'))
NODES = tuple(sorted({node for edge in EDGES for node in edge}))
PREFERENCES = dict(credit_limit=1, comfort_min=-1, comfort_max=1, auto_adjust=True)


def positions(values):
    result = dict.fromkeys(NODES, 0)
    for (a, b), balance in zip(EDGES, values):
        result[a] += balance
        result[b] -= balance
    return result


def gross(values):
    return sum(map(abs, values))


def exposures(values):
    result = dict.fromkeys(NODES, 0)
    for (a, b), balance in zip(EDGES, values):
        result[a] += abs(balance)
        result[b] += abs(balance)
    return result


def arcs(values):
    result = {}
    for (a, b), balance in zip(EDGES, values):
        for source, target, before in ((a, b, balance), (b, a, -balance)):
            after = before + 1
            if not -1 <= after <= 1:
                continue
            assert comfort_move(before, after, PREFERENCES, PREFERENCES)
            assert comfort_move(-before, -after, PREFERENCES, PREFERENCES)
            result[source, target] = dict(before=before, after=after,
                                          cost=abs(after)-abs(before))
    return result


def simple_cycles(available):
    """Enumerate both directed orientations, deduplicating rotations only."""
    adjacency = {node: sorted(b for a, b in available if a == node) for node in NODES}
    found = set()

    def visit(path):
        for peer in adjacency[path[-1]]:
            if peer == path[0] and len(path) >= 3:
                found.add(min(tuple(path[i:]+path[:i]) for i in range(len(path))))
            elif peer not in path:
                visit(path+[peer])

    for node in NODES:
        visit([node])
    return sorted(found)


def cycle_costs(path, available):
    costs = [available[a, b]['cost'] for a, b in zip(path, path[1:]+path[:1])]
    local = {node: costs[i-1]+costs[i] for i, node in enumerate(path)}
    assert sum(local.values()) == 2*sum(costs)
    return sum(costs), local


def clear_debt_cycle(values, path):
    result = list(values)
    for a, b in zip(path, path[1:]+path[:1]):
        if (a, b) in EDGES:
            index, sign = EDGES.index((a, b)), 1
        else:
            index, sign = EDGES.index((b, a)), -1
        before = sign*result[index]
        assert before == -1
        assert comfort_move(before, before+1, PREFERENCES, PREFERENCES)
        result[index] += sign
    assert positions(result) == positions(values)
    return tuple(result)


def check():
    initial = (-1,)*len(EDGES)
    short_first = clear_debt_cycle(initial, ('A', 'B', 'C', 'D'))
    long_first = clear_debt_cycle(initial, ('A', 'B', 'C', 'E', 'F'))
    assert (gross(initial), gross(short_first), gross(long_first)) == (7, 3, 2)
    initial_arcs = arcs(initial)
    for path in (('A', 'B', 'C', 'D'), ('A', 'B', 'C', 'E', 'F')):
        total, local = cycle_costs(path, initial_arcs)
        assert total < 0 and all(cost < 0 for cost in local.values())

    feasible, minimum, optima = 0, None, []
    for candidate in product((-1, 0, 1), repeat=len(EDGES)):
        if positions(candidate) != positions(initial):
            continue
        feasible += 1
        debt = gross(candidate)
        if minimum is None or debt < minimum:
            minimum, optima = debt, [candidate]
        elif debt == minimum:
            optima.append(candidate)
    assert minimum == gross(long_first) == 2 < gross(short_first)
    # Each local two-edge nonexpansion also makes total per-node exposure
    # nonincreasing. A zero-exposure intermediary can never be reactivated.
    zeroed = [node for node, amount in exposures(short_first).items() if amount == 0]
    assert zeroed == ['B', 'D']
    assert all(any(exposures(candidate)[node] > 0 for node in zeroed) for candidate in optima)

    remaining = arcs(short_first)
    cycles = simple_cycles(remaining)
    improving = []
    for path in cycles:
        total, local = cycle_costs(path, remaining)
        if total >= 0:
            continue
        # Actual bilateral comfort admits every edge. The private pair gate does not.
        assert max(local.values()) == 2
        assert not all(cost <= 0 for cost in local.values())
        improving.append(dict(cycle='-'.join(path+(path[0],)), gross_delta=total,
                              rejected_participants={node: cost for node, cost in local.items() if cost > 0}))
    assert len(improving) == 2 and all(row['gross_delta'] == -1 for row in improving)
    assert not any(sum(remaining[a, b]['cost'] for a, b in zip(path, path[1:]+path[:1])) == -len(path)
                   for path in cycles), 'No ordinary debt cycle should remain'
    return dict(verified=True, scope='Offline bounded integer mathematics; not a discovery or protocol experiment',
                edges=[list(edge) for edge in EDGES], signed_edge_domain=[-1, 0, 1],
                enumerated_ledgers=3**len(EDGES), feasible_ledgers=feasible,
                initial_debt=gross(initial), short_first_debt=gross(short_first),
                long_first_debt=gross(long_first), exhaustive_optimum=minimum,
                optimal_ledgers=len(optima), zero_exposure_nodes_after_short=zeroed,
                all_optima_require_reactivating_one=True, residual_simple_cycles=len(cycles),
                improving_residual_cycles=improving, private_admissible_improving_cycles=0,
                comfort_source_sha256=hashlib.sha256((APP/'comfort.py').read_bytes()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = json.dumps(check(), indent=2)+'\n'
    if args.output:
        args.output.write_text(result)
    print(result, end='')


if __name__ == '__main__':
    main()
