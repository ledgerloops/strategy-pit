"""Independent locality and settlement checks; no benchmark performance claims."""
from collections import Counter
from pathlib import Path
import sys
import unittest

DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(DIRECTORY))
sys.path.insert(0, str(DIRECTORY.parent))

from distributed import Token
from dfs_benchmark import positions, replay
from improved_numbat import ImprovedNumbat, ObjectiveClosureNode
from ledgerloops_benchmark import JsonNumbat


class LocalDecisionContext:
    """No remote nodes, graph, global counters, or oracle are available to an actor."""
    def __init__(self):
        self.search_budget = 256
        self.time = 0
        self.metrics = Counter()
        self.sent = []

    def send(self, source, target, kind, payload):
        self.sent.append((source, target, kind, payload))

    def __getattr__(self, name):
        raise AssertionError('Actor attempted to inspect unavailable simulator state: '+name)


def token_for(path, capacities, sequence=1):
    token = Token((path[0], sequence), list(path), set(path))
    token.capacities = list(capacities)
    return token


class ObjectiveClosureTests(unittest.TestCase):
    def closure(self, path, capacities, outgoing, reservations=None):
        context = LocalDecisionContext()
        actor = ObjectiveClosureNode(path[-1], context)
        actor.outgoing.update(outgoing)
        actor.reservations.update(reservations or {})
        actor.receive('step', token_for(path, capacities))
        self.assertEqual(len(context.sent), 1)
        self.assertEqual(context.sent[0][2], 'prepare')
        return context.sent[0][3]

    def test_only_cycle_suffix_limits_amount_and_decision_needs_no_remote_state(self):
        # The small p->a prefix is not part of either cancellable cycle.
        proposal = self.closure(['p','a','b','c','d'], [1,9,9,9], {'a':9,'b':12})
        self.assertEqual(proposal.nodes, ['a','b','c','d'])
        self.assertEqual(proposal.amount, 9)

    def test_larger_bottleneck_can_outweigh_a_longer_cycle(self):
        proposal = self.closure(['a','b','c','d','e'], [2,9,9,9], {'a':2,'c':8})
        self.assertEqual(proposal.nodes, ['c','d','e'])
        self.assertEqual(proposal.amount, 8)

    def test_equal_gross_reduction_prefers_shorter_cycle(self):
        proposal = self.closure(['a','b','c','d','e'], [3,10,10,10], {'a':3,'c':5})
        self.assertEqual(proposal.nodes, ['c','d','e'])
        self.assertEqual(proposal.amount, 5)

    def test_reserved_closing_capacity_and_two_node_cycles_are_unavailable(self):
        proposal = self.closure(['a','b','c','d'], [10,10,10],
                                {'a':10,'b':4,'c':1000}, {('busy',1):('a',10)})
        self.assertEqual(proposal.nodes, ['b','c','d'])
        self.assertEqual(proposal.amount, 4)

    def test_without_a_closure_forwarding_and_random_state_match_frozen_numbat(self):
        graph = {('a','b'):5, ('b','c'):7, ('b','d'):11}
        simulations = [cls(graph, seed=17) for cls in (JsonNumbat, ImprovedNumbat)]
        for simulation in simulations:
            simulation.events.clear()
            simulation.nodes['b'].receive('step', token_for(['a','b'], [5]))
        self.assertEqual(simulations[0].events, simulations[1].events)
        self.assertEqual(simulations[0].random.getstate(), simulations[1].random.getstate())
        self.assertEqual(simulations[1].metrics['objective_closure_proposals'], 0)

    def audit_drained(self, simulation, graph):
        simulation.drain(max_events=10000)
        residual = simulation.graph_snapshot()
        self.assertEqual(residual, replay(graph, simulation.cycles))
        self.assertEqual(positions(residual), positions(graph))
        self.assertEqual(simulation.pending_reservations, 0)
        self.assertFalse(simulation.events)
        self.assertTrue(all(0 < amount <= graph[edge] for edge, amount in residual.items()))
        self.assertEqual(simulation.metrics['messages'], simulation.communication['application_deliveries'])
        self.assertTrue(all(frozenset((a,b)) in simulation.channels for _,a,b,_ in simulation.message_log))

    def test_overstated_hint_is_shrunk_by_actual_prepare_before_settlement(self):
        graph = {('a','b'):1, ('b','c'):9, ('c','a'):7}
        simulation = ImprovedNumbat(graph, seed=3, max_delay=1)
        simulation.events.clear()
        simulation.nodes['a'].active = True
        simulation.nodes['c'].receive('step', token_for(['a','b','c'], [8,9]))
        self.audit_drained(simulation, graph)
        self.assertEqual(simulation.cycles, [(['a','b','c'],1)])

    def test_competing_closures_cannot_double_spend_the_shared_edge(self):
        graph = {('a','b'):5, ('b','c'):8, ('c','a'):8, ('b','d'):9, ('d','a'):9}
        for seed in range(8):
            with self.subTest(seed=seed):
                simulation = ImprovedNumbat(graph, seed=seed, max_delay=7)
                simulation.events.clear()
                simulation.nodes['a'].active = True
                simulation.nodes['c'].receive('step', token_for(['a','b','c'], [5,8], 1))
                simulation.nodes['d'].receive('step', token_for(['a','b','d'], [5,9], 2))
                self.audit_drained(simulation, graph)
                self.assertEqual(sum(amount for _,amount in simulation.cycles), 5)
                self.assertEqual(simulation.metrics['aborted'], 1)


if __name__ == '__main__':
    unittest.main()
