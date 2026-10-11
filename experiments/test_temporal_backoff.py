import unittest
from distributed import Token, Transaction
from temporal_backoff import BackoffTemporalProtocol
from temporal_episodes import Episode, EpisodeMessage, EpisodeTemporalProtocol
from temporal_benchmark import synthetic, audit


class BackoffTests(unittest.TestCase):
    def actor(self):
        sim = BackoffTemporalProtocol(retry_interval=50)
        sim.searches_enabled = False
        sim.add_transfer('a', 'b', 5)
        sim.run(0)
        sim.searches_enabled = True
        actor = sim.nodes['a']
        token = Token(('c', 1), ['a','b','c'], {'a','b','c'})
        token.episode_quotes = {('a','b'): (actor.episodes['b'].number, 0)}
        tx = Transaction(token, ['a','b','c'], 5)
        return sim, actor, tx

    def test_local_reason_separates_depletion_and_reservation(self):
        sim, actor, tx = self.actor()
        self.assertEqual(actor.prepare_reason(tx), 'available')
        actor.reservations[('other',1)] = ('b',5)
        self.assertEqual(actor.prepare_reason(tx), 'reserved')
        actor.outgoing['b'] = 0
        self.assertEqual(actor.prepare_reason(tx), 'depleted')
        actor.episodes['b'].live = False
        self.assertEqual(actor.prepare_reason(tx), 'episode')

    def test_stale_packet_never_counted_as_contention(self):
        sim, actor, tx = self.actor()
        actor.reservations[('other',1)] = ('b',5)
        actor.episodes['c'] = Episode(number=2, balance=2, live=True)
        message = EpisodeMessage('c',1,0,tx)
        self.assertEqual(actor.prepare_reason(message), 'episode')

    def test_pause_affects_only_own_initiation(self):
        sim, actor, tx = self.actor()
        actor.resume_at = 200
        actor.receive('wake', None)
        self.assertFalse(actor.active)
        self.assertEqual(sim.metrics['backoff_suppressed_wakes'], 1)
        self.assertTrue(any(event[2:4] == ('a','wake') for event in sim.events))

    def test_local_failure_backoff_caps_without_global_reads(self):
        sim, actor, tx = self.actor()
        actor.reservations[('other',1)] = ('b',5)
        class Facade:
            metrics = sim.metrics
            backoff_enabled = True
            time = 7
            retry_interval = 50
            def send(self, *args):
                pass
            def __getattr__(self, name):
                raise AssertionError('Unexpected simulator access: ' + name)
        actor.sim = Facade()
        for _ in range(5):
            actor.receive('prepare', tx)
        self.assertEqual(actor.backoff_level, 3)
        self.assertEqual(actor.resume_at, 407)
        self.assertEqual(sim.metrics['prepare_local_reserved'], 5)

    def test_disabled_matches_frozen_baseline(self):
        events = synthetic('bursts',12,101)
        outputs=[]
        for cls, kwargs in ((EpisodeTemporalProtocol,{}),(BackoffTemporalProtocol,{'backoff_enabled':False})):
            sim=cls(algorithm='random',seed=101,**kwargs)
            for e in events:
                sim.add_transfer(e.source,e.target,e.amount,at=e.time)
            sim.run(800)
            sim.drain()
            self.assertTrue(audit(sim,events,800)['valid'])
            outputs.append((sim.ledger_records,sim.metrics['messages'],sim.metrics['searches']))
        self.assertEqual(outputs[0],outputs[1])

    def test_enabled_preserves_ledger_with_loss(self):
        events=synthetic('community',12,102)
        sim=BackoffTemporalProtocol(algorithm='numbat',seed=102,loss=.1)
        for e in events:
            sim.add_transfer(e.source,e.target,e.amount,at=e.time)
        sim.run(800)
        sim.drain()
        self.assertTrue(audit(sim,events,800)['valid'])
        self.assertTrue(all(0<=node.backoff_level<=3 for node in sim.nodes.values()))


if __name__=='__main__':
    unittest.main()
