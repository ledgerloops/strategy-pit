import unittest
from headroom import Settlement
from temporal_headroom import TemporalHeadroom, replay_audit


class TemporalHeadroomTests(unittest.TestCase):
    def example(self, ac):
        sim = TemporalHeadroom()
        for a, b, amount in [('A','B',7),('A','C',ac),('D','A',5),('C','D',5),('B','C',3)]:
            sim.transfer(a,b,amount)
        arcs = [('A','C',1,ac),('C','D',1,5),('D','A',1,5)]
        sim.nodes['A'].receive('D','prepare',Settlement(['A','C','D'],arcs,5))
        sim.drain()
        sim.audit()
        return sim

    def test_closed_original_blocks_restoration(self):
        sim = self.example(5)
        self.assertEqual(sim.nodes['C'].residual('A',-1),0)
        sim.search_from('C')
        self.assertEqual(sum(sim.snapshot().values()),10)
        self.assertTrue(replay_audit(sim))

    def test_live_variant_restores(self):
        sim = self.example(6)
        sim.search_from('C')
        self.assertEqual(sim.snapshot(),{('A','B'):4,('A','C'):4})
        self.assertEqual(sim.metrics['restored_volume'],3)
        self.assertTrue(replay_audit(sim))

    def test_cap_shifts_zero_and_reversal(self):
        sim = self.example(6)
        sim.transfer('A','C',3)
        self.assertEqual(sim.nodes['A'].owned['C'],[9,4])
        sim.transfer('C','A',2)
        self.assertEqual(sim.nodes['A'].owned['C'],[7,2])
        old = sim.episodes[('A','C')][0]
        sim.transfer('C','A',2)
        self.assertNotIn(('A','C'),sim.episodes)
        sim.transfer('A','C',2)
        self.assertEqual(sim.nodes['A'].owned['C'],[2,2])
        self.assertGreater(sim.episodes[('A','C')][0],old)
        sim.transfer('C','A',7)
        self.assertEqual(sim.nodes['C'].owned['A'],[5,5])
        self.assertTrue(replay_audit(sim))

    def test_no_restoration_control(self):
        sim = self.example(6)
        sim.restoration = False
        sim.search_from('C')
        self.assertEqual(sum(sim.snapshot().values()),11)
        self.assertTrue(replay_audit(sim))

    def test_reset_cap_treatment(self):
        sim = self.example(6)
        sim.reset_caps = True
        # Replay policy changed only now; previous transfers started at cap anyway.
        sim.transfer('A','C',3)
        self.assertEqual(sim.nodes['A'].owned['C'],[4,4])
        self.assertTrue(replay_audit(sim))

    def test_local_node_cannot_read_global_graph(self):
        sim = self.example(6)
        class LocalPort:
            def __getattr__(self, name):
                if name in {'send', 'rng', 'metrics', 'records', 'search_budget',
                            'max_hops', 'restoration'}:
                    return getattr(sim, name)
                raise AssertionError('nonlocal access: ' + name)
        for node in sim.nodes.values():
            node.transport = LocalPort()
        sim.search_from('C')
        self.assertEqual(sum(sim.snapshot().values()), 8)
        self.assertTrue(replay_audit(sim))

    def test_invalid_input(self):
        sim = TemporalHeadroom()
        for a,b,v in [(0,0,1),(0,1,0),(0,1,1.0)]:
            with self.assertRaises(ValueError): sim.transfer(a,b,v)

if __name__ == '__main__': unittest.main()
