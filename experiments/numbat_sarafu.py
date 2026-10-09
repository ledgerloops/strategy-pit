"""Finite-budget neighbor-message comparison on the pinned full Sarafu snapshot.

No historical Jerboa/Jaribu timing or performance equivalence is claimed. The
250k message admission cutoff is soft: admitted work drains and overshoot is
reported. Search is bounded and may leave substantial clearing opportunities.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import platform
import time

from dfs_benchmark import PINNED_REF, SCALE, pinned_text, read_graph, describe, replay, positions
from numbat_benchmark import CappedDFS, CappedNumbat

ROOT = Path(__file__).parent


def main():
    debt = pinned_text(ROOT.parent, PINNED_REF, 'debt.csv')
    graph = read_graph(debt)
    snapshot_hash = hashlib.sha256(debt.encode()).hexdigest()
    historical = json.loads((ROOT / 'results/sarafu.json').read_text())
    assert historical['complete'] and historical['dataset_sha256'] == snapshot_hash
    config = dict(seed=0, max_delay=5, retry_interval=50, max_hops=100,
                  search_budget=256, message_cutoff=250000)
    result = dict(schema_version=1, complete=False, expected_methods=3,
                  dataset_commit=PINNED_REF, dataset_sha256=snapshot_hash,
                  input_edges=len(graph), input_nodes=len({n for e in graph for n in e}),
                  input_total_scaled=sum(graph.values()), scale=SCALE,
                  python_version=platform.python_version(), config=config, search_horizon=500,
                  source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                      for name in ('numbat.py', 'distributed.py', 'dfs_benchmark.py',
                                   'numbat_benchmark.py', 'numbat_sarafu.py')},
                  reference_scores=historical['saved_solutions'], methods={},
                  assumptions=['Node decisions use only own balances/reservations and received tokens.',
                    'One scheduler seed and finite bounded searches; not an estimate of eventual maximal clearing.',
                    'Reliable exactly-once neighbor messaging; honest nodes and no crashes.',
                    'Stop admitting new searches at250000 messages or500ticks, then drain all admitted work.',
                    'Final messages can exceed cutoff; overshoot and drain tick are reported.',
                    'Offline historical DFS and MCF scores have global access and are quality references only.',
                    'Audit independently replays every completed cycle once and verifies all net positions.'])
    output = ROOT / 'results/numbat-sarafu.json'
    def save():
        output.write_text(json.dumps(result, indent=2) + '\n')
    save()
    for label, cls, extra in [('distributed_dfs', CappedDFS, {}),
                             ('distributed_largest_dfs', CappedDFS, dict(policy='largest')),
                             ('numbat', CappedNumbat, {})]:
        started = time.monotonic()
        simulation = cls(graph, **config, **extra)
        simulation.run(500, max_events=5000000)
        simulation.drain(max_events=5000000)
        expected = replay(graph, simulation.cycles)
        assert expected == simulation.graph_snapshot()
        assert positions(expected) == positions(graph)
        assert not simulation.events and simulation.pending_reservations == 0
        measured = describe(graph, simulation.cycles)
        measured.update(protocol=dict(simulation.metrics), cutoff_tick=simulation.cutoff_tick,
                        message_overshoot=max(0, simulation.metrics['messages']-config['message_cutoff']),
                        drain_completed_at=simulation.time, pending_events_after_drain=0,
                        pending_reservations_after_drain=0, conservation_ok=True,
                        independent_replay_ok=True, seconds=time.monotonic()-started)
        result['methods'][label] = measured
        save()
        print(f"{label}: {measured['cleared_percent']:.6f}% "
              f"{simulation.metrics['messages']} messages, "
              f"drained at {simulation.time}; {measured['seconds']:.1f}s", flush=True)
        del simulation
    result['complete'] = True
    save()


if __name__ == '__main__':
    main()
