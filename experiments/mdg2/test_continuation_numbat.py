"""Focused correctness checks; no performance campaign or parameter selection."""
import collections
import json
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from continuation_numbat import ContinuationNode, ContinuationNumbat
from distributed import Token, Transaction
from ledgerloops_benchmark import JsonNumbat, encode_payload, decode_payload


class LocalSimulation:
    time = 17
    searches_enabled = True
    search_budget = 256
    def __init__(self):
        self.metrics = collections.Counter()
        self.sent = []
    def send(self, *args):
        self.sent.append(args)


def transaction(path=('p','a','b','c'), ident=('p', 1), amount=2, hops=3):
    token = Token(ident, list(path), set(path)|{'old-dead-end'}, hops)
    token.capacities = [9, 7, 8][:len(path)-1]
    return Transaction(token, list(path[-3:]), amount, list(path[-3:]), 0)


def independent_audit(graph, simulation):
    remaining = dict(graph)
    for path, amount in simulation.cycles:
        assert len(path)>=3 and len(set(path))==len(path)
        assert type(amount) is int and amount>0
        for edge in zip(path, path[1:]+path[:1]):
            assert remaining.get(edge, 0)>=amount
            remaining[edge]-=amount
    remaining={edge:value for edge,value in remaining.items() if value}
    assert remaining==simulation.graph_snapshot()
    def positions(edges):
        result=collections.Counter()
        for (a,b),value in edges.items():
            result[a]-=value
            result[b]+=value
        return {node:value for node,value in result.items() if value}
    assert positions(graph)==positions(remaining)
    assert not simulation.events and simulation.pending_reservations==0
    assert not any(n.active for n in simulation.nodes.values())
    assert simulation.communication['data_attempts']==simulation.communication['application_deliveries']==simulation.metrics['messages']
    assert simulation.metrics['cleared']==sum(graph.values())-sum(remaining.values())


class ContinuationTests(unittest.TestCase):
    def test_prefix_caps_visited_budget_and_fresh_identity_are_local(self):
        sim=LocalSimulation();node=ContinuationNode('c',sim);node.sequence=12
        tx=transaction();node._completed_cycle=tx
        node.finish(tx.token)
        source,target,kind,new=sim.sent.pop()
        self.assertEqual((source,target,kind),('c','a','step'))
        self.assertEqual(new.path,['p','a'])
        self.assertEqual(new.capacities,[9])
        self.assertEqual(new.visited,{'p','a'})
        self.assertEqual(new.hops,6)
        self.assertEqual(new.ident,('c',13))
        self.assertEqual(node.sequence,13)
        self.assertEqual(tx.token.ident,('p',1))
        self.assertEqual(tx.token.path,['p','a','b','c'])
        self.assertEqual(tx.token.capacities,[9,7,8])
        clone=decode_payload(json.loads(json.dumps(encode_payload(new))))
        self.assertEqual(clone.__dict__,new.__dict__)

    def test_continuation_stops_at_budget_and_benchmark_admission_stop(self):
        for disabled,hops in [(True,3),(False,253)]:
            with self.subTest(disabled=disabled,hops=hops):
                sim=LocalSimulation();sim.searches_enabled=not disabled
                node=ContinuationNode('c',sim);tx=transaction(hops=hops);node._completed_cycle=tx
                node.finish(tx.token)
                self.assertEqual(sim.sent[0][:3],('c','b','finish'))
                self.assertEqual(node.sequence,0)
                self.assertEqual(sim.metrics['successful_search_continuations'],0)

    def test_abort_finish_does_not_continue(self):
        sim=LocalSimulation();node=ContinuationNode('c',sim);tx=transaction()
        node.finish(tx.token)
        self.assertEqual(sim.sent[0][:3],('c','b','finish'))
        self.assertEqual(node.sequence,0)

    def test_final_commit_precedes_continuation_and_releases_old_reservation(self):
        sim=LocalSimulation();node=ContinuationNode('c',sim)
        node.outgoing={'a':2};tx=transaction()
        node.reservations[tx.token.ident]=('a',2)
        sim.metrics['live_reservations']=1;sim.cycles=[];sim.cycle_records=[]
        node.receive('commit',tx)
        self.assertEqual(node.outgoing['a'],0)
        self.assertEqual(node.reservations,{})
        self.assertIn(('p',1),node.committed)
        self.assertEqual(sim.cycles,[(['a','b','c'],2)])
        self.assertEqual(sim.sent[0][:3],('c','a','step'))
        self.assertEqual(node.sequence,1)
        self.assertEqual(tx.token.ident,('p',1))
        self.assertIsNone(node._completed_cycle)

    def test_return_releases_original_search_root_after_ordinary_finish(self):
        graph={('p','a'):9,('a','b'):2,('b','c'):2,('c','a'):2}
        simulation=ContinuationNumbat(graph,seed=901,message_cutoff=5000,search_budget=24)
        simulation.run(200)
        simulation.drain()
        independent_audit(graph,simulation)
        self.assertGreater(simulation.metrics['successful_search_continuations'],0)
        self.assertFalse(simulation.nodes['p'].active)
        for node in simulation.nodes.values():
            self.assertLessEqual(node.sequence,simulation.metrics['searches']+simulation.metrics['successful_search_continuations'])

    def test_disabled_continuation_matches_unmodified_control_settlement(self):
        graph={('a','b'):7,('b','c'):3,('c','a'):5}
        # All 3-node cycles exceed a 3-hop continuation allowance; ordinary
        # discovery and every settlement stay exactly equal to close-first.
        args=dict(seed=903,max_delay=1,retry_interval=50,search_budget=3,max_hops=10,message_cutoff=1000,close_first=True)
        plain=JsonNumbat(graph,**args);variant=ContinuationNumbat(graph,**args)
        for sim in (plain,variant):
            sim.run(200);sim.drain();independent_audit(graph,sim)
        self.assertEqual(plain.cycles,variant.cycles)
        self.assertEqual(plain.graph_snapshot(),variant.graph_snapshot())
        self.assertEqual(plain.metrics,variant.metrics)
        self.assertEqual(plain.communication,variant.communication)

    def test_overlapping_cycles_conserve_and_drain_under_delayed_messages(self):
        graph={('a','b'):9,('b','c'):7,('c','a'):5,('b','d'):6,('d','a'):4,('c','d'):3,('d','e'):4,('e','b'):6}
        for seed in range(911,919):
            with self.subTest(seed=seed):
                sim=ContinuationNumbat(graph,seed=seed,max_delay=7,search_budget=40,message_cutoff=5000)
                sim.run(300);sim.drain();independent_audit(graph,sim)
                self.assertTrue(all(amount>0 for _,amount in sim.cycles))

    def test_message_cutoff_disables_further_continuations_and_drains(self):
        graph={('a','b'):7,('b','c'):3,('c','a'):5}
        sim=ContinuationNumbat(graph,seed=920,message_cutoff=3,max_delay=1)
        sim.run(100);sim.drain();independent_audit(graph,sim)
        self.assertEqual(sim.metrics['successful_search_continuations'],0)
        self.assertIsNotNone(sim.cutoff_tick)


if __name__=='__main__':
    unittest.main()
