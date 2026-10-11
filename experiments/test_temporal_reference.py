"""Small exact references and chronology counterexamples, independent of search."""
import importlib.util
from itertools import product
import unittest

from temporal_reference import gross_graph, min_residual, positions
from temporal_sarafu import Transfer, net_graph

HAS_ORTOOLS = importlib.util.find_spec('ortools') is not None


@unittest.skipUnless(HAS_ORTOOLS, 'Optional OR-Tools solver unavailable')
class TemporalReferenceTests(unittest.TestCase):
    def test_gross_bound_can_improve_on_final_batch_optimum(self):
        arrivals = [Transfer(i, a, b, 1) for i, (a, b) in
                    enumerate([(0, 1), (1, 2), (2, 0), (1, 0)])]
        gross, net = gross_graph(arrivals), net_graph(arrivals)
        self.assertEqual(min_residual(gross)['minimum_final_debt_scaled'], 1)
        self.assertEqual(min_residual(net)['minimum_final_debt_scaled'], 2)
        # Clear the first three arrivals' triangle, then post the last transfer.
        first = net_graph(arrivals[:3])
        self.assertEqual(first, {(0, 1): 1, (1, 2): 1, (2, 0): 1})
        after_clear_and_last = net_graph(arrivals[3:])
        self.assertEqual(sum(after_clear_and_last.values()), 1)
        self.assertEqual(positions(after_clear_and_last), positions(gross))

    def test_same_gross_bound_can_be_unattainable_in_fixed_chronology(self):
        arrivals = [Transfer(i, a, b, 1) for i, (a, b) in
                    enumerate([(0, 1), (1, 0), (1, 2), (2, 0)])]
        self.assertEqual(net_graph(arrivals[:2]), {})
        # Neither intermediate prefix nor the final graph contains a >=3 cycle.
        self.assertEqual(len(net_graph(arrivals[:3])), 1)
        self.assertEqual(net_graph(arrivals), {(1, 2): 1, (2, 0): 1})
        self.assertEqual(min_residual(gross_graph(arrivals))['minimum_final_debt_scaled'], 1)
        self.assertEqual(sum(net_graph(arrivals).values()), 2)

    def test_objective_matches_exhaustive_integer_feasible_residuals(self):
        edges = [(0, 1), (1, 0), (1, 2), (2, 0)]
        for capacities in [(1, 1, 1, 1), (2, 1, 2, 1), (1, 2, 1, 2), (2, 2, 2, 2)]:
            graph = dict(zip(edges, capacities))
            optimum = min(sum(values) for values in product(*(range(c+1) for c in capacities))
                          if positions(dict(zip(edges, values))) == positions(graph))
            self.assertEqual(min_residual(graph)['minimum_final_debt_scaled'], optimum)

    def test_two_cycles_and_empty_graph(self):
        self.assertEqual(min_residual({(0, 1): 3, (1, 0): 2})['minimum_final_debt_scaled'], 1)
        self.assertEqual(min_residual({})['minimum_final_debt_scaled'], 0)
        with self.assertRaises(ValueError):
            min_residual({(0, 0): 1})
        with self.assertRaises(ValueError):
            min_residual({(0, 1): -1})


if __name__ == '__main__':
    unittest.main()
