"""Independent locality and delayed-settlement checks for Numbat.

These test the reliable-message research model, not crash-safe settlement.
"""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from numbat import Numbat
from dfs_benchmark import positions, replay


class LocalCapabilities:
    """A node may send messages, use its clock/RNG, and record metrics.

    Graph inspection and other nodes' state are deliberately inaccessible.
    Scheduler internals retain graph access to deliver messages and audit results.
    """
    permitted = frozenset({
        'send', 'schedule', 'time', 'random', 'metrics', 'searches_enabled',
        'retry_interval', 'search_budget', 'max_hops', 'capacity_power',
        'close_first', 'snapshot_capacity', 'cycles', 'cycle_records',
    })

    def __init__(self, simulator):
        self._simulator = simulator

    def __getattr__(self, name):
        if name not in self.permitted:
            raise AssertionError(f'Node attempted nonlocal simulator access: {name}')
        return getattr(self._simulator, name)


class NumbatAdversarialTests(unittest.TestCase):
    def check_completed(self, simulator, original):
        simulator.stop_searches()
        simulator.drain()
        remaining = simulator.graph_snapshot()
        self.assertEqual(replay(original, simulator.cycles), remaining)
        self.assertEqual(positions(original), positions(remaining))
        self.assertEqual(simulator.pending_reservations, 0)
        self.assertEqual(simulator.events, [])
        for _, sender, receiver, _ in simulator.message_log:
            self.assertIn(frozenset((sender, receiver)), simulator.channels)
        return remaining

    def test_protocol_runs_without_graph_capability(self):
        graph = {('a', 'b'): 8, ('b', 'c'): 5, ('c', 'a'): 5,
                 ('b', 'd'): 4, ('d', 'e'): 4, ('e', 'a'): 4}
        simulator = Numbat(graph, seed=37, max_delay=11, retry_interval=7)
        for node in simulator.nodes.values():
            node.sim = LocalCapabilities(simulator)
        simulator.run(1000)
        self.check_completed(simulator, graph)
        self.assertGreater(len(simulator.cycles), 0)

    def test_competing_cycles_with_replenishment(self):
        initial = {('a', 'b'): 2, ('b', 'c'): 7, ('c', 'a'): 7,
                   ('b', 'd'): 7, ('d', 'a'): 7}
        for seed in (107, 109, 113, 127):
            for exponent in (0, 0.5, 1, 2):
                with self.subTest(seed=seed, exponent=exponent):
                    graph = dict(initial)
                    simulator = Numbat(graph, seed=seed, max_delay=23,
                                       retry_interval=3, capacity_power=exponent)
                    for tick in (17, 31, 51, 83):
                        simulator.add_edge('a', 'b', 2, at=tick)
                        graph['a', 'b'] += 2
                    simulator.run(1200)
                    self.check_completed(simulator, graph)

    def test_new_link_revives_previously_exhausted_search(self):
        graph = {('a', 'b'): 6, ('b', 'c'): 6}
        simulator = Numbat(graph, seed=137, retry_interval=5)
        simulator.run(150)
        self.assertEqual(simulator.cycles, [])
        simulator.add_edge('c', 'd', 6, at=170)
        simulator.add_edge('d', 'a', 6, at=190)
        graph.update({('c', 'd'): 6, ('d', 'a'): 6})
        simulator.run(700)
        self.assertEqual(self.check_completed(simulator, graph), {})
        self.assertTrue(all(row['time'] >= 190 for row in simulator.cycle_records))

    def test_hop_cap_reports_uncleared_long_cycle(self):
        graph = {(str(i), str((i + 1) % 13)): 10 for i in range(13)}
        simulator = Numbat(graph, seed=139, max_hops=5, search_budget=50)
        simulator.run(400)
        self.assertEqual(self.check_completed(simulator, graph), graph)
        self.assertEqual(simulator.cycles, [])


if __name__ == '__main__':
    unittest.main()
