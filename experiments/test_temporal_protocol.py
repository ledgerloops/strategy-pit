import unittest
from temporal_protocol import TemporalProtocol


def nets(graph):
    result = {}
    for (a,b), value in graph.items():
        result[a] = result.get(a,0) - value
        result[b] = result.get(b,0) + value
    return {a:v for a,v in result.items() if v}


class TemporalTests(unittest.TestCase):
    def test_loss_sleep_and_turn_reference(self):
        for transport in ('concurrent','stop_wait'):
            sim = TemporalProtocol(seed=12, loss=.3, ack_loss=.5, transport=transport, retry_interval=30)
            sim.add_sleep('b',0,100)
            for a,b in [('a','b'),('b','c'),('c','a')]:
                sim.add_transfer(a,b,7,at=0)
            sim.run(1000)
            sim.drain()
            self.assertEqual(sim.graph_snapshot(),{})
            self.assertEqual(sim.metrics['cleared'],21)
            self.assertGreater(sim.metrics['retransmissions'],0)
            self.assertGreater(sim.metrics['duplicates_suppressed'],0)
            self.assertEqual(sim.metrics['messages'],sim.metrics['application_deliveries'])
            self.assertEqual(sim.open_channels,set())

    def test_reversal_and_reopening(self):
        sim = TemporalProtocol(seed=2)
        sim.stop_searches()
        sim.add_transfer('a','b',7)
        sim.run(0)
        sim.add_transfer('b','a',7,at=1)
        sim.run(1)
        self.assertFalse(sim.open_channels)
        sim.add_transfer('b','a',3,at=2)
        sim.drain()
        self.assertEqual(sim.graph_snapshot(),{('b','a'):3})

    def test_dynamic_net_positions(self):
        for seed in range(8):
            sim = TemporalProtocol(seed=seed,loss=.2,retry_interval=20)
            events = [(0,'a','b',10),(1,'b','c',8),(2,'c','a',6),
                      (25,'b','a',8),(30,'a','c',4),(50,'c','b',7)]
            expected = {}
            for at,a,b,value in events:
                sim.add_transfer(a,b,value,at=at)
                expected[a,b] = expected.get((a,b),0)+value
            sim.run(800)
            sim.drain()
            self.assertEqual(nets(sim.graph_snapshot()),nets(expected))
            self.assertEqual(sum(sim.graph_snapshot().values()),
                             sim.metrics['added']-sim.metrics['bilateral_netting']-sim.metrics['cleared'])

    def test_permanent_loss_is_incomplete(self):
        sim = TemporalProtocol({('a','b'):1,('b','c'):1,('c','a'):1},loss=1)
        sim.run(100)
        with self.assertRaises(RuntimeError):
            sim.drain(max_events=200)
        self.assertTrue(sim.pending)

class LocalFacade:
    def __init__(self, sim):
        self._sim = sim

    def __getattr__(self, name):
        if name in ('nodes', 'channels', 'graph_snapshot', 'open_channels', 'ledger_records'):
            raise AssertionError('Algorithm requested global graph: ' + name)
        return getattr(self._sim, name)


class FaultEveryEnvelope(TemporalProtocol):
    """First data and ACK for every logical envelope fail, then recover."""
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


class TransportAuditTests(unittest.TestCase):
    def test_every_message_lost_ack_lost_with_local_facade(self):
        for algorithm in ('numbat','random','largest'):
            sim = FaultEveryEnvelope({('a','b'):8,('b','c'):5,('c','a'):5},
                                     algorithm=algorithm,retry_interval=100,seed=8)
            sim.run(1000)
            sim.drain()
            self.assertEqual(sim.graph_snapshot(),{('a','b'):3})
            self.assertEqual(sim.metrics['data_dropped'],sim.metrics['messages'])
            self.assertEqual(sim.metrics['ack_dropped'],sim.metrics['messages'])
            self.assertEqual(sim.metrics['application_deliveries'],sim.metrics['messages'])
            self.assertGreater(sim.metrics['duplicates_suppressed'],0)
            balances = {}
            for record in sim.ledger_records:
                a,b = record['source'],record['target']
                key = tuple(sorted((a,b)))
                sign = 1 if key == (a,b) else -1
                before = balances.get(key,0)
                if record['kind'] == 'commit':
                    self.assertGreaterEqual(before * sign,-record['delta'])
                balances[key] = before + sign * record['delta']
            self.assertEqual({k:v for k,v in balances.items() if v},{('a','b'):3})


if __name__ == '__main__':
    unittest.main()
