"""Deterministic offline witness and consent checks; no performance campaign."""
import copy
import itertools
import random
import unittest

from private_residual_diagnostic import diagnose, diagnose_edges


def prefs(low=-10000, high=10000, auto=True, credit=10000):
    return dict(credit_limit=credit, comfort_min=low, comfort_max=high, auto_adjust=auto)


def edges(values, policy=None):
    policy = policy or prefs()
    return [(a, b, balance, copy.deepcopy(policy), copy.deepcopy(policy)) for a, b, balance in values]


def exhaustive_negative(result):
    """Brute force elementary cycles, independent of Bellman-Ford."""
    graph = {}
    for a, b, value, own, other in result:
        graph[a, b] = value
        graph[b, a] = -value
    nodes = sorted({a for a, b in graph})
    # Called only with broad, all-opt-in bounds far from balances.
    for length in range(3, len(nodes)+1):
        for path in itertools.permutations(nodes, length):
            if path[0] != min(path):
                continue
            pairs = list(zip(path, path[1:]+path[:1]))
            if all(pair in graph for pair in pairs):
                cost = sum(abs(graph[pair]+1)-abs(graph[pair]) for pair in pairs)
                if cost < 0:
                    return True
    return False


class ResidualDiagnosticTests(unittest.TestCase):
    def test_ordinary_debt_cycle_replays_and_preserves_net_positions(self):
        result = diagnose_edges(edges([('a', 'b', -2), ('b', 'c', -2), ('c', 'a', -2)]))
        self.assertEqual((result['nodes'], result['trustlines'], result['gross_debt']), (3, 3, 6))
        for kind in ('positive_debt_cycle', 'admissible_debt_cycle', 'improving_headroom_cycle'):
            witness = result[kind]
            self.assertEqual(witness['gross_reduction'], 3)
            self.assertEqual(witness['assisted_edges'], 0)
            self.assertTrue(witness['local_nonexpansion_permitted'])
            self.assertFalse(any(witness['local_net_delta'].values()))
            self.assertEqual(len(set(witness['path'][:-1])), len(witness['path'])-1)

    def test_acyclic_debt_can_have_improving_headroom_cycle(self):
        result = diagnose_edges(edges([('a', 'b', -2), ('b', 'c', -2), ('c', 'a', 0)]))
        self.assertIsNone(result['positive_debt_cycle'])
        self.assertIsNone(result['admissible_debt_cycle'])
        witness = result['improving_headroom_cycle']
        self.assertEqual((witness['gross_delta'], witness['assisted_edges']), (-1, 1))
        self.assertTrue(witness['local_nonexpansion_permitted'])

    def test_global_improvement_can_violate_private_local_nonexpansion(self):
        result = diagnose_edges(edges([('a', 'b', -2), ('b', 'c', -2), ('c', 'd', -2),
                                       ('d', 'e', 0), ('e', 'a', 0)]))
        witness = result['improving_headroom_cycle']
        self.assertIsNone(result['positive_debt_cycle'])
        self.assertEqual(witness['gross_delta'], -1)
        self.assertEqual(witness['local_gross_delta']['e'], 2)
        self.assertFalse(witness['local_nonexpansion_permitted'])

    def test_topological_cycle_does_not_imply_bilateral_consent(self):
        result = diagnose_edges(edges([('a', 'b', -2), ('b', 'c', -2), ('c', 'a', -2)], prefs(auto=False)))
        self.assertIsNotNone(result['positive_debt_cycle'])
        self.assertIsNone(result['admissible_debt_cycle'])
        self.assertIsNone(result['improving_headroom_cycle'])

    def test_narrow_comfort_denies_helper_but_allows_strict_debt_reduction(self):
        policy = prefs(low=0, high=0, auto=False)
        result = diagnose_edges(edges([('a', 'b', -2), ('b', 'c', -2), ('c', 'a', 0)], policy))
        self.assertIsNone(result['improving_headroom_cycle'])
        result = diagnose_edges(edges([('a', 'b', -2), ('b', 'c', -2), ('c', 'a', -2)], policy))
        self.assertIsNotNone(result['admissible_debt_cycle'])

    def test_zero_and_single_trustline_have_no_spurious_two_node_cycle(self):
        for values in ([], [('a', 'b', 0)], [('a', 'b', -2)]):
            result = diagnose_edges(edges(values))
            self.assertIsNone(result['positive_debt_cycle'])
            self.assertIsNone(result['improving_headroom_cycle'])

    def test_nonmirrored_pending_endpoint_state_refused(self):
        balances = {'a': {'b': -2}, 'b': {'a': 1}}
        preferences = {'a': {'b': prefs()}, 'b': {'a': prefs()}}
        with self.assertRaisesRegex(ValueError, 'Non-mirrored'):
            diagnose(balances, preferences)
        with self.assertRaises(ValueError):
            diagnose_edges(edges([('a', 'b', -2), ('b', 'a', 2)]))

    def test_invalid_preferences_missing_endpoints_and_boolean_balances_refused(self):
        for balance in (True, 1.5):
            with self.assertRaises(ValueError):
                diagnose_edges(edges([('a', 'b', balance)]))
        with self.assertRaises(ValueError):
            diagnose_edges(edges([('a', 'b', -2)], prefs(low=2, high=1)))
        with self.assertRaises(ValueError):
            diagnose({'a': {'b': -2}, 'b': {}}, {'a': {'b': prefs()}, 'b': {}})
        with self.assertRaises(ValueError):
            diagnose({'a': {'b': -2}, 'b': {'a': 2}}, {'a': {}, 'b': {}})

    def test_hard_grant_prevents_headroom_assistance(self):
        result = diagnose_edges(edges([('a', 'b', -2), ('b', 'c', -2), ('c', 'a', 0)], prefs(credit=0)))
        self.assertIsNone(result['improving_headroom_cycle'])

    def test_bellman_ford_matches_exhaustive_simple_cycles_on_tiny_graphs(self):
        randomizer = random.Random(503)
        for _ in range(40):
            values = [(a, b, randomizer.randrange(-2, 3))
                      for a, b in itertools.combinations('abcde', 2) if randomizer.random() < .55]
            inputs = edges(values)
            result = diagnose_edges(inputs)
            self.assertEqual(result['improving_headroom_cycle'] is not None, exhaustive_negative(inputs))
            if result['improving_headroom_cycle'] is not None:
                self.assertLess(result['improving_headroom_cycle']['gross_delta'], 0)


if __name__ == '__main__':
    unittest.main()
