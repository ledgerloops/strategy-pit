"""Focused ordering/locality and unchanged-protocol checks, no performance run."""
import copy
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from comfort_decrease_first import DecreaseFirstNetwork,DecreaseFirstShuffle
from comfort_headroom import Actor,Network
from test_comfort_headroom import audit,improving,terms


class DecreaseFirstTests(unittest.TestCase):
    def test_preserves_shuffle_draws_and_within_class_ties(self):
        links={peer:[balance,terms(),terms()] for peer,balance in [('a',-2),('b',3),('c',-1),('d',0),('e',-4)]}
        for seed in range(8):
            baseline_rng=random.Random(seed);candidate_rng=random.Random(seed)
            expected=list(links);actual=list(links)
            baseline_rng.shuffle(expected)
            expected.sort(key=lambda peer:abs(links[peer][0]+1)-abs(links[peer][0]))
            DecreaseFirstShuffle(candidate_rng,links).shuffle(actual)
            self.assertEqual(actual,expected)
            self.assertEqual(candidate_rng.getstate(),baseline_rng.getstate())
            self.assertEqual(set(actual[:3]),{'a','c','e'})
            self.assertEqual(set(actual[3:]),{'b','d'})

    def test_wrapper_observes_current_own_balance_without_external_state(self):
        links={'a':[-2,terms(),terms()],'b':[0,terms(),terms()]}
        wrapper=DecreaseFirstShuffle(random.Random(77),links)
        peers=['a','b'];wrapper.shuffle(peers);self.assertEqual(peers,['a','b'])
        links['a'][0]=1;links['b'][0]=-1
        peers=['a','b'];wrapper.shuffle(peers);self.assertEqual(peers,['b','a'])
        self.assertEqual(set(vars(wrapper)),{'rng','own_links'})

    def test_actor_prioritizes_debt_edge_but_keeps_helper_when_needed(self):
        sent=[];actor=Actor('a',7,lambda *args:sent.append(args),lambda *args:None)
        actor.links={'help':[0,terms(),terms()],'reduce':[-2,terms(),terms()]}
        actor.rng=DecreaseFirstShuffle(actor.rng,actor.links)
        # At a non-root node helpers are eligible; a reducing edge gets first go.
        token=dict(id='t',policy='comfort_headroom',path=['p','a'],quotes=[dict(source='p',target='a',before=-2,after=-1)],
                   visited=['p','a'],tried=[],gross_delta=-1,discovery_left=10,max_depth=4)
        actor.advance(copy.deepcopy(token))
        self.assertEqual(sent[-1][1],'reduce')
        token['tried']=[['a','reduce']]
        actor.advance(copy.deepcopy(token))
        self.assertEqual(sent[-1][1],'help')

    def test_cancellation_matches_unmodified_messages_bytes_and_economics(self):
        edges=[('a','b',-3,terms(),terms()),('b','c',-2,terms(),terms()),('c','a',-4,terms(),terms()),
               ('a','d',-2,terms(),terms()),('d','b',-1,terms(),terms())]
        for seed in range(4):
            plain=Network(edges,seed);candidate=DecreaseFirstNetwork(edges,seed)
            for net in (plain,candidate):
                net.clear('cancellation',180,max_hops=4)
                audit(edges,net)
            self.assertEqual(plain.snapshot(),candidate.snapshot())
            self.assertEqual(plain.receipts,candidate.receipts)
            self.assertEqual(plain.message_records,candidate.message_records)
            self.assertEqual(plain.score(),candidate.score())

    def test_helping_fixture_and_every_small_budget_preserve_all_invariants(self):
        edges=improving()
        for budget in range(0,61):
            net=DecreaseFirstNetwork(edges,seed=81)
            original_nets=net.nets()
            result=net.clear('comfort_headroom',budget,max_hops=3)
            self.assertLessEqual(result['used_messages'],budget)
            self.assertEqual(net.nets(),original_nets)
            self.assertLessEqual(net.score()['gross_debt'],4)
            audit(edges,net)
        net=DecreaseFirstNetwork(edges,81);net.clear('comfort_headroom',100,max_hops=3)
        self.assertEqual(net.score()['gross_debt'],2)
        self.assertEqual(net.assisted_moves,2)

    def test_arrivals_and_partial_optin_still_use_underlying_admission(self):
        edges=improving();helper=list(edges[2]);helper[3]=terms(2,False);edges[2]=tuple(helper)
        net=DecreaseFirstNetwork(edges,seed=82)
        net.clear('comfort_headroom',100,max_hops=3)
        self.assertEqual(net.moves,0)
        before=net.nets();self.assertTrue(net.transfer('a','b',1))
        self.assertEqual(net.nets()['a'],before['a']+1)
        self.assertFalse(net.transfer('a','b',100))
        self.assertFalse(any(actor.reservations for actor in net.actors.values()))


if __name__=='__main__':unittest.main()
