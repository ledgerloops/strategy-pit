import unittest
from copy import deepcopy
from temporal_episode_gold import verify


class GoldTests(unittest.TestCase):
    def fixture(self):
        row=dict(algorithm='random',seed=0,loss=0,sleep=False,horizon=2300,complete=True,
                 metrics={'messages':100},elapsed_seconds=1,at_horizon={'debt_scaled':42})
        report=dict(complete=True,rows=[row],fixture_metadata={'source_sha256':'fixture'},
                    selection={'first_standard_transfers':30726},source_sha256={'core.py':'source'})
        return report,deepcopy(report)

    def test_only_runtime_may_differ(self):
        old,new=self.fixture();new['rows'][0]['elapsed_seconds']=900
        self.assertTrue(verify(old,new)['equivalent'])
        new['rows'][0]['at_horizon']['debt_scaled']=43
        with self.assertRaisesRegex(ValueError,'Non-timing'):
            verify(old,new)

    def test_reference_inputs_and_sources_must_match(self):
        for part,key in [('fixture_metadata','source_sha256'),('source_sha256','core.py'),('selection','first_standard_transfers')]:
            old,new=self.fixture();new[part][key]='changed'
            with self.assertRaises(ValueError):verify(old,new)
        old,new=self.fixture();new['complete']=False
        with self.assertRaises(ValueError):verify(old,new)


if __name__=='__main__':unittest.main()
