"""Analytical and exhaustive checks for unlimited-neighbor credit."""
import itertools
import unittest

from dfs_benchmark import positions
from unlimited_credit import solve

try:
    import ortools
except ImportError:
    ortools = None


@unittest.skipUnless(ortools, 'Requires optional OR-Tools environment')
class UnlimitedCreditTests(unittest.TestCase):
    def test_tree_positions_fix_every_edge(self):
        graph = {('a', 'b'): 3, ('b', 'c'): 3}
        result = solve(graph, unlimited=True)
        self.assertEqual(result['remaining_scaled'], 6)
        self.assertEqual(result['net_internal_debt_scaled'], 3)
        self.assertEqual(result['mean_hops_per_net_unit'], 2)

    def test_additional_neighbor_pair_shortens_obligation_route(self):
        graph = {('a', 'b'): 3, ('b', 'c'): 3}
        self.assertEqual(solve(graph, unlimited=True, extra_neighbors=[('a', 'c')])['remaining_scaled'], 3)
        self.assertEqual(solve(graph, unlimited=False, extra_neighbors=[('a', 'c')])['remaining_scaled'], 6)

    def test_initial_balances_can_exceed_reference_capacity(self):
        graph = {('a', 'b'): 10, ('b', 'c'): 10, ('c', 'a'): 9}
        result = solve(graph, unlimited=True)
        self.assertEqual(result['infinity_replaced_by_proven_supply_bound'], 1)
        self.assertEqual(result['remaining_scaled'], 1)
        self.assertEqual(solve(graph)['remaining_scaled'], 2)
        self.assertEqual(result['reversed_original_edges'], 1)

    def test_zero_supply_and_empty_graph(self):
        graph = {('a', 'b'): 3, ('b', 'c'): 3, ('c', 'a'): 3}
        self.assertEqual(solve(graph, unlimited=True)['remaining_scaled'], 0)
        self.assertEqual(solve({}, unlimited=True)['remaining_scaled'], 0)

    def test_disconnected_components(self):
        graph = {('a', 'b'): 3, ('b', 'c'): 3, ('c', 'a'): 3, ('d', 'e'): 2}
        result = solve(graph, unlimited=True)
        self.assertEqual(result['remaining_scaled'], 2)
        self.assertEqual(result['positive_final_edges'], 1)

    def test_all_small_triangle_states_against_exhaustive_balances(self):
        pairs = [('a', 'b'), ('a', 'c'), ('b', 'c')]
        for original in itertools.product((-1, 0, 1), repeat=3):
            def graph_for(values):
                return {(a, b) if value > 0 else (b, a): abs(value)
                        for (a, b), value in zip(pairs, values) if value}
            graph = graph_for(original)
            net = positions(graph)
            supply = sum(value for value in net.values() if value > 0)
            best = min(sum(abs(v) for v in values)
                       for values in itertools.product(range(-supply, supply + 1), repeat=3)
                       if positions(graph_for(values)) == net)
            result = solve(graph, unlimited=True, extra_neighbors=pairs)
            self.assertEqual(result['remaining_scaled'], best, original)


if __name__ == '__main__':
    unittest.main()
