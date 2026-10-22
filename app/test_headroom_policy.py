"""Pure economic gates; network/hashlock behavior is tested separately."""
from itertools import product
import unittest

from comfort import MAX_AMOUNT
from headroom_policy import advance_surplus, edge_allowed, pair_surplus


def preferences(**overrides):
    return dict(dict(credit_limit=20, comfort_min=-20, comfort_max=20,
                     auto_adjust=True), **overrides)


def quote(peer, before, after, own=None, remote=None):
    return dict(peer=peer, before=before, after=after,
                own_preferences=preferences() if own is None else own,
                peer_preferences=preferences() if remote is None else remote)


class HeadroomPolicyTests(unittest.TestCase):
    def test_actual_finite_cost_and_zero_boundary(self):
        for before, after in ((-2, -1), (-1, 0), (0, 1), (2, 1), (1, 0), (0, -1)):
            self.assertTrue(edge_allowed(before, after, preferences(), preferences()))
            self.assertEqual(abs(abs(after)-abs(before)), abs(after-before))
        for before, after in ((-1, 1), (1, -1), (0, 0), (1, 1)):
            self.assertFalse(edge_allowed(before, after, preferences(), preferences()))

    def test_bilateral_limits_comfort_and_opt_out(self):
        self.assertFalse(edge_allowed(0, 2, preferences(credit_limit=1), preferences()))
        self.assertFalse(edge_allowed(0, -2, preferences(), preferences(credit_limit=1)))
        for endpoint in (0, 1):
            for restricted in (preferences(auto_adjust=False),
                               preferences(comfort_min=0, comfort_max=0)):
                settings = [preferences(), preferences()]
                settings[endpoint] = restricted
                self.assertFalse(edge_allowed(0, 1, *settings))
        self.assertFalse(edge_allowed(0, 1, preferences(comfort_min=1), preferences(comfort_min=1)))
        self.assertFalse(edge_allowed(0, 1, preferences(), None))

    def test_bounded_integer_inputs(self):
        for before, after in ((False, 1), (0, True), (0, 1.0), (0, MAX_AMOUNT+1)):
            self.assertFalse(edge_allowed(before, after, preferences(), preferences()))
        for amount in (True, 0, -1, 1.0, MAX_AMOUNT+1):
            with self.assertRaises(ValueError):
                advance_surplus(False, -2, amount)
        for incoming, cost, origin in ((0, 0, False), (False, False, False), (False, 1, False),
                                       (False, -2, 1)):
            with self.assertRaises(ValueError):
                advance_surplus(incoming, cost, 1, origin)

    def test_token_is_consumed_cannot_be_duplicated_and_origin_retains_gain(self):
        self.assertTrue(advance_surplus(False, -2, 1))
        self.assertTrue(advance_surplus(True, -2, 1))  # saturated, no extra token
        self.assertFalse(advance_surplus(True, 2, 1))
        with self.assertRaises(ValueError):
            advance_surplus(False, 2, 1)
        for incoming in (False, True):
            self.assertEqual(advance_surplus(incoming, 0, 1), incoming)
            self.assertFalse(advance_surplus(incoming, -2, 1, origin=True))
            for cost in (0, 2):
                with self.assertRaises(ValueError):
                    advance_surplus(incoming, cost, 1, origin=True)

    def test_pair_quotes_preserve_local_net_position_and_amount(self):
        self.assertFalse(pair_surplus([quote('a', 1, 0), quote('b', -1, 0)], 1, origin=True))
        helper = [quote('a', 0, 1), quote('b', 0, -1)]
        self.assertFalse(pair_surplus(helper, 1, incoming=True))
        with self.assertRaises(ValueError):
            pair_surplus(helper, 1)
        for changes, amount in (([quote('a', 0, 1), quote('b', 0, 1)], 1),
                                ([quote('a', 1, 0), quote('a', -1, 0)], 1),
                                ([quote('a', 1, 0), quote('b', -1, 0)], 2),
                                ([quote('a', -1, 1), quote('b', 1, -1)], 2),
                                ([{}], 1)):
            with self.assertRaises(ValueError):
                pair_surplus(changes, amount)

    def test_competing_loop_helper_can_be_supported(self):
        # Origin E retains -2; F earns surplus, A passes, D consumes, C passes.
        surplus = advance_surplus(False, -2, 1, origin=True)
        for cost in (-2, 0, 2, 0):
            surplus = advance_surplus(surplus, cost, 1)
        self.assertFalse(surplus)
        self.assertEqual(sum((-2, -2, 0, 2, 0)) // 2, -1)

    def test_all_accepted_cost_sequences_strictly_reduce_total_debt(self):
        accepted = 0
        for length in range(3, 9):
            for remaining in product((-2, 0, 2), repeat=length-1):
                surplus = False
                try:
                    for cost in remaining:
                        surplus = advance_surplus(surplus, cost, 1)
                except ValueError:
                    continue
                accepted += 1
                self.assertLess((-2+sum(remaining))/2, 0)
        self.assertGreater(accepted, 100)

    def test_sufficient_gate_is_not_complete(self):
        # Four saving vertices and two consecutive helpers have negative cost,
        # but a single surplus cannot finance both helpers without replenishment.
        remaining = (-2, -2, -2, 0, 2, 2, 0)
        self.assertLess(-2+sum(remaining), 0)
        surplus = False
        with self.assertRaises(ValueError):
            for cost in remaining:
                surplus = advance_surplus(surplus, cost, 1)


if __name__ == '__main__':
    unittest.main()
