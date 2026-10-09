from dataclasses import replace
import itertools
import unittest

from trustline_experiments import (audit, exact_reference, fixtures, line, old_model,
                                   ratchet_fixture, rerouting_fixture, run_policy,
                                   run_suite, seeded_graph, snapshot)
from trustlines import TrustlineNetwork, apply_move, best_cycle_move


try:
    import ortools
except ImportError:
    ortools = None


class TrustlineExperimentTests(unittest.TestCase):
    def test_ratchet_alternates_and_outer_cycle_is_fair_baseline(self):
        results = fixtures(include_mcf=False)
        ratchet = results['ratchet']
        self.assertEqual([row['delta'] for row in ratchet['trace']], [1, 2, 2, 1])
        self.assertEqual([row['shared_A_view_B'] for row in ratchet['trace']], [1, -1, 1, 0])
        self.assertEqual(ratchet['audit']['debt_trace'], [12, 11, 7, 3, 0])
        self.assertEqual(ratchet['old_model']['dfs_final_debt'], 0)

    def test_new_credit_reroutes_real_old_model_dead_end(self):
        initial = rerouting_fixture()
        self.assertEqual(old_model(initial, False)['dfs_final_debt'], 6)
        result = run_policy(initial, 'best')
        self.assertEqual(result['final_debt'], 3)
        self.assertEqual(result['edge_updates_away_from_zero'], 1)
        self.assertTrue(result['positions_preserved'])

    def test_limits_change_but_graph_input_stays_same_across_headrooms(self):
        for seed in range(5):
            graphs = [seeded_graph(seed, headroom) for headroom in (0, 1, 5)]
            balances = [{edge: value.balance for edge, value in graph.lines.items()}
                        for graph in graphs]
            self.assertEqual(balances[0], balances[1])
            self.assertEqual(balances[0], balances[2])
            self.assertEqual(snapshot(graphs[0]), snapshot(seeded_graph(seed, 0)))

    def test_audit_rejects_false_objective_bounds_noop_and_final_state(self):
        initial = ratchet_fixture()
        move = best_cycle_move(initial, ('A', 'B', 'C'))
        for invalid in [replace(move, debt_after=0), replace(move, delta=2),
                        replace(move, delta=0), replace(move, balances_before=(0, 0, 0))]:
            with self.assertRaises(ValueError):
                audit(initial, [invalid])
        with self.assertRaises(ValueError):
            audit(initial, [move], initial)
        final = initial.copy()
        apply_move(final, move)
        self.assertEqual(audit(initial, [move], final)['debt_trace'], [12, 11])

    def test_seeded_random_policy_is_repeatable(self):
        network = seeded_graph(3, 5, .65)
        self.assertEqual(run_policy(network, 'random', 42), run_policy(network, 'random', 42))
        self.assertEqual(network.debt(), run_policy(network, 'best')['initial_debt'])

    @unittest.skipUnless(ortools, 'Optional ORTools oracle is not installed')
    def test_exact_reference_matches_independent_exhaustive_balances(self):
        for source_balances in itertools.product((-1, 0, 1), repeat=3):
            graph = TrustlineNetwork([line(a, b, value, -1, 1) for (a, b), value in
                                     zip([('A', 'B'), ('A', 'C'), ('B', 'C')], source_balances)])
            position = graph.positions()
            best = 100
            for ab, ac, bc in itertools.product((-1, 0, 1), repeat=3):
                if {'A': ab + ac, 'B': bc - ab, 'C': -ac - bc} == position:
                    best = min(best, abs(ab) + abs(ac) + abs(bc))
            self.assertEqual(exact_reference(graph), best)

    @unittest.skipUnless(ortools, 'Optional ORTools oracle is not installed')
    def test_full_cycle_search_matches_oracle_and_zero_headroom_baseline(self):
        suite = run_suite(seeds=2)
        self.assertTrue(suite['complete'])
        self.assertEqual(len(suite['cases']), suite['expected_cases'])
        self.assertEqual(sum(len(case['runs']) for case in suite['cases']), suite['expected_runs'])
        for case in suite['cases']:
            for run in case['runs']:
                self.assertTrue(run['bounds_ok'])
                if run['max_cycle_length'] is None:
                    self.assertEqual(run['gap_to_exact'], 0)
            if case['headroom'] == 0:
                self.assertEqual(case['exact_final_debt'], case['old_model']['optimal_final_debt'])


if __name__ == '__main__':
    unittest.main()
