import copy
import unittest

from temporal_benchmark import audit, run_case, synthetic
from temporal_protocol import TemporalProtocol
from temporal_sarafu import Transfer


class TemporalBenchmarkTests(unittest.TestCase):
    def settled(self):
        events = [Transfer(0,0,1,9),Transfer(1,1,2,7),Transfer(2,2,0,5),
                  Transfer(40,1,0,6),Transfer(50,0,2,3)]
        sim = TemporalProtocol(seed=4,loss=.2,ack_loss=.4,retry_interval=20)
        for e in events:
            sim.add_transfer(e.source,e.target,e.amount,at=e.time)
        sim.run(400)
        sim.drain()
        return sim,events

    def test_independent_event_replay_checks_delayed_reverse_transfers(self):
        sim,events = self.settled()
        result = audit(sim,events,400)
        self.assertTrue(result['net_positions_preserved'])
        self.assertEqual(result['final_debt_scaled'],sum(sim.graph_snapshot().values()))
        self.assertGreater(result['debt_amount_ticks_to_horizon'],0)

    def test_audit_rejects_duplicate_commit_and_future_transfer(self):
        sim,events=self.settled()
        original=copy.deepcopy(sim.ledger_records)
        commit=next(r for r in sim.ledger_records if r['kind']=='commit')
        commit['delta']=-999999
        with self.assertRaises(AssertionError):
            audit(sim,events,400)
        sim.ledger_records=original
        future=[Transfer(e.time+1000,e.source,e.target,e.amount) for e in events]
        with self.assertRaises(AssertionError):
            audit(sim,future,400)

    def test_matrix_inputs_are_repeatable_and_include_direction_reversals(self):
        for kind in ['sparse','community','bursts']:
            events=synthetic(kind,12,0)
            self.assertEqual(events,synthetic(kind,12,0))
            edges={(e.source,e.target) for e in events}
            self.assertTrue(any((b,a) in edges for a,b in edges))
            self.assertGreater(len({e.time for e in events}),1)

    def test_bounded_case_drains_and_audits_with_loss_and_sleep(self):
        result=run_case(synthetic('community',12,1),algorithm='numbat',seed=1,
                        loss=.3,sleep=True,transport='stop_wait',horizon=800)
        self.assertTrue(result['complete'],result.get('error'))
        self.assertTrue(result['audit']['all_transfers_applied'])
        self.assertEqual(result['pending_envelopes'],0)
        self.assertEqual(result['pending_reservations'],0)


if __name__=='__main__':
    unittest.main()
