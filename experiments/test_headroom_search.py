import unittest

from headroom import Headroom, Token
from headroom_search import DecreaseFirstHeadroom
from headroom_benchmark import audit_records, fixtures
from test_headroom import LocalTransport
from simulate import aggregate, scenario


class DecreaseFirstTests(unittest.TestCase):
    def test_decrease_precedes_larger_restoration(self):
        caps = {('b', 'a'): 10, ('a', 'c'): 10, ('c', 'b'): 10, ('a', 'd'): 1}
        initial = {('a', 'd'): 1}
        for cls, expected in [(Headroom, 'b'), (DecreaseFirstHeadroom, 'd')]:
            sim = cls(caps, initial)
            sim.nodes['a'].receive('a', 'search', Token(['a']))
            self.assertEqual(sim.events[0][1], expected)

    def test_same_simple_cycle_result_and_message_counts(self):
        caps = {('a', 'b'): 2, ('b', 'c'): 5, ('c', 'a'): 4}
        baseline, variant = Headroom(caps), DecreaseFirstHeadroom(caps)
        self.assertEqual(baseline.run(2), variant.run(2))
        self.assertEqual(baseline.metrics, variant.metrics)

    def test_mixed_recovery_works_without_global_graph_access(self):
        for name, caps, initial in fixtures():
            sim = DecreaseFirstHeadroom(caps, initial)
            for node in sim.nodes.values():
                node.transport = LocalTransport(sim)
            final = sim.run(2)
            checked = audit_records(caps, initial, sim.records, final)
            self.assertTrue(checked['mixed_settlements'])
            self.assertEqual(sum(final.values()), 7 if name == 'alice' else 2)

    def test_training_graph_bounds_and_independent_signed_replay(self):
        for seed in (101, 102):
            for topology in ('sparse', 'dense', 'community', 'disconnected'):
                caps = aggregate(scenario(topology + '-static', seed, 24))
                sim = DecreaseFirstHeadroom(caps, seed=seed, search_budget=64)
                for node in sim.nodes.values():
                    node.transport = LocalTransport(sim)
                final = sim.run(2)
                result = audit_records(caps, caps, sim.records, final)
                self.assertTrue(result['every_balance_within_original_cap'])
                self.assertTrue(result['every_settlement_preserved_net_positions'])


if __name__ == '__main__':
    unittest.main()
