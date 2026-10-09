"""Focused tests of Numbat's capacity hints, which are never settlement authority."""
import math
import unittest

from distributed import Token
from numbat import Numbat
from simulate import Addition, audit


class NumbatTests(unittest.TestCase):
    def test_nonfinite_or_negative_power_rejected(self):
        for power in (-1, math.nan, math.inf, -math.inf):
            with self.subTest(power=power), self.assertRaises(ValueError):
                Numbat(capacity_power=power)

    def test_snapshot_bottleneck_limits_initial_reservation(self):
        simulation = Numbat({('a', 'b'): 2, ('b', 'c'): 9, ('c', 'a'): 7})
        token = Token(('a', 1), ['a', 'b', 'c'], {'a', 'b', 'c'})
        token.capacities = [2, 9]
        simulation.nodes['c'].receive('step', token)
        proposals = [event[4] for event in simulation.events if event[3] == 'prepare']
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].amount, 2)

    def test_stale_capacity_hint_is_revalidated(self):
        graph = {('a', 'b'): 1, ('b', 'c'): 9, ('c', 'a'): 7}
        simulation = Numbat(graph, max_delay=1)
        simulation.events.clear()  # Drive one search, with an outdated first-edge hint.
        simulation.nodes['a'].active = True
        token = Token(('a', 1), ['a', 'b', 'c'], {'a', 'b', 'c'})
        token.capacities = [2, 9]
        simulation.nodes['c'].receive('step', token)
        simulation.drain()
        self.assertEqual(simulation.cycles, [(['a', 'b', 'c'], 1)])
        additions = [Addition(0, a, b, value) for (a, b), value in graph.items()]
        _, expected = audit(additions, simulation.cycle_records, simulation.time)
        self.assertEqual(expected, simulation.graph_snapshot())
        self.assertEqual(simulation.pending_reservations, 0)

    def test_capacity_hints_not_disclosed_when_disabled(self):
        simulation = Numbat({('a', 'b'): 2, ('b', 'c'): 9, ('c', 'a'): 7},
                           snapshot_capacity=False)
        simulation.run(100)
        simulation.drain()
        self.assertEqual(simulation.metrics['message_capacity_values'], 0)


if __name__ == '__main__':
    unittest.main()
