from collections import Counter
from types import SimpleNamespace
import unittest
from temporal_metrics import temporal_exposure
from temporal_sarafu import Transfer


class TemporalExposureTests(unittest.TestCase):
    def test_backlog_and_staged_commits_are_measured_separately(self):
        arrivals=[Transfer(0,0,1,10),Transfer(0,1,2,10),Transfer(0,2,0,10)]
        records=[dict(kind='transfer',time=at,source=a,target=b,delta=10)
                 for at,a,b in [(0,0,1),(0,1,2),(2,2,0)]]
        records += [dict(kind='commit',time=at,source=a,target=b,delta=-4,txid=(0,1))
                    for at,a,b in [(3,0,1),(5,1,2),(8,2,0)]]
        sim=SimpleNamespace(ledger_records=records,metrics=Counter(data_attempts=20,ack_attempts=15))
        out=temporal_exposure(sim,arrivals,6)
        self.assertEqual(out['requested_unposted_amount_ticks_to_horizon'],20)
        self.assertEqual(out['unposted_amount_at_horizon'],0)
        self.assertEqual(out['committed_edge_amount_ticks_awaiting_cycle_completion_to_horizon'],16)
        self.assertEqual(out['committed_edge_amount_ticks_awaiting_cycle_completion_through_drain'],32)
        self.assertEqual(out['committed_edge_amount_in_unfinished_cycles_at_horizon'],8)
        self.assertEqual(out['wire_attempts_data_plus_ack'],35)
        early=temporal_exposure(sim,arrivals,1)
        self.assertEqual(early['unposted_amount_at_horizon'],10)
        self.assertEqual(early['requested_unposted_amount_ticks_to_horizon'],10)

    def test_missing_or_reordered_posting_is_rejected(self):
        arrival=Transfer(2,0,1,10)
        sim=SimpleNamespace(ledger_records=[],metrics=Counter())
        with self.assertRaises(ValueError):
            temporal_exposure(sim,[arrival],5)
        sim.ledger_records=[dict(kind='transfer',time=1,source=0,target=1,delta=10)]
        with self.assertRaises(ValueError):
            temporal_exposure(sim,[arrival],5)

    def test_large_delay_has_larger_amount_weight_than_small(self):
        arrivals=[Transfer(0,0,1,1000),Transfer(0,2,3,1)]
        def measure(large_at,small_at):
            records=sorted([dict(kind='transfer',time=large_at,source=0,target=1,delta=1000),
                            dict(kind='transfer',time=small_at,source=2,target=3,delta=1)],key=lambda r:r['time'])
            return temporal_exposure(SimpleNamespace(ledger_records=records,metrics=Counter()),arrivals,10)
        self.assertEqual(measure(10,0)['requested_unposted_amount_ticks_to_horizon'],10000)
        self.assertEqual(measure(0,10)['requested_unposted_amount_ticks_to_horizon'],10)

    def test_partial_cycle_is_censored_not_falsely_completed(self):
        records=[dict(kind='commit',time=2,source=0,target=1,delta=-4,txid=(0,1)),
                 dict(kind='commit',time=5,source=1,target=2,delta=-4,txid=(0,1))]
        sim=SimpleNamespace(ledger_records=records,metrics=Counter())
        with self.assertRaises(ValueError):
            temporal_exposure(sim,[],10)
        out=temporal_exposure(sim,[],10,allow_incomplete=True)
        self.assertTrue(out['censored'])
        self.assertEqual(out['committed_edge_amount_ticks_awaiting_cycle_completion_to_horizon'],52)
        self.assertEqual(out['committed_edge_amount_in_unfinished_cycles_at_horizon'],8)
        self.assertEqual(out['peak_committed_edge_amount_in_unfinished_cycles_to_horizon'],8)
        self.assertEqual(out['net_position_gap_l1_against_posted_transfers_at_horizon'],8)

    def test_complete_same_tick_cycle_has_no_staged_area(self):
        records=[dict(kind='commit',time=2,source=a,target=b,delta=-4,txid=(0,1))
                 for a,b in [(0,1),(1,2),(2,0)]]
        out=temporal_exposure(SimpleNamespace(ledger_records=records,metrics=Counter()),[],10)
        self.assertEqual(out['committed_edge_amount_ticks_awaiting_cycle_completion_to_horizon'],0)
        self.assertEqual(out['peak_committed_edge_amount_in_unfinished_cycles_to_horizon'],0)
        self.assertEqual(out['net_position_gap_l1_against_posted_transfers_at_horizon'],0)

    def test_unposted_transfer_retains_censored_area(self):
        sim=SimpleNamespace(ledger_records=[],metrics=Counter())
        out=temporal_exposure(sim,[Transfer(2,0,1,10)],5,allow_incomplete=True)
        self.assertTrue(out['censored'])
        self.assertEqual(out['requested_unposted_amount_ticks_to_horizon'],30)
        self.assertEqual(out['unposted_amount_at_horizon'],10)

    def test_observation_clock_and_future_requests(self):
        sim=SimpleNamespace(ledger_records=[],metrics=Counter(),time=10)
        out=temporal_exposure(sim,[Transfer(0,0,1,7),Transfer(20,1,2,99)],5,allow_incomplete=True)
        self.assertEqual(out['external_posting_amount_ticks_through_drain'],70)
        self.assertEqual(out['requested_unposted_amount_ticks_to_horizon'],35)
        self.assertEqual(out['unposted_transfers_at_trace_end'],1)
        self.assertEqual(out['future_requests_beyond_observation'],1)

    def test_opposite_pending_cycles_do_not_cancel_exposure(self):
        records=[dict(kind='commit',time=2,source=0,target=1,delta=-4,txid=(0,1)),
                 dict(kind='commit',time=2,source=1,target=0,delta=-4,txid=(1,1))]
        sim=SimpleNamespace(ledger_records=records,metrics=Counter(),time=4)
        out=temporal_exposure(sim,[],4,allow_incomplete=True)
        self.assertEqual(out['net_position_gap_l1_against_posted_transfers_at_horizon'],0)
        self.assertEqual(out['committed_edge_amount_in_unfinished_cycles_at_horizon'],8)
        self.assertEqual(out['committed_edge_amount_ticks_awaiting_cycle_completion_to_horizon'],16)


if __name__=='__main__':
    unittest.main()
