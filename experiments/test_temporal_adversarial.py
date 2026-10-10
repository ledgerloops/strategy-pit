"""Adversarial transport and ledger checks, independent of benchmark auditors."""
from collections import Counter
import unittest

from distributed import Token
from temporal_protocol import TemporalProtocol


def signed_net(graph):
    net = Counter()
    for (a, b), amount in graph.items():
        net[a] -= amount
        net[b] += amount
    return {node: value for node, value in net.items() if value}


class NodeLocalFacade:
    """Allow local timing, messages and instrumentation, but no topology reads."""
    __slots__ = ('__capabilities',)
    allowed = {'time', 'searches_enabled', 'retry_interval', 'random', 'metrics',
               'schedule', 'send', 'search_budget', 'max_hops', 'policy',
               'capacity_power', 'snapshot_capacity', 'close_first',
               'cycles', 'cycle_records', 'record_ledger'}

    def __init__(self, sim):
        object.__setattr__(self, '_NodeLocalFacade__capabilities',
                           {key: (lambda key=key: getattr(sim, key)) for key in self.allowed})

    def __getattr__(self, key):
        if key not in self.allowed:
            raise AssertionError('Nonlocal node access: ' + key)
        return self.__capabilities[key]()


class DropFirstSettlementMessages(TemporalProtocol):
    def __init__(self, *args, **kwargs):
        self.forced_drops = set()
        super().__init__(*args, **kwargs)

    def _delivery(self, ident):
        envelope = self.pending.get(ident)
        if envelope and envelope.kind in {'prepare', 'commit'} and envelope.kind not in self.forced_drops:
            self.forced_drops.add(envelope.kind)
            return
        return super()._delivery(ident)


class TemporalAdversarialTests(unittest.TestCase):
    def triangle(self, cls=TemporalProtocol, **kwargs):
        sim = cls({('a', 'b'): 5, ('b', 'c'): 5, ('c', 'a'): 5},
                  algorithm='random', max_delay=1, retransmit=2, **kwargs)
        sim.stop_searches()
        sim.run(0)
        return sim

    def start_known_cycle(self, sim):
        sim.nodes['a'].active = True
        sim.nodes['c'].receive('step', Token(('a', 1), ['a', 'b', 'c'], {'a', 'b', 'c'}))

    def independently_replay(self, sim):
        graph, commit_ids = {}, set()
        for expected_order, record in enumerate(sim.ledger_records):
            self.assertEqual(record['order'], expected_order)
            a, b, delta = record['source'], record['target'], record['delta']
            if record['kind'] == 'transfer':
                value = graph.get((a, b), 0) - graph.get((b, a), 0) + delta
                graph[a, b], graph[b, a] = max(value, 0), max(-value, 0)
            else:
                self.assertEqual(record['kind'], 'commit')
                self.assertLess(delta, 0)
                key = (record['txid'], a, b)
                self.assertNotIn(key, commit_ids)
                commit_ids.add(key)
                graph[a, b] = graph.get((a, b), 0) + delta
                self.assertGreaterEqual(graph[a, b], 0)
        self.assertEqual({edge: value for edge, value in graph.items() if value}, sim.graph_snapshot())
        posted = Counter()
        for _, a, b, amount in sim.transfer_records:
            posted[a, b] += amount
        self.assertEqual(signed_net(sim.graph_snapshot()), signed_net(posted))

    def test_ack_loss_replays_closed_channel_controls_once(self):
        for transport in ('concurrent', 'stop_wait'):
            sim = self.triangle(ack_loss=1, transport=transport)
            self.start_known_cycle(sim)
            sim.run(60)
            self.assertTrue(sim.pending)
            self.assertGreater(sim.metrics['duplicates_suppressed'], 0)
            if transport == 'concurrent':
                self.assertFalse(sim.open_channels)
                self.assertEqual(sim.metrics['cleared'], 15)
                self.assertEqual(len(sim.cycles), 1)
            sim.ack_loss = 0
            sim.drain()
            self.assertEqual(sim.metrics['cleared'], 15)
            self.assertEqual(len(sim.cycles), 1)
            self.assertFalse(sim.pending)
            self.assertFalse(sim.open_channels)
            self.assertEqual(len(sim.channels), 3)  # Explicit control-traffic grace.
            self.independently_replay(sim)

    def test_lost_prepare_commit_and_sleep_eventually_finish(self):
        sim = self.triangle(cls=DropFirstSettlementMessages, ack_loss=.3, seed=8)
        sim.add_sleep('b', 1, 20)
        sim.add_sleep('b', 15, 25)
        self.assertEqual(sim.awake_at('b', 2), 40)
        self.start_known_cycle(sim)
        sim.drain()
        self.assertEqual(sim.forced_drops, {'prepare', 'commit'})
        self.assertEqual(sim.metrics['cleared'], 15)
        self.assertEqual(sim.pending_reservations, 0)
        self.assertFalse(sim.pending)
        self.assertGreater(sim.metrics['retransmissions'], 0)
        self.independently_replay(sim)

    def test_deferred_reversal_posts_between_commit_hops(self):
        sim = self.triangle()
        self.start_known_cycle(sim)
        sim.run(1)
        self.assertTrue(sim.nodes['a'].reservations)
        sim.add_transfer('b', 'a', 9)
        sim.run(1)
        self.assertEqual(sum(map(len, sim.transfer_queues.values())), 1)
        self.assertEqual(len(sim.transfer_records), 3)
        self.assertEqual(signed_net(sim.graph_snapshot()), {})
        sim.drain()
        applied = sim.transfer_records[-1][0]
        self.assertGreater(applied, 1)
        self.assertLess(applied, sim.cycle_records[0]['time'])
        self.assertEqual(sim.graph_snapshot(), {('b', 'a'): 9})
        self.assertEqual(sum(map(len, sim.transfer_queues.values())), 0)
        self.independently_replay(sim)

    def test_sleep_backlog_is_not_applied_external_debt(self):
        sim = TemporalProtocol()
        sim.stop_searches()
        sim.add_sleep('b', 0, 100)
        sim.add_transfer('a', 'b', 7, at=0)
        sim.add_transfer('b', 'a', 10, at=1)
        sim.run(50)
        self.assertEqual(sim.graph_snapshot(), {})
        self.assertEqual(sim.transfer_records, [])
        self.assertEqual(sum(map(len, sim.transfer_queues.values())), 2)
        sim.drain()
        self.assertEqual(sim.graph_snapshot(), {('b', 'a'): 3})
        self.assertEqual([r[0] for r in sim.transfer_records], [100, 100])
        self.assertEqual(sim.metrics['transfer_delay'], 199)
        self.independently_replay(sim)

    def test_nodes_do_not_access_topology_or_other_node_state(self):
        for algorithm in ('random', 'largest', 'numbat'):
            sim = TemporalProtocol({('a', 'b'): 5, ('b', 'c'): 5, ('c', 'a'): 5},
                                   algorithm=algorithm, seed=4, loss=.2, ack_loss=.3)
            sim.run(0)
            for node in sim.nodes.values():
                node.sim = NodeLocalFacade(sim)
            for forbidden in ('nodes', 'channels', 'open_channels', 'graph_snapshot', 'pending'):
                with self.assertRaises(AssertionError):
                    getattr(sim.nodes['a'].sim, forbidden)
            sim.add_sleep('b', 5, 30)
            sim.add_transfer('b', 'a', 3, at=20)
            sim.run(500)
            sim.drain()
            self.independently_replay(sim)


if __name__ == '__main__':
    unittest.main()
