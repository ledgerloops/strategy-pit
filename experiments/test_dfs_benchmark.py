"""Independent small-graph correctness checks for the static research harness."""
import itertools
import random
import unittest

from dfs_benchmark import clear_dfs, describe, mcf_reference, positions, read_graph, replay, units


def brute_optimum(graph):
    edges = list(graph)
    best = 0
    for removed in itertools.product(*(range(graph[e] + 1) for e in edges)):
        flow = dict(zip(edges, removed))
        if not positions(flow):
            best = max(best, sum(removed))
    return best


class StaticDfsTests(unittest.TestCase):
    def test_triangle_and_capacity_boundary(self):
        graph = {('a','b'):12, ('b','c'):9, ('c','a'):6}
        for policy in ('numeric', 'relabel', 'largest', 'smallest', 'largest-relabel'):
            cycles = clear_dfs(graph, policy, 8)
            self.assertEqual(replay(graph, cycles), {('a','b'):6, ('b','c'):3})
            self.assertEqual(sum(map(lambda c:len(c[0])*c[1],cycles)),18)
            self.assertEqual(graph[('a','b')],12)

    def test_empty_and_acyclic_graph(self):
        self.assertEqual(clear_dfs({}), [])
        graph = {('a','b'):5, ('b','c'):7, ('d','b'):2}
        self.assertEqual(replay(graph, clear_dfs(graph)), graph)
        self.assertTrue(describe(graph, [])['residual_is_acyclic'])

    def test_dead_ends_are_not_counted_as_cleared(self):
        graph = {('0','1'):100, ('1','2'):100, ('3','4'):2, ('4','5'):3, ('5','3'):4}
        report = describe(graph, clear_dfs(graph))
        self.assertEqual(report['cleared_scaled'],6)
        self.assertEqual(positions(replay(graph,clear_dfs(graph))),positions(graph))

    def test_strict_solution_validation(self):
        graph = {('a','b'):5, ('b','c'):5, ('c','a'):5}
        for cycle in [(['a','b','c'],6), (['a','b','c'],0), (['a','b','c'],-1),
                      (['a','b'],1), (['a','b','c','a','b','c'],1), (['a','d','c'],1)]:
            with self.assertRaises(ValueError):
                replay(graph,[cycle])
        with self.assertRaises(ValueError):
            replay(graph,[(['a','b','c'],5),(['a','b','c'],1)])

    def test_parser_rejects_rounding_and_bad_graphs(self):
        for value in ('0', '-1', '0.0001', 'NaN', 'Infinity'):
            with self.assertRaises(ValueError): units(value)
        self.assertEqual(units('12.345'),12345)
        for text in ('a a 1', 'a b 1\nb a 1'):
            with self.assertRaises(ValueError):read_graph(text)
        self.assertEqual(read_graph('a b 1\na b 0.2'),{('a','b'):1200})

    def test_greedy_maximal_is_not_maximum(self):
        # Two cycles share 0->1. A 3-cycle clears 3; a 4-cycle clears 4.
        graph = {('0','1'):1, ('1','2'):1, ('2','0'):1,
                 ('1','3'):1, ('3','4'):1, ('4','0'):1}
        report = describe(graph,clear_dfs(graph))
        self.assertEqual(report['cleared_scaled'],3)
        self.assertTrue(report['residual_is_acyclic'])
        self.assertEqual(brute_optimum(graph),4)

    def test_random_small_graphs_are_safe_and_maximal(self):
        for seed in range(80):
            rng=random.Random(seed)
            graph={}
            for a,b in itertools.combinations(map(str,range(7)),2):
                if rng.random()<0.45:
                    edge=(a,b) if rng.random()<0.5 else (b,a)
                    graph[edge]=rng.randint(1,20)
            for policy in ('numeric','relabel','largest','smallest','largest-relabel'):
                cycles=clear_dfs(graph,policy,seed)
                report=describe(graph,cycles)
                self.assertTrue(report['residual_is_acyclic'],(seed,policy))
                self.assertEqual(positions(replay(graph,cycles)),positions(graph))
                self.assertEqual(cycles,clear_dfs(graph,policy,seed))

    def test_mcf_matches_exhaustive_integer_optimum(self):
        try:
            import ortools  # noqa: F401
        except ImportError:
            self.skipTest('Optional reference check requires OR-Tools')
        for seed in range(20):
            rng=random.Random(seed)
            graph={}
            for a,b in itertools.combinations(map(str,range(4)),2):
                if rng.random()<0.85:
                    graph[(a,b) if rng.random()<0.5 else (b,a)]=rng.randint(1,2)
            if not graph:
                continue
            report=describe(graph,mcf_reference(graph))
            self.assertEqual(report['cleared_scaled'],brute_optimum(graph),seed)
            for policy in ('numeric','largest','smallest','relabel'):
                self.assertLessEqual(describe(graph,clear_dfs(graph,policy,seed))['cleared_scaled'],report['cleared_scaled'])


if __name__ == '__main__':
    unittest.main()
