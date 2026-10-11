import unittest
from distributed import Token
from temporal_rank import RankTemporalProtocol, dense_ranks
from temporal_benchmark import synthetic, audit


class RankTests(unittest.TestCase):
    def test_ties_and_amount_scale_invariance(self):
        self.assertEqual(dense_ranks({'a':1,'b':1,'c':100}),{'a':1,'b':1,'c':2})
        self.assertEqual(dense_ranks({'a':100,'b':100,'c':10000}),{'a':1,'b':1,'c':2})

    def test_heavy_neighbor_does_not_capture_all_searches(self):
        sim=RankTemporalProtocol(seed=301)
        sim.stop_searches()
        for peer,amount in [('b',1),('c',1),('d',100)]:sim.add_transfer('a',peer,amount)
        sim.run(0)
        choices=[]
        sim.send=lambda source,dest,*rest:choices.append(dest)
        for i in range(3000):sim.nodes['a'].receive('step',Token(('a',i),['a'],{'a'}))
        fraction=choices.count('d')/len(choices)
        self.assertGreater(fraction,.45)
        self.assertLess(fraction,.55)

    def test_strict_episode_and_loss_settlement_audit(self):
        events=synthetic('bursts',24,301)
        sim=RankTemporalProtocol(seed=301,loss=.3)
        sim.add_sleep(0,100,80)
        for e in events:sim.add_transfer(e.source,e.target,e.amount,at=e.time)
        sim.run(800)
        sim.drain()
        self.assertTrue(audit(sim,events,800)['valid'])
        self.assertGreater(sim.metrics['stale_episode_rejections'],0)


if __name__=='__main__':unittest.main()
