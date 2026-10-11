import unittest
from distributed import Token, Transaction
from temporal_episodes import EpisodeMessage
from temporal_episode_only import EpisodeOnlyTemporalProtocol
from temporal_benchmark import synthetic, audit


class EpisodeOnlyTests(unittest.TestCase):
    def setup_actor(self):
        sim=EpisodeOnlyTemporalProtocol()
        sim.stop_searches()
        for a,b in [('a','b'),('b','c'),('c','a')]:
            sim.add_transfer(a,b,5)
        sim.run(0)
        actor=sim.nodes['a']
        token=Token(('c',1),['c','a'],{'c','a'})
        token.episode_quotes={('a','b'):(actor.episodes['b'].number,actor.episodes['b'].revision)}
        tx=Transaction(token,['a','b','c'],5)
        incoming=actor.episodes['c']
        message=EpisodeMessage('c',incoming.number,incoming.revision,tx)
        sim.send=lambda *args: None
        return sim,actor,tx,message

    def test_same_episode_revision_accepts_current_capacity(self):
        sim,actor,tx,message=self.setup_actor()
        actor.episodes['c'].revision+=1
        actor.episodes['b'].revision+=1
        actor.outgoing['b']=2
        actor.receive('prepare',message)
        self.assertEqual(actor.reservations[tx.token.ident],('b',2))
        self.assertEqual(tx.amount,2)

    def test_closed_or_reopened_rejects(self):
        for reopened in (False,True):
            sim,actor,tx,message=self.setup_actor()
            actor.episodes['c'].live=reopened
            actor.episodes['c'].number+=int(reopened)
            actor.receive('prepare',message)
            self.assertFalse(actor.reservations)
            self.assertEqual(sim.metrics['stale_episode_rejections'],1)

    def test_reserved_capacity_still_aborts(self):
        sim,actor,tx,message=self.setup_actor()
        actor.reservations[('other',1)]=('b',5)
        actor.episodes['b'].revision+=1
        actor.receive('prepare',message)
        self.assertNotIn(tx.token.ident,actor.reservations)
        self.assertEqual(sim.metrics['aborted'],1)

    def test_unreserved_old_commit_rejected(self):
        sim,actor,tx,message=self.setup_actor()
        actor.receive('commit',message)
        self.assertEqual(actor.outgoing['b'],5)
        self.assertEqual(sim.metrics['unknown_control_rejections'],1)

    def test_loss_and_dynamic_reversals_audit(self):
        events=synthetic('bursts',24,101)
        for algorithm in ('random','numbat'):
            sim=EpisodeOnlyTemporalProtocol(seed=101,algorithm=algorithm,loss=.1)
            for e in events:sim.add_transfer(e.source,e.target,e.amount,at=e.time)
            sim.run(800)
            sim.drain()
            self.assertTrue(audit(sim,events,800)['valid'])


if __name__=='__main__':unittest.main()
