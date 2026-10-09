"""Independent integer-state checks for the centralized trustline model."""
import itertools
import random
import unittest

from trustlines import Trustline, TrustlineNetwork, apply_move, best_cycle_move, optimize


def state_positions(edges, balances):
    """Independent incidence calculation, without the model's position helper."""
    result = {node: 0 for edge in edges for node in edge}
    for (a, b), balance in zip(edges, balances):
        result[a] += balance
        result[b] -= balance
    return result


def brute_optimum(lines):
    edges = [(line.a, line.b) for line in lines]
    target = state_positions(edges, [line.balance for line in lines])
    best = sum(abs(line.balance) for line in lines)
    for balances in itertools.product(*(range(line.lower, line.upper + 1)
                                        for line in lines)):
        cost = sum(map(abs, balances))
        if cost < best and state_positions(edges, balances) == target:
            best = cost
    return best


class TrustlineAdversarialTests(unittest.TestCase):
    def test_cycle_quote_matches_independent_integer_search(self):
        for seed in range(240):
            rng = random.Random(seed)
            cycle = list('abcdefg'[:rng.randint(3, 7)])
            rng.shuffle(cycle)
            edges = list(zip(cycle, cycle[1:] + cycle[:1]))
            lines = []
            for source, target in edges:
                lower, upper = -rng.randint(0, 5), rng.randint(0, 5)
                lines.append(Trustline(*sorted((source, target)),
                                       rng.randint(lower, upper), lower, upper))
            network = TrustlineNetwork(lines)
            signs = [1 if source < target else -1 for source, target in edges]
            candidates = []
            for delta in range(-10, 11):
                balances = [line.balance + sign * delta
                            for line, sign in zip(lines, signs)]
                if all(line.lower <= balance <= line.upper
                       for line, balance in zip(lines, balances)):
                    candidates.append((sum(map(abs, balances)), abs(delta), delta))
            expected_cost, _, expected_delta = min(candidates)
            before_positions = network.positions()
            move = best_cycle_move(network, cycle)
            self.assertEqual((move.debt_after, move.delta),
                             (expected_cost, expected_delta), seed)
            apply_move(network, move)
            self.assertEqual(network.positions(), before_positions, seed)

    def test_exhaustive_cycles_reach_brute_global_optimum(self):
        for seed in range(60):
            rng = random.Random(seed)
            lines = []
            for a, b in itertools.combinations('abcd', 2):
                if rng.random() < .15:
                    continue
                lower, upper = -rng.randint(0, 2), rng.randint(0, 2)
                lines.append(Trustline(a, b, rng.randint(lower, upper), lower, upper))
            expected = brute_optimum(lines)
            for policy in ('first', 'best'):
                network = TrustlineNetwork(lines)
                original_positions = network.positions()
                result = optimize(network, policy=policy)
                self.assertTrue(result.complete, (seed, policy))
                self.assertEqual(network.debt(), expected, (seed, policy))
                self.assertEqual(network.positions(), original_positions, (seed, policy))
                self.assertTrue(all(move.reduction > 0 for move in result.moves))

    def test_global_reduction_can_increase_one_participants_gross_exposure(self):
        network = TrustlineNetwork([
            Trustline('a', 'b', 1, -2, 2), Trustline('b', 'c', 1, -2, 2),
            Trustline('c', 'd', -3, -4, 4), Trustline('d', 'e', -3, -4, 4),
            Trustline('a', 'e', 3, -4, 4),
        ])
        before_positions = network.positions()
        before_exposure = abs(network.view('b', 'a')) + abs(network.view('b', 'c'))
        move = best_cycle_move(network, tuple('abcde'))
        self.assertEqual((move.delta, move.debt_before, move.debt_after), (1, 11, 10))
        apply_move(network, move)
        after_exposure = abs(network.view('b', 'a')) + abs(network.view('b', 'c'))
        self.assertEqual((before_exposure, after_exposure), (2, 4))
        self.assertEqual(network.positions(), before_positions)

    def test_short_cycle_search_can_stop_above_global_optimum(self):
        network = TrustlineNetwork([
            Trustline('a', 'b', -1, -1, 1), Trustline('b', 'c', -1, -1, 1),
            Trustline('c', 'd', -1, -1, 1), Trustline('a', 'd', 1, -1, 1),
        ])
        result = optimize(network, max_length=3)
        self.assertFalse(result.complete)
        self.assertEqual(network.debt(), 4)
        self.assertEqual(brute_optimum(list(network.lines.values())), 0)
        self.assertTrue(optimize(network).complete)
        self.assertEqual(network.debt(), 0)


if __name__ == '__main__':
    unittest.main()
