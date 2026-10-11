"""Independent strict-episode race, loss, and boundary checks."""
from collections import Counter
import random
import unittest

from distributed import Token, Transaction
from temporal_episodes import EpisodeMessage, EpisodeTemporalProtocol
from temporal_headroom import TemporalHeadroom, replay_audit
from test_temporal_adversarial import NodeLocalFacade, signed_net


class EpisodeAdversarialTests(unittest.TestCase):
    def quiet_triangle(self, **kwargs):
        sim = EpisodeTemporalProtocol({('a','b'):6, ('b','c'):5, ('c','a'):5},
                                      max_delay=1, retransmit=2, **kwargs)
        sim.stop_searches()
        sim.run(0)
        return sim

    def cycle(self, sim):
        token = Token(('a', 91), ['a','b','c'], {'a','b','c'})
        token.episode_quotes = {(a,b):(sim.nodes[a].episodes[b].number,
                                      sim.nodes[a].episodes[b].revision)
                                for a,b in [('a','b'),('b','c'),('c','a')]}
        sim.nodes['a'].active = True
        sim.nodes['c'].receive('step', token)

    def test_unknown_completion_cannot_reserve_or_change_balance(self):
        sim = self.quiet_triangle()
        original = sim.graph_snapshot()
        token = Token(('a', 88), ['a','b','c'], {'a','b','c'})
        tx = Transaction(token,['a','b','c'],3,prepared=['a'])
        for kind,payload in [('abort',tx),('commit',tx),('finish',token)]:
            sim.nodes['a'].receive(kind, EpisodeMessage('c',1,0,payload))
        self.assertEqual(sim.graph_snapshot(),original)
        self.assertEqual(sim.pending_reservations,0)
        self.assertEqual(sim.metrics['unknown_control_rejections'],3)

    def test_reopened_incoming_prepare_rejected_even_matching_amount(self):
        sim = self.quiet_triangle()
        token = Token(('a', 89), ['a','b','c'], {'a','b','c'})
        token.episode_quotes = {('a','b'):(1,0)}
        tx = Transaction(token,['a','b','c'],1)
        sim.send('c','a','prepare',tx)
        sim.add_transfer('a','c',5)
        sim.add_transfer('c','a',5)
        sim.drain()
        self.assertEqual(sim.metrics['stale_episode_rejections'],1)
        self.assertFalse(sim.cycles)
        self.assertEqual(sim.pending_reservations,0)
        self.assertEqual(sim.nodes['a'].episodes['c'].number,2)

    def test_lost_ack_after_closure_is_receipt_not_reapplication(self):
        sim = self.quiet_triangle(ack_loss=1)
        self.cycle(sim)
        sim.run(40)
        self.assertEqual(sim.graph_snapshot(),{('a','b'):1})
        self.assertTrue(sim.pending)
        self.assertGreater(sim.metrics['duplicates_suppressed'],0)
        self.assertEqual(len(sim.cycles),1)
        sim.ack_loss=0
        sim.drain()
        self.assertEqual(len(sim.cycles),1)
        self.assertFalse(sim.pending)

    def test_reserved_pair_delays_reversal_until_its_commit(self):
        sim = self.quiet_triangle()
        self.cycle(sim)
        sim.run(1)
        self.assertTrue(sim.nodes['a'].reservations)
        sim.add_transfer('b','a',9)
        sim.run(1)
        self.assertEqual(len(sim.transfer_records),3)
        sim.drain()
        self.assertEqual(sim.graph_snapshot(),{('b','a'):8})
        self.assertEqual(sim.nodes['a'].episodes['b'].number,2)
        self.assertEqual(sim.nodes['a'].episodes['b'].ceiling,8)
        self.assertEqual(len(sim.cycles),1)
        self.assertEqual(sim.pending_reservations,0)
        self.assertGreater(sim.metrics['transfer_deferrals'],0)

    def test_local_actor_facade_randomized_transfers_and_failures(self):
        for algorithm in ('random','largest','numbat'):
            for seed in range(5):
                rng=random.Random(seed)
                sim=EpisodeTemporalProtocol(algorithm=algorithm, seed=seed,
                                            loss=.25,ack_loss=.35,retry_interval=15)
                sim.stop_searches()
                for a in range(5):
                    sim.add_transfer(a,(a+1)%5,5)
                sim.run(0)
                for node in sim.nodes.values():
                    node.sim=NodeLocalFacade(sim)
                sim.searches_enabled=True
                for a in range(5):
                    sim.schedule(1,a,'wake',None)
                    sim.add_sleep(a,25+a*7,35)
                for at in range(2,120,3):
                    a,b=rng.sample(range(5),2)
                    sim.add_transfer(a,b,rng.randrange(1,9),at=at)
                sim.run(250)
                sim.drain()
                posted=Counter()
                for _,a,b,v in sim.transfer_records:
                    posted[a,b]+=v
                self.assertEqual(signed_net(sim.graph_snapshot()),signed_net(posted))
                self.assertEqual(sum(sim.graph_snapshot().values()),sim.metrics['added']-
                                 sim.metrics['bilateral_netting']-sim.metrics['cleared'])
                self.assertFalse(sim.pending)
                self.assertEqual(sim.pending_reservations,0)
                for a,node in sim.nodes.items():
                    for b,ep in node.episodes.items():
                        opposite=sim.nodes[b].episodes[a]
                        self.assertEqual(ep.number,opposite.number)
                        self.assertEqual(ep.revision,opposite.revision)
                        self.assertEqual(ep.balance,-opposite.balance)
                        self.assertEqual(ep.live,bool(ep.balance))
                        self.assertLessEqual(abs(ep.balance),ep.ceiling)

    def test_headroom_live_shift_then_reversal_discards_permission(self):
        sim=TemporalHeadroom()
        for a,b,v in [('a','b',10),('b','c',6),('c','a',6)]:
            sim.transfer(a,b,v)
        sim.search_from('a')
        self.assertEqual(sim.nodes['a'].owned['b'],[10,4])
        sim.transfer('a','b',3)
        self.assertEqual(sim.nodes['a'].owned['b'],[13,7])
        sim.transfer('b','a',5)
        self.assertEqual(sim.nodes['a'].owned['b'],[8,2])
        sim.transfer('b','a',7)
        self.assertEqual(sim.nodes['b'].owned['a'],[5,5])
        self.assertNotIn('b',sim.nodes['a'].owned)
        self.assertEqual(sim.generations[('a','b')],2)
        self.assertTrue(replay_audit(sim))

    def test_headroom_randomized_replay_with_live_and_closed_relations(self):
        for seed in range(10):
            rng=random.Random(seed)
            sim=TemporalHeadroom(seed=seed,search_budget=25)
            for time in range(80):
                a,b=rng.sample(range(6),2)
                sim.transfer(a,b,rng.randrange(1,12),time)
                sim.search_from(rng.randrange(6))
                self.assertTrue(replay_audit(sim))


if __name__ == '__main__':
    unittest.main()
