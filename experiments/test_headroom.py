import random
import unittest

from headroom import Headroom, Settlement


class LocalTransport:
    """Executable capability boundary: peers cannot inspect the simulator graph."""
    __slots__ = ('send', 'rng', 'metrics', 'records', 'search_budget', 'max_hops')

    def __init__(self, sim):
        self.send = sim.send
        self.rng = sim.rng
        self.metrics = sim.metrics
        self.search_budget = sim.search_budget
        self.max_hops = sim.max_hops

        class AppendOnlyRecords:
            def append(self, record):
                sim.records.append(record)

        self.records = AppendOnlyRecords()

    def __getattr__(self, name):
        raise AssertionError('node attempted nonlocal transport access: ' + name)


class HeadroomTests(unittest.TestCase):
    def test_recovers_greedy_dead_end(self):
        caps = {(0, 1): 1, (1, 2): 1, (2, 0): 1,
                (1, 3): 1, (3, 4): 1, (4, 0): 1}
        current = {edge: int(edge in {(1, 3), (3, 4), (4, 0)}) for edge in caps}
        sim = Headroom(caps, current)
        final = sim.run(2)
        self.assertEqual(sum(final.values()), 2)
        self.assertTrue(any(-1 in r['directions'] for r in sim.records))
        self.assertEqual(final[(1, 2)], 1)
        self.assertEqual(final[(2, 0)], 1)
        sim.audit()

    def test_alice_reallocation_with_improving_outer_loop(self):
        # First Alice->Charlie->Doris->Alice clears five. Bob->Charlie
        # supplies the additional decrease making restoration of AC worthwhile.
        caps = {('A', 'B'): 7, ('A', 'C'): 5, ('D', 'A'): 5,
                ('C', 'D'): 5, ('B', 'C'): 3}
        current = dict(caps)
        for edge in [('A', 'C'), ('D', 'A'), ('C', 'D')]:
            current[edge] = 0
        sim = Headroom(caps, current)
        result = sim.run(2)
        self.assertEqual([result[e] for e in [('A', 'B'), ('A', 'C'), ('D', 'A')]], [4, 3, 0])
        self.assertEqual(sim.initial_debt - sum(result.values()), 3)

    def test_neutral_cycle_not_accepted(self):
        sim = Headroom({('a', 'b'): 5}, search_budget=20)
        self.assertEqual(sim.run(2), {('a', 'b'): 5})
        self.assertFalse(sim.records)

    def test_worsening_reverse_cycle_not_accepted(self):
        caps = {('a', 'b'): 4, ('b', 'c'): 4, ('c', 'a'): 4}
        sim = Headroom(caps, {edge: 0 for edge in caps})
        self.assertEqual(sum(sim.run(2).values()), 0)
        self.assertFalse(sim.records)

    def test_nodes_run_without_global_graph_or_result_access(self):
        caps = {(0, 1): 1, (1, 2): 1, (2, 0): 1,
                (1, 3): 1, (3, 4): 1, (4, 0): 1}
        current = {edge: int(edge in {(1, 3), (3, 4), (4, 0)}) for edge in caps}
        sim = Headroom(caps, current)
        for node in sim.nodes.values():
            node.transport = LocalTransport(sim)
        for attribute in ('nodes', 'snapshot', 'net_positions', 'original_net', 'events'):
            with self.assertRaises(AssertionError):
                getattr(sim.nodes[0].transport, attribute)
        self.assertEqual(sum(sim.run(2).values()), 2)
        self.assertTrue(any(-1 in record['directions'] for record in sim.records))

    def test_prepare_rechecks_capacity_and_does_not_settle_early(self):
        caps = {('a', 'b'): 2, ('b', 'c'): 5, ('c', 'a'): 4}
        sim = Headroom(caps)
        tx = Settlement(['a', 'b', 'c'],
                        [('a', 'b', 1, 10), ('b', 'c', 1, 10), ('c', 'a', 1, 10)], 10)
        sim.nodes['a'].receive('c', 'prepare', tx)
        while sim.events[0][2] == 'prepare':
            sender, receiver, kind, payload = sim.events.popleft()
            sim.nodes[receiver].receive(sender, kind, payload)
        self.assertEqual(tx.amount, 2)
        self.assertEqual(sim.snapshot(), caps)
        self.assertFalse(sim.records)
        sender, receiver, kind, payload = sim.events.popleft()
        sim.nodes[receiver].receive(sender, kind, payload)
        # In-flight commit really is non-atomic: boundary audit must refuse it.
        self.assertNotEqual(sim.net_positions(sim.snapshot()), sim.original_net)
        self.assertFalse(sim.records)
        with self.assertRaisesRegex(AssertionError, 'completed settlement'):
            sim.audit()
        sim.drain()
        sim.audit()
        self.assertEqual(sim.snapshot(), {('a', 'b'): 0, ('b', 'c'): 3, ('c', 'a'): 2})
        self.assertEqual(len(sim.records), 1)
        self.assertEqual(sim.records[0]['debt_reduction'], 6)

    def test_prepare_rechecks_reverse_owner_headroom(self):
        caps = {('A', 'B'): 7, ('A', 'C'): 1, ('D', 'A'): 1,
                ('C', 'D'): 1, ('B', 'C'): 3}
        current = {edge: (value if edge in {('A', 'B'), ('B', 'C')} else 0)
                   for edge, value in caps.items()}
        sim = Headroom(caps, current)
        tx = Settlement(['C', 'A', 'B'],
                        [('C', 'A', -1, 20), ('A', 'B', 1, 20), ('B', 'C', 1, 20)], 20)
        sim.nodes['C'].receive('B', 'prepare', tx)
        sim.drain()
        sim.audit()
        self.assertEqual(tx.amount, 1)
        self.assertEqual(sim.snapshot()[('A', 'C')], 1)
        self.assertEqual(sim.records[0]['debt_reduction'], 1)

    def test_budget_exhaustion_is_not_an_optimality_certificate(self):
        sim = Headroom({('a', 'b'): 4, ('b', 'c'): 4, ('c', 'a'): 4}, search_budget=1)
        self.assertEqual(sum(sim.run(3).values()), 12)
        self.assertFalse(sim.records)
        self.assertGreater(sim.metrics['budget_exhaustions'], 0)

    def test_snapshot_validation(self):
        for values in [{('a', 'b'): 6}, {('a', 'b'): -1}, {('a', 'b'): 3}, {('a', 'c'): 1}]:
            with self.assertRaises(ValueError):
                Headroom({('a', 'b'): 5}, values)

    def test_seeded_graph_invariants_and_neighbor_messages(self):
        for seed in range(10):
            rng = random.Random(seed)
            caps = {(a, b): rng.randint(1, 9) for a in range(8) for b in range(8)
                    if a != b and rng.random() < .3}
            sim = Headroom(caps, seed=seed, search_budget=100, max_hops=8)
            sim.run(3)
            sim.audit()
            self.assertLessEqual(sum(sim.snapshot().values()), sum(caps.values()))
            self.assertEqual(sim.metrics['messages_advertise'], len(caps))
        with self.assertRaises(ValueError):
            Headroom({('a', 'b'): 1, ('c', 'd'): 1}).send('a', 'c', 'search', None)

    def test_record_replay_independently_checks_every_settlement(self):
        def net(graph, node):
            return sum(amount * ((b == node) - (a == node))
                       for (a, b), amount in graph.items())

        for seed in range(12):
            rng = random.Random(seed)
            caps = {(a, b): rng.randint(1, 5) for a in range(7) for b in range(7)
                    if a != b and rng.random() < .4}
            sim = Headroom(caps, seed=seed, search_budget=100, max_hops=7)
            for node in sim.nodes.values():
                node.transport = LocalTransport(sim)
            sim.run(3)
            replay = dict(caps)
            for record in sim.records:
                before = sum(replay.values())
                path = record['nodes']
                self.assertEqual(len(path), len(set(path)))
                for i, direction in enumerate(record['directions']):
                    a, b = path[i], path[(i + 1) % len(path)]
                    edge = (a, b) if direction == 1 else (b, a)
                    replay[edge] -= direction * record['amount']
                    self.assertTrue(0 <= replay[edge] <= caps[edge])
                actual_gain = before - sum(replay.values())
                self.assertGreater(actual_gain, 0)
                self.assertEqual(actual_gain, record['debt_reduction'])
                for node in range(7):
                    self.assertEqual(net(replay, node), net(caps, node))
            self.assertEqual(replay, sim.snapshot())


if __name__ == '__main__':
    unittest.main()
