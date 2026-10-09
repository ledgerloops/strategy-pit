"""Safety and progress checks under concurrent local searches and delayed delivery."""
import unittest

from experiments.distributed import DistributedDFS
from experiments.dfs_benchmark import positions, replay


class DistributedTests(unittest.TestCase):
    def finish_and_check(self, sim, graph):
        sim.drain()
        residual = sim.graph_snapshot()
        self.assertEqual(replay(graph, sim.cycles), residual)
        self.assertEqual(positions(graph), positions(residual))
        self.assertEqual(sim.pending_reservations, 0)
        self.assertTrue(all(amount > 0 for amount in residual.values()))
        for _, a, b, _ in sim.message_log:
            self.assertIn(frozenset((a, b)), sim.channels)
        return residual

    def test_triangle_progress_across_delays(self):
        graph = {('a', 'b'): 8, ('b', 'c'): 6, ('c', 'a'): 7}
        for seed in range(10):
            with self.subTest(seed=seed):
                sim = DistributedDFS(graph, seed=seed, max_delay=13, retry_interval=7)
                sim.run(700)
                residual = self.finish_and_check(sim, graph)
                self.assertEqual(sum(residual.values()), 3)
                self.assertEqual(sum(amount for _, amount in sim.cycles), 6)

    def test_overlapping_cycles_cannot_double_spend(self):
        graph = {('a', 'b'): 5, ('b', 'c'): 8, ('c', 'a'): 8,
                 ('b', 'd'): 9, ('d', 'a'): 9, ('c', 'd'): 4}
        for seed in range(20):
            with self.subTest(seed=seed):
                sim = DistributedDFS(graph, seed=seed, max_delay=23, retry_interval=3)
                sim.run(1200)
                residual = self.finish_and_check(sim, graph)
                self.assertNotIn(('a', 'b'), residual)
                self.assertEqual(sum(amount for _, amount in sim.cycles), 5)

    def test_dead_end_becomes_cycle_after_new_link(self):
        graph = {('a', 'b'): 10, ('b', 'c'): 10}
        sim = DistributedDFS(graph, seed=14, retry_interval=5)
        sim.run(100)
        self.assertEqual(sim.graph_snapshot(), graph)
        self.assertEqual(sim.cycles, [])
        sim.add_edge('c', 'a', 7, at=130)
        graph['c', 'a'] = 7
        sim.run(400)
        residual = self.finish_and_check(sim, graph)
        self.assertEqual(residual, {('a', 'b'): 3, ('b', 'c'): 3})
        self.assertTrue(all(record['time'] >= 130 for record in sim.cycle_records))

    def test_links_arrive_during_reservations(self):
        graph = {('a', 'b'): 4, ('b', 'c'): 4, ('c', 'a'): 4}
        sim = DistributedDFS(graph, seed=9, max_delay=19, retry_interval=4)
        for at in range(5, 200, 7):
            edge = list(graph)[at % 3]
            sim.add_edge(*edge, 2, at=at)
            graph[edge] += 2
        sim.run(1000)
        self.finish_and_check(sim, graph)
        self.assertGreater(len(sim.cycles), 1)

    def test_search_bounds_terminate_without_erasing_debt(self):
        graph = {(str(i), str(i+1)): 4 for i in range(30)}
        graph['30', '0'] = 4
        sim = DistributedDFS(graph, max_hops=5, search_budget=8, retry_interval=3)
        sim.run(80)
        self.assertEqual(self.finish_and_check(sim, graph), graph)
        self.assertEqual(sim.cycles, [])

    def test_largest_local_policy_is_safe_with_delays(self):
        graph = {('a', 'b'): 12, ('b', 'c'): 7, ('c', 'a'): 7,
                 ('b', 'd'): 11, ('d', 'a'): 11}
        for seed in range(10):
            sim = DistributedDFS(graph, policy='largest', seed=seed,
                                 max_delay=17, retry_interval=4)
            sim.run(700)
            residual = self.finish_and_check(sim, graph)
            self.assertNotIn(('a', 'b'), residual)
            self.assertGreater(sim.metrics['message_node_ids'], sim.metrics['messages'])
            self.assertTrue(all(record['duration'] > 0 for record in sim.cycle_records))

    def test_event_budget_reports_incomplete_run(self):
        sim = DistributedDFS({('a', 'b'): 1}, retry_interval=1)
        with self.assertRaisesRegex(RuntimeError, 'budget'):
            sim.run(100, max_events=1)
        sim.drain()


if __name__ == '__main__':
    unittest.main()
