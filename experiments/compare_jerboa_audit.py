"""Audit cycle output, reporting skipped invalid cycles separately.

Usage: python experiments/compare_jerboa_audit.py DEBT.csv SOLUTION.csv
The valid-subset score is never a claim that the whole solution is valid.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from dfs_benchmark import positions, read_graph, units


def audit(debt_path: Path, solution_path: Path) -> dict:
    graph = read_graph(debt_path.read_text())
    remaining = dict(graph)
    errors = []
    valid = 0
    lines = [line for line in solution_path.read_text().splitlines() if line.strip()]
    for index, line in enumerate(lines):
        try:
            *nodes, value = line.split()
            amount = units(value)
            if len(nodes) < 3 or len(set(nodes)) != len(nodes):
                raise ValueError('Cycle must have at least three distinct nodes')
            edges = list(zip(nodes, nodes[1:] + nodes[:1]))
            bad = [
                {'edge': edge, 'available': remaining.get(edge, 0), 'requested': amount}
                for edge in edges if remaining.get(edge, 0) < amount
            ]
            if bad:
                raise ValueError(str(bad))
            for edge in edges:
                remaining[edge] -= amount
            valid += 1
        except ValueError as error:
            errors.append({'line': index + 1, 'error': str(error)})
    assert positions(graph) == positions(remaining)
    initial = sum(graph.values())
    cleared = initial - sum(remaining.values())
    return {
        'path': str(solution_path),
        'sha256': hashlib.sha256(solution_path.read_bytes()).hexdigest(),
        'cycles': len(lines),
        'valid_cycles': valid,
        'invalid_cycles': len(errors),
        'whole_solution_valid': not errors,
        'valid_subset_cleared_pct': 100 * cleared / initial,
        'initial_debt_units': initial,
        'valid_subset_cleared_units': cleared,
        'errors': errors,
    }


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    print(json.dumps(audit(Path(sys.argv[1]), Path(sys.argv[2])), indent=2))
