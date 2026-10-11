import unittest
from distributed import Token, Transaction
from temporal_episodes import EpisodeTemporalProtocol, EpisodeMessage


class EpisodesTest(unittest.TestCase):
    def quiet(self, **kwargs):
        sim = EpisodeTemporalProtocol(**kwargs)
        sim.stop_searches()
        return sim

    def test_close_reopen_and_reverse(self):
        sim = self.quiet()
        for a,b,v in [('a','b',7),('b','a',7),('a','b',3),('b','a',5)]:
            sim.add_transfer(a,b,v)
            sim.drain()
        ep = sim.nodes['a'].episodes['b']
        self.assertEqual((ep.number, ep.balance, ep.ceiling), (3,-2,2))
        self.assertEqual(sim.metrics['episode_closures'],2)
        self.assertEqual(sim.metrics['episode_reopenings'],2)

    def test_stale_step_does_not_search_reopened_pair(self):
        sim = self.quiet()
        sim.add_transfer('a','b',5)
        sim.drain()
        token = Token(('a',99), ['a','b'], {'a','b'})
        sim.send('a','b','step',token)
        sim.add_transfer('b','a',5)
        sim.add_transfer('a','b',5)
        sim.drain()
        self.assertEqual(sim.metrics['stale_episode_rejections'],1)
        self.assertEqual(sim.metrics['proposals'],0)

    def test_unknown_commit_cannot_use_reopened_capacity(self):
        sim = self.quiet()
        sim.add_transfer('a','b',5)
        sim.drain()
        tx = Transaction(Token(('z',1),['a','b','c'],{'a','b','c'}),['a','b','c'],3)
        sim.nodes['a'].receive('commit',EpisodeMessage('b',1,0,tx))
        self.assertEqual(sim.graph_snapshot(),{('a','b'):5})
        self.assertEqual(sim.metrics['unknown_control_rejections'],1)

    def test_stale_outgoing_prepare_quote_rejected(self):
        sim = self.quiet()
        for a,b in [('a','b'),('b','c'),('c','a')]:
            sim.add_transfer(a,b,5)
        sim.drain()
        token = Token(('c',99),['a','b','c'],{'a','b','c'})
        token.episode_quotes = {('a','b'):(0,0)}
        tx = Transaction(token,['a','b','c'],3)
        sim.nodes['a'].receive('prepare',EpisodeMessage('c',1,0,tx))
        sim.drain()
        self.assertEqual(sim.metrics['stale_episode_rejections'],1)
        self.assertEqual(sim.pending_reservations,0)

    def test_stale_revision_step_is_cancelled(self):
        sim = self.quiet()
        sim.add_transfer('a','b',5)
        sim.drain()
        token = Token(('a',42),['a','b'],{'a','b'})
        sim.send('a','b','step',token)
        sim.add_transfer('a','b',1)
        sim.drain()
        self.assertEqual(sim.metrics['stale_episode_rejections'],1)

    def test_duplicate_applied_commit_only_receipt(self):
        sim = self.quiet()
        sim.add_transfer('a','b',5)
        sim.drain()
        tx = Transaction(Token(('z',1),['a','b','c'],{'a','b','c'}),['a','b','c'],3)
        sim.nodes['a'].committed.add(tx.token.ident)
        before = sim.metrics['messages']
        sim.nodes['a'].receive('commit',EpisodeMessage('b',0,0,tx))
        self.assertEqual(sim.metrics['messages'],before)
        self.assertEqual(sim.metrics['duplicate_commit_receipts'],1)
        self.assertEqual(sim.graph_snapshot(),{('a','b'):5})

    def test_loss_sleep_and_conservation(self):
        for algorithm in ('random','largest','numbat'):
            sim = EpisodeTemporalProtocol(algorithm=algorithm,loss=.3,ack_loss=.4,seed=7,retry_interval=20)
            for a,b in [('a','b'),('b','c'),('c','a')]:
                sim.add_transfer(a,b,5)
            sim.add_sleep('b',20,50)
            sim.add_transfer('a','b',2,at=30)
            sim.run(300)
            sim.drain()
            self.assertEqual(sim.graph_snapshot(),{('a','b'):2})
            self.assertEqual(sim.pending_reservations,0)
            self.assertFalse(sim.pending)
            self.assertTrue(sim.metrics['retransmissions'])
            for node in sim.nodes.values():
                for peer, ep in node.episodes.items():
                    self.assertLessEqual(abs(ep.balance),ep.ceiling)
                    self.assertEqual(ep.live, bool(ep.balance))

    def test_clearing_preserves_cap_until_zero(self):
        sim = EpisodeTemporalProtocol(seed=1,retry_interval=10)
        for a,b,v in [('a','b',6),('b','c',5),('c','a',5)]:
            sim.add_transfer(a,b,v)
        sim.run(150)
        sim.drain()
        ep = sim.nodes['a'].episodes['b']
        self.assertEqual((ep.balance,ep.ceiling,ep.live),(1,6,True))
        sim.add_transfer('b','a',1)
        sim.drain()
        self.assertEqual(sim.nodes['a'].episodes['b'].ceiling,0)

if __name__ == '__main__':
    unittest.main()
