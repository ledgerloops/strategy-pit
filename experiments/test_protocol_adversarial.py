"""Independent safety checks; these finite runs do not prove protocol liveness."""
import itertools
import random
import unittest

from dfs_benchmark import positions
from distributed import DistributedDFS
from simulate import Addition, aggregate, audit


class ProtocolAdversarialTests(unittest.TestCase):
    def check_drained(self, sim, additions):
        sim.drain()
        measured, residual = audit(additions, sim.cycle_records, sim.time)
        self.assertEqual(residual, sim.graph_snapshot())
        self.assertEqual(positions(aggregate(additions)), positions(residual))
        self.assertEqual(sim.pending_reservations, 0)
        self.assertFalse(any(node.active for node in sim.nodes.values()))
        self.assertEqual(sum(aggregate(additions).values()),
                         sum(residual.values()) + measured['cleared_scaled'])
        for sent_at, source, target, _ in sim.message_log:
            self.assertTrue(any(e.time <= sent_at and
                                {e.source, e.target} == {source, target}
                                for e in additions))
        return measured

    def test_overlapping_bottleneck_transactions(self):
        graph = {('a', 'b'): 9, ('b', 'c'): 8, ('c', 'a'): 8,
                 ('b', 'd'): 8, ('d', 'a'): 8,
                 ('b', 'e'): 8, ('e', 'a'): 8}
        additions = [Addition(0, a, b, amount) for (a, b), amount in graph.items()]
        for seed in range(25):
            sim = DistributedDFS(graph, seed=seed, max_delay=13, retry_interval=3)
            sim.run(800)
            measured = self.check_drained(sim, additions)
            self.assertEqual(measured['cleared_scaled'], 27, seed)

    def test_previously_dead_end_closes_after_new_neighbor_arrives(self):
        additions = [Addition(0, 'a', 'b', 10), Addition(0, 'b', 'c', 10),
                     Addition(400, 'c', 'a', 7)]
        sim = DistributedDFS({}, seed=2, retry_interval=7)
        for e in additions:
            sim.add_edge(e.source, e.target, e.amount, at=e.time)
        self.assertEqual(sim.nodes, {}, 'Future links must not register nodes early')
        sim.run(399)
        self.assertFalse(sim.cycles)
        self.assertNotIn(frozenset(('c', 'a')), sim.channels)
        sim.run(1000)
        self.assertEqual(self.check_drained(sim, additions)['cleared_scaled'], 21)

    def test_replenished_triangle_and_new_node_while_messages_fly(self):
        additions = [Addition(time, a, b, amount)
                     for time, amount in ((0, 3), (11, 9), (80, 7), (450, 4))
                     for a, b in (('a', 'b'), ('b', 'c'), ('c', 'a'))]
        additions += [Addition(14, 'c', 'new', 6), Addition(19, 'new', 'a', 6)]
        for seed in range(10):
            sim = DistributedDFS({}, seed=seed, max_delay=11, retry_interval=5)
            for e in additions:
                sim.add_edge(e.source, e.target, e.amount, at=e.time)
            sim.run(1100)
            self.check_drained(sim, additions)

    def test_inflight_commit_requires_drain_before_conservation_claim(self):
        graph = {('a', 'b'): 5, ('b', 'c'): 5, ('c', 'a'): 5}
        additions = [Addition(0, a, b, amount) for (a, b), amount in graph.items()]
        sim = DistributedDFS(graph, seed=0, max_delay=4, retry_interval=10)
        observed_partial = False
        for tick in range(100):
            sim.run(tick)
            if positions(sim.graph_snapshot()) != positions(graph):
                observed_partial = True
                break
        self.assertTrue(observed_partial)
        self.check_drained(sim, additions)

    def test_depth_limit_is_a_real_liveness_limitation(self):
        graph = {(str(a), str((a + 1) % 8)): 1 for a in range(8)}
        sim = DistributedDFS(graph, seed=1, max_hops=7, retry_interval=5)
        sim.run(200)
        sim.drain()
        self.assertEqual(sim.cycles, [])
        self.assertEqual(sim.graph_snapshot(), graph)

    def test_random_stream_safety_without_assuming_maximality(self):
        for seed in range(40):
            rng = random.Random(seed)
            additions = []
            for a, b in itertools.combinations(map(str, range(10)), 2):
                if rng.random() < .35:
                    if rng.random() < .5:
                        a, b = b, a
                    for _ in range(rng.randint(1, 3)):
                        additions.append(Addition(rng.randrange(120), a, b,
                                                  rng.randint(1, 20)))
            sim = DistributedDFS({}, seed=seed, max_delay=15, retry_interval=5,
                                 max_hops=10, search_budget=70)
            for e in additions:
                sim.add_edge(e.source, e.target, e.amount, at=e.time)
            sim.run(400)
            self.check_drained(sim, additions)


if __name__ == '__main__':
    unittest.main()
