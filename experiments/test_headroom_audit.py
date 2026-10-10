"""Independent Headroom replay checks and adversarial audit examples."""
import copy
import unittest

from headroom import Headroom
from headroom_benchmark import audit_records, fixtures, fixture_checks, ReductionOnlyNode


class HeadroomAuditTests(unittest.TestCase):
    def test_fixtures_match_brute_force_and_mcf(self):
        try:
            import ortools  # noqa: F401
        except ImportError:
            self.skipTest('optional MCF reference requires OR-Tools')
        results = fixture_checks()
        self.assertEqual([r['final_debt'] for r in results], [7, 2])
        self.assertEqual([r['audit']['restored_scaled'] for r in results], [3, 2])
        self.assertEqual([r['audit']['participant_exposure_increase_events'] for r in results], [0, 1])

    def test_corrupt_settlement_and_output_are_rejected(self):
        _, caps, initial = fixtures()[0]
        sim = Headroom(caps, initial)
        final = sim.run(2)
        audit_records(caps, initial, sim.records, final)
        for change in ('amount', 'debt_reduction', 'directions', 'nodes'):
            records = copy.deepcopy(sim.records)
            if change == 'amount':
                records[0]['amount'] = 100
            elif change == 'debt_reduction':
                records[0]['debt_reduction'] += 1
            elif change == 'directions':
                records[0]['directions'] = [-1] * len(records[0]['nodes'])
            else:
                records[0]['nodes'][0] = 'absent'
            with self.assertRaises(AssertionError):
                audit_records(caps, initial, records, final)
        wrong = dict(final)
        wrong['A', 'B'] -= 1
        with self.assertRaises(AssertionError):
            audit_records(caps, initial, sim.records, wrong)

    def test_pure_reduction_ablation_cannot_escape_greedy_traps(self):
        for _, caps, initial in fixtures():
            sim = Headroom(caps, initial)
            for node in sim.nodes.values():
                node.__class__ = ReductionOnlyNode
            final = sim.run(2)
            self.assertEqual(sum(final.values()), sum(initial.values()))
            self.assertEqual(sim.records, [])
            audit_records(caps, initial, sim.records, final)

    def test_neutral_or_reverse_cycles_are_rejected(self):
        caps = {('a', 'b'): 2, ('b', 'c'): 2, ('c', 'a'): 2}
        initial = dict(caps)
        neutral = {'nodes': ['a', 'b'], 'directions': [1, -1],
                   'amount': 1, 'debt_reduction': 0}
        with self.assertRaises(AssertionError):
            audit_records(caps, initial, [neutral], initial)
        increased = {edge: 1 for edge in caps}
        reverse = {'nodes': ['a', 'c', 'b'], 'directions': [-1, -1, -1],
                   'amount': 1, 'debt_reduction': -3}
        with self.assertRaises(AssertionError):
            audit_records(caps, increased, [reverse], caps)


if __name__ == '__main__':
    unittest.main()
