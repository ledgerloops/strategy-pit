import unittest
from trustlines import (Trustline, TrustlineNetwork, best_cycle_move, apply_move,
                        enumerate_cycles, optimize, CycleMove)


def ratchet():
    return TrustlineNetwork([
        Trustline('a', 'b', 0, -1, 1),
        Trustline('b', 'c', -3, -3, 3),
        Trustline('a', 'c', 3, -3, 3),
        Trustline('a', 'd', -3, -3, 3),
        Trustline('b', 'd', 3, -3, 3),
    ])


class TrustlineTests(unittest.TestCase):
    def test_view_and_bounds_are_antisymmetric(self):
        network = TrustlineNetwork([Trustline('a', 'b', 2, -3, 7)])
        self.assertEqual(network.view('b', 'a'), -2)
        self.assertEqual(network.bounds('b', 'a'), (-7, 3))
        self.assertEqual(network.positions(), {'a': 2, 'b': -2})
        self.assertEqual(network.debt(), 2)

    def test_invalid_lines_and_duplicate_endpoints(self):
        for args in [('a', 'a', 0, -1, 1), ('b', 'a', 0, -1, 1),
                     ('a', 'b', 3, -1, 1), ('a', 'b', 1, 1, 2),
                     ('a', 'b', 0.0, -1, 1), ('a', 'b', True, -1, 1)]:
            with self.assertRaises(ValueError):
                Trustline(*args)
        line = Trustline('a', 'b', 0, -1, 1)
        with self.assertRaises(ValueError):
            TrustlineNetwork([line, line])

    def test_shared_edge_ratchet_reverses_three_times(self):
        network = ratchet()
        positions = network.positions()
        bridge = [network.view('a', 'b')]
        debts = [network.debt()]
        for cycle, delta in [(('a', 'b', 'c'), 1), (('b', 'a', 'd'), 2),
                             (('a', 'b', 'c'), 2), (('b', 'a', 'd'), 1)]:
            move = best_cycle_move(network, cycle)
            self.assertEqual(move.delta, delta)
            apply_move(network, move)
            self.assertEqual(network.positions(), positions)
            self.assertLess(network.debt(), debts[-1])
            self.assertTrue(all(l.lower <= l.balance <= l.upper for l in network.lines.values()))
            bridge.append(network.view('a', 'b'))
            debts.append(network.debt())
        self.assertEqual(bridge, [0, 1, -1, 1, 0])
        self.assertEqual(debts, [12, 11, 7, 3, 0])
        self.assertEqual(len(network.lines), 5)

    def test_reverse_cycle_produces_same_final_state(self):
        first, second = ratchet(), ratchet()
        a = best_cycle_move(first, ('a', 'b', 'c'))
        b = best_cycle_move(second, ('a', 'c', 'b'))
        self.assertEqual(a.delta, -b.delta)
        apply_move(first, a)
        apply_move(second, b)
        self.assertEqual(first.lines, second.lines)

    def test_no_plateau_moves(self):
        network = TrustlineNetwork([
            Trustline('a', 'b', -3, -5, 5), Trustline('b', 'c', -3, -5, 5),
            Trustline('c', 'd', 3, -5, 5), Trustline('a', 'd', -3, -5, 5)])
        self.assertEqual(best_cycle_move(network, ('a', 'b', 'c', 'd')).delta, 0)

    def test_simple_cycles_required(self):
        for cycle in [('a', 'b'), ('a', 'b', 'a'), ('a', 'b', 'c', 'a'), ('a', 'b', 'z')]:
            with self.assertRaises(ValueError):
                best_cycle_move(ratchet(), cycle)

    def test_quote_rejects_stale_state_and_forgery(self):
        network = ratchet()
        move = best_cycle_move(network, ('a', 'b', 'c'))
        with self.assertRaises(ValueError):
            apply_move(network, CycleMove(move.cycle, 5, move.debt_before, 0, move.balances_before))
        apply_move(network, move)
        with self.assertRaises(ValueError):
            apply_move(network, move)

    def test_enumeration_deduplicates_and_reports_bounds(self):
        all_cycles = enumerate_cycles(ratchet())
        self.assertTrue(all_cycles.complete)
        self.assertEqual(len(all_cycles.cycles), 3)
        self.assertEqual(sorted(map(len, all_cycles.cycles)), [3, 3, 4])
        self.assertFalse(enumerate_cycles(ratchet(), max_length=3).complete)
        self.assertFalse(enumerate_cycles(ratchet(), max_cycles=1).complete)
        self.assertTrue(enumerate_cycles(ratchet(), max_cycles=3).complete)

    def test_optimization_and_incomplete_step_budget(self):
        for policy in ('first', 'best', 'random'):
            network = ratchet()
            original = network.copy()
            result = optimize(network, policy=policy)
            self.assertTrue(result.complete)
            self.assertEqual(result.debt_after, 0)
            self.assertEqual(original.debt(), 12)
            self.assertEqual(network.positions(), original.positions())
            for move in result.moves:
                self.assertGreater(move.reduction, 0)
        bounded = optimize(ratchet(), max_steps=0)
        self.assertFalse(bounded.complete)
        self.assertEqual(bounded.termination, 'step_bound')
        self.assertFalse(optimize(ratchet(), max_length=3).complete)

    def test_empty_and_tree_are_complete(self):
        for network in [TrustlineNetwork(), TrustlineNetwork([Trustline('a', 'b', 2, -3, 3)])]:
            before = network.debt()
            result = optimize(network)
            self.assertTrue(result.complete)
            self.assertEqual(result.debt_after, before)


if __name__ == '__main__':
    unittest.main()
