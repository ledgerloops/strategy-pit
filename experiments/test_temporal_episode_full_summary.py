import unittest
from copy import deepcopy
from temporal_episode_full_summary import verify_fast_sources


class SummaryTests(unittest.TestCase):
    def test_changed_fast_adapter_cannot_reuse_gold(self):
        gold={'source_sha256':{'base.py':'base','fast_temporal_transport.py':'adapter','temporal_episode_fast_case.py':'driver'}}
        verify_fast_sources(gold,deepcopy(gold))
        for name in ('fast_temporal_transport.py','temporal_episode_fast_case.py'):
            changed=deepcopy(gold);changed['source_sha256'][name]='changed'
            with self.assertRaises(ValueError):verify_fast_sources(gold,changed)


if __name__=='__main__':unittest.main()
