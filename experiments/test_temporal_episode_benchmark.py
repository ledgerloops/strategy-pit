"""Integration checks for completed and explicitly censored benchmark rows."""
import unittest
from temporal_episode_benchmark import run_case
from temporal_sarafu import Transfer


class BenchmarkTests(unittest.TestCase):
    def test_matched_fault_triangle_audits(self):
        events=tuple(Transfer(0,a,b,1000,i) for i,(a,b) in enumerate([(0,1),(1,2),(2,0)]))
        for algorithm in ('random','numbat'):
            row=run_case(events,algorithm=algorithm,seed=0,loss=.3,sleep=True,horizon=800,event_budget=100000)
            self.assertTrue(row['complete'],row.get('error'))
            self.assertTrue(row['audit']['net_positions_preserved'])
            self.assertIn('exposure',row)
            self.assertEqual(row['pending_transfers'],0)

    def test_budget_exhaustion_not_success(self):
        events=(Transfer(0,0,1,1000,0),Transfer(1,1,2,1000,1))
        row=run_case(events,algorithm='random',seed=0,loss=.3,sleep=False,horizon=800,event_budget=1)
        self.assertFalse(row['complete'])
        self.assertIn('error',row)
        self.assertIn('exposure',row)


if __name__=='__main__':
    unittest.main()
