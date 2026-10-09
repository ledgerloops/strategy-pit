import unittest

from simulate import Addition, aggregate, audit, periodic_dfs, scenario, run_case
from dfs_benchmark import clear_dfs, replay


class SimulationTests(unittest.TestCase):
    def test_steady_stream_and_burst_have_new_links_and_repeatable_input(self):
        for topology in ('sparse', 'dense', 'community', 'disconnected'):
            for mode in ('static', 'steady', 'burst'):
                events = scenario(f'{topology}-{mode}', seed=9)
                self.assertEqual(events, scenario(f'{topology}-{mode}', seed=9))
                graph = aggregate(events)
                self.assertFalse(any((b, a) in graph for a, b in graph))
                replay(graph, clear_dfs(graph))
                self.assertGreater(len(graph), 10)
                if mode != 'static':
                    self.assertGreater(len({e.time for e in events}), 1)

    def test_modes_preserve_same_aggregate_obligations(self):
        for topology in ('sparse', 'dense', 'community', 'disconnected'):
            graphs = [aggregate(scenario(f'{topology}-{mode}', seed=4))
                      for mode in ('static', 'steady', 'burst')]
            self.assertEqual(graphs[0], graphs[1])
            self.assertEqual(graphs[1], graphs[2])

    def test_distributed_case_is_audited_and_fully_drained(self):
        result = run_case('community-steady', 8, 12, 100, 5)
        protocol = result['methods']['distributed_dfs']
        self.assertTrue(protocol['conservation_ok'])
        self.assertTrue(protocol['settlements_respect_arrival_times'])
        self.assertEqual(protocol['pending_reservations_after_drain'], 0)
        self.assertEqual(protocol['pending_events_after_drain'], 0)
        self.assertGreater(protocol['protocol']['messages'], 0)

    def test_late_link_reopens_previously_acyclic_component(self):
        additions = [Addition(0, 'a', 'b', 5), Addition(0, 'b', 'c', 5), Addition(75, 'c', 'a', 3)]
        cycles = periodic_dfs(additions, interval=50, until=100)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0]['time'], 100)
        result, remaining = audit(additions, cycles, horizon=150)
        self.assertEqual(result['cleared_scaled'], 9)
        self.assertEqual(remaining, {('a', 'b'): 2, ('b', 'c'): 2})
        self.assertEqual(result['debt_amount_ticks'], 1275)

    def test_audit_rejects_using_future_link(self):
        additions = [Addition(0, 'a', 'b', 5), Addition(0, 'b', 'c', 5), Addition(75, 'c', 'a', 3)]
        with self.assertRaises(ValueError):
            audit(additions, [{'time': 50, 'nodes': ['a', 'b', 'c'], 'amount': 3}], 150)

    def test_disconnected_scenario_has_no_cross_component_links(self):
        self.assertTrue(all((int(e.source) < 12) == (int(e.target) < 12)
                            for e in scenario('disconnected-steady')))


if __name__ == '__main__':
    unittest.main()
