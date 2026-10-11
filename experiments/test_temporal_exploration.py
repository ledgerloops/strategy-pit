import unittest

from distributed import Token
from temporal_exploration import ExplorationTemporalProtocol, TemporalExplorationNode
from temporal_benchmark import audit, synthetic
from test_temporal_adversarial import NodeLocalFacade


class FacadeExploration(ExplorationTemporalProtocol):
    def _post(self, a, b, amount, requested):
        super()._post(a, b, amount, requested)
        for name in (a, b):
            self.nodes[name].sim = NodeLocalFacade(self)


class TemporalExplorationTests(unittest.TestCase):
    def test_finish_pops_one_capacity_for_one_path_hop(self):
        sim = ExplorationTemporalProtocol({('a', 'b'): 5, ('b', 'c'): 5})
        sim.stop_searches()
        sim.run(0)
        token = Token(('a', 1), ['a', 'b', 'c'], {'a', 'b', 'c'})
        token.capacities = [5, 5]
        sim.nodes['c'].receive('finish', token)
        envelope = next(iter(sim.pending.values()))
        self.assertEqual(envelope.payload.path, ['a', 'b'])
        self.assertEqual(envelope.payload.capacities, [5])

    def test_uniform_and_weighted_branches_preserve_capacity_hints(self):
        class FixedRandom:
            def __init__(self, coin):
                self.coin = coin

            def random(self):
                coin, self.coin = self.coin, .5
                return coin

            def shuffle(self, values):
                values.reverse()

        for coin, destination, capacity in ((.1, 'c', 1), (.9, 'b', 10)):
            sim = ExplorationTemporalProtocol({('a', 'b'): 10, ('a', 'c'): 1})
            sim.stop_searches()
            sim.run(0)
            sim.random = FixedRandom(coin)
            sim.nodes['a'].receive('step', Token(('a', 1), ['a'], {'a'}))
            envelope = next(iter(sim.pending.values()))
            self.assertEqual(envelope.dest, destination)
            self.assertEqual(envelope.payload.capacities, [capacity])

    def test_new_and_reopened_endpoints_keep_variant(self):
        sim = ExplorationTemporalProtocol()
        sim.stop_searches()
        sim.add_transfer('a', 'b', 5)
        sim.run(0)
        sim.add_transfer('b', 'a', 5, at=1)
        sim.add_transfer('b', 'a', 2, at=2)
        sim.drain()
        self.assertEqual(sim.graph_snapshot(), {('b', 'a'): 2})
        self.assertTrue(all(isinstance(node, TemporalExplorationNode) for node in sim.nodes.values()))

    def test_mixture_is_local_and_independently_audits_under_loss(self):
        for seed in (101, 102):
            arrivals = synthetic('community', 12, seed)
            sim = FacadeExploration(seed=seed, loss=.3, ack_loss=.4,
                                    search_budget=64, max_hops=24)
            for event in arrivals:
                sim.add_transfer(event.source, event.target, event.amount, at=event.time)
            sim.run(0)
            for node in sim.nodes.values():
                node.sim = NodeLocalFacade(sim)
            sim.run(800)
            sim.drain()
            result = audit(sim, arrivals, 800)
            self.assertTrue(result['valid'])
            self.assertFalse(sim.pending)
            self.assertEqual(sim.pending_reservations, 0)


if __name__ == '__main__':
    unittest.main()
