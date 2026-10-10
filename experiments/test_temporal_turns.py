import unittest

from temporal_turns import TurnTemporalProtocol
from test_temporal_protocol import LocalFacade, nets


class FaultEveryTurnEnvelope(TurnTemporalProtocol):
    def _attempt(self, ident):
        env = self.pending.get(ident)
        saved = self.loss
        self.loss = float(env is not None and env.attempts == 0)
        try:
            super()._attempt(ident)
        finally:
            self.loss = saved

    def _delivery(self, ident):
        saved = self.ack_loss
        self.ack_loss = float(ident not in self.seen)
        try:
            super()._delivery(ident)
        finally:
            self.ack_loss = saved

    def _post(self, *args):
        super()._post(*args)
        for node in self.nodes.values():
            node.sim = LocalFacade(self)


class TemporalTurnsTests(unittest.TestCase):
    def test_clears_with_loss_sleep_and_all_control_accounting(self):
        for algorithm in ('numbat', 'random', 'largest'):
            sim = TurnTemporalProtocol(algorithm=algorithm, seed=12, loss=.3,
                                       ack_loss=.5, retry_interval=40, turn_batch=2)
            sim.add_sleep('b', 0, 100)
            for a, b in [('a','b'), ('b','c'), ('c','a')]:
                sim.add_transfer(a, b, 7, at=0)
            sim.run(1200)
            sim.drain()
            self.assertEqual(sim.graph_snapshot(), {})
            self.assertEqual(sim.metrics['cleared'], 21)
            self.assertGreater(sim.metrics['turn_controls'], 0)
            self.assertEqual(sim.metrics['turn_controls'],
                             sim.metrics['messages_turn_request'] + sim.metrics['messages_turn_grant'])
            self.assertEqual(sim.metrics['messages'],
                             sim.metrics['application_messages'] + sim.metrics['turn_controls'])
            self.assertGreater(sim.metrics['retransmissions'], 0)
            self.assertGreater(sim.metrics['duplicates_suppressed'], 0)

    def test_changing_graph_preserves_net_positions(self):
        for seed in range(12):
            sim = TurnTemporalProtocol(seed=seed, loss=.25, ack_loss=.35,
                                       retry_interval=25, max_delay=9)
            events = [(0,'a','b',10), (1,'b','c',8), (2,'c','a',6),
                      (25,'b','a',8), (30,'a','c',4), (50,'c','b',7)]
            expected = {}
            for at, a, b, value in events:
                sim.add_transfer(a, b, value, at=at)
                expected[a,b] = expected.get((a,b), 0) + value
            sim.add_sleep('a', 80, 75)
            sim.add_sleep('c', 90, 120)
            sim.run(1000)
            sim.drain()
            self.assertEqual(nets(sim.graph_snapshot()), nets(expected))
            self.assertEqual(sum(sim.graph_snapshot().values()),
                             sim.metrics['added'] - sim.metrics['bilateral_netting'] - sim.metrics['cleared'])
            for (node, peer), endpoint in sim.turn_endpoints.items():
                other = sim.turn_endpoints.get((peer, node))
                if other:
                    self.assertEqual(endpoint.epoch, other.epoch)
                    self.assertNotEqual(endpoint.owns_turn, other.owns_turn)

    def test_pair_state_survives_closure_and_reopening(self):
        sim = TurnTemporalProtocol(seed=3, retry_interval=20)
        for a, b in [('a','b'), ('b','c'), ('c','a')]:
            sim.add_transfer(a, b, 4)
        sim.run(500)
        sim.drain()
        self.assertEqual(sim.open_channels, set())
        identities = {key: id(endpoint) for key, endpoint in sim.turn_endpoints.items()}
        epochs = {key: endpoint.epoch for key, endpoint in sim.turn_endpoints.items()}
        # Reopening uses retained transport identities even though economic
        # balances reached zero. Searches can be restarted by local wakes.
        sim.searches_enabled = True
        for name in sim.nodes:
            sim.schedule(sim.time + 1, name, 'wake', None)
        for a, b in [('a','b'), ('b','c'), ('c','a')]:
            sim.add_transfer(a, b, 3)
        sim.run(sim.time + 500)
        sim.drain()
        self.assertEqual(sim.graph_snapshot(), {})
        self.assertEqual(sim.metrics['cleared'], 21)
        for key in identities:
            self.assertEqual(id(sim.turn_endpoints[key]), identities[key])
            self.assertGreaterEqual(sim.turn_endpoints[key].epoch, epochs[key])

    def test_every_wire_message_and_ack_lost_once_with_local_facade(self):
        sim = FaultEveryTurnEnvelope({('a','b'):8, ('b','c'):5, ('c','a'):5},
                                    retry_interval=100, seed=8)
        sim.run(1500)
        sim.drain()
        self.assertEqual(sim.graph_snapshot(), {('a','b'):3})
        self.assertEqual(sim.metrics['data_dropped'], sim.metrics['messages'])
        self.assertEqual(sim.metrics['ack_dropped'], sim.metrics['messages'])
        self.assertGreater(sim.metrics['messages_turn_request'], 0)
        self.assertGreater(sim.metrics['messages_turn_grant'], 0)
        self.assertGreater(sim.metrics['duplicates_suppressed'], 0)

    def test_permanent_loss_reports_incomplete(self):
        sim = TurnTemporalProtocol({('a','b'):1, ('b','c'):1, ('c','a'):1}, loss=1)
        sim.run(100)
        with self.assertRaises(RuntimeError):
            sim.drain(max_events=200)


if __name__ == '__main__':
    unittest.main()
