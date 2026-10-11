"""Independent economic-episode admission tests using real transfer updates."""
from collections import Counter
import random
import unittest
from distributed import Token, Transaction
from temporal_episode_only import EpisodeOnlyTemporalProtocol
from test_temporal_adversarial import NodeLocalFacade, signed_net


class EpisodeOnlyAdversarialTests(unittest.TestCase):
    def prepared_packet(self):
        sim=EpisodeOnlyTemporalProtocol(max_delay=1,retransmit=2)
        sim.stop_searches()
        for a,b in [('a','b'),('b','c'),('c','a')]:
            sim.add_transfer(a,b,5)
        sim.run(0)
        token=Token(('a',99),['a','b','c'],{'a','b','c'})
        token.episode_quotes={(a,b):(1,0) for a,b in [('a','b'),('b','c'),('c','a')]}
        tx=Transaction(token,['a','b','c'],5)
        # Route was discovered through all three actors before this delayed prepare.
        for node in sim.nodes.values():node.admitted_tokens.add(token.ident)
        sim.nodes['a'].active=True
        sim.send('c','a','prepare',tx)
        return sim

    def test_real_live_offsets_limit_old_quote_settlement(self):
        sim=self.prepared_packet()
        sim.add_transfer('b','a',3)
        sim.add_transfer('a','c',1)
        sim.run(0)
        self.assertEqual(sim.nodes['a'].episodes['b'].number,1)
        self.assertEqual(sim.nodes['a'].episodes['b'].revision,1)
        sim.drain()
        self.assertEqual(sim.graph_snapshot(),{('b','c'):3,('c','a'):2})
        self.assertEqual(sim.cycles,[(['a','b','c'],2)])
        self.assertEqual(sim.pending_reservations,0)

    def test_outgoing_reversal_and_reopening_invalidates_old_quote(self):
        for reverse in (False,True):
            sim=self.prepared_packet()
            sim.add_transfer('b','a',7 if reverse else 5)
            if not reverse:
                sim.add_transfer('a','b',5)
            sim.drain()
            self.assertFalse(sim.cycles)
            self.assertEqual(sim.metrics['stale_episode_rejections'],1)
            self.assertEqual(sim.pending_reservations,0)
            self.assertEqual(sim.nodes['a'].episodes['b'].number,2)

    def test_dynamic_loss_sleep_only_local_decisions(self):
        for algorithm in ('random','largest','numbat'):
            for seed in range(5):
                sim=EpisodeOnlyTemporalProtocol(algorithm=algorithm,seed=seed,loss=.25,ack_loss=.35,retry_interval=15)
                sim.stop_searches()
                for a in range(5):sim.add_transfer(a,(a+1)%5,5)
                sim.run(0)
                for a,node in sim.nodes.items():
                    node.sim=NodeLocalFacade(sim)
                    sim.schedule(1,a,'wake',None)
                    sim.add_sleep(a,20+a*3,45)
                sim.searches_enabled=True
                rng=random.Random(seed)
                for t in range(2,120,3):
                    a,b=rng.sample(range(5),2)
                    sim.add_transfer(a,b,rng.randrange(1,10),at=t)
                sim.run(250)
                sim.drain()
                posted=Counter()
                for _,a,b,v in sim.transfer_records:posted[a,b]+=v
                self.assertEqual(signed_net(sim.graph_snapshot()),signed_net(posted))
                self.assertEqual(sum(sim.graph_snapshot().values()),sim.metrics['added']-sim.metrics['cleared']-sim.metrics['bilateral_netting'])
                self.assertFalse(sim.pending)
                self.assertEqual(sim.pending_reservations,0)
                for node in sim.nodes.values():
                    for ep in node.episodes.values():
                        self.assertLessEqual(abs(ep.balance),ep.ceiling)
                        self.assertEqual(bool(ep.balance),ep.live)


if __name__=='__main__':unittest.main()
