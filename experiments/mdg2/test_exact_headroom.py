"""Exactness and budget/locality correctness, without performance workloads."""
from collections import Counter
import copy
import itertools
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from exact_headroom import ExactActor,ExactNetwork,canonical_cycle
from test_comfort_headroom import terms


def positions(ledger):
    result=Counter()
    for (a,b),value in ledger.items():result[a]+=value;result[b]-=value
    return {node:value for node,value in result.items() if value}


def exhaustive(edges):
    original={(a,b):value for a,b,value,_,_ in edges};target=positions(original);best=sum(abs(v) for v in original.values())
    ranges=[range(-peer['credit_limit'],own['credit_limit']+1) for _,_,_,own,peer in edges]
    for values in itertools.product(*ranges):
        ledger=dict(zip(original,values))
        if positions(ledger)==target:best=min(best,sum(abs(v) for v in values))
    return best


def audit(edges,network,result):
    ledger={(a,b):value for a,b,value,_,_ in edges}
    for receipt in network.receipts:
        changes=receipt['changes'];path=receipt['path'];delta=0
        assert len(path)>=3 and len(set(path))==len(path) and len(path)==len(changes)
        assert abs(changes[0][3])<abs(changes[0][2])
        before=positions(ledger)
        for a,b,old,new in changes:
            pair=(a,b) if (a,b) in ledger else (b,a);sign=1 if pair==(a,b) else -1
            assert old==sign*ledger[pair] and new==old+1
            ledger[pair]=sign*new;delta+=abs(new)-abs(old)
        assert positions(ledger)==before and delta==receipt['gross_delta']<0
    assert ledger=={(e['source'],e['target']):e['balance'] for e in network.snapshot()}
    assert network.messages==network.delivered==sum(network.by_kind.values())
    assert network.message_bytes==sum(network.bytes_by_kind.values())
    assert not network.queue and not any(a.reservations for a in network.actors.values())
    assert result['used_messages']<=result['budget'] and result['quiescent']
    assert sum(network.score()['phase_messages'].values())==network.messages
    assert sum(network.score()['phase_bytes'].values())==network.message_bytes
    assert len(network.message_records)<=network.message_sample_limit
    if result['certified']:
        potentials=result['potentials']
        for a,actor in network.actors.items():
            for b,(before,_,_) in actor.links.items():
                if actor.allowed(b,1,'comfort_headroom'):
                    cost=abs(before+1)-abs(before)
                    assert cost+potentials[a]-potentials[b]>=0
        assert result['certificate']['reported_nodes']==len(network.actors)


class ExactTests(unittest.TestCase):
    def test_negative_cycle_rotation_reduces_initiator_debt(self):
        cycle=canonical_cycle(['a','b','c'],[1,-1,-1])
        self.assertIsNotNone(cycle);self.assertLess(cycle['costs'][0],0)
        self.assertEqual(sum(cycle['costs']),-1)
        self.assertIsNone(canonical_cycle(['a','b','c'],[-1,1,1]))
        self.assertIsNone(canonical_cycle(['a','b'],[-1,-1]))

    def test_broad_helper_reaches_exhaustive_optimum_with_certificate(self):
        p=terms(3,limit=3)
        edges=[('a','b',-2,p,p),('b','c',-2,p,p),('c','a',0,p,p)]
        network=ExactNetwork(edges);result=network.clear_exact(10000)
        self.assertTrue(result['certified']);self.assertEqual(result['status'],'certified')
        self.assertEqual(network.score()['gross_debt'],exhaustive(edges))
        self.assertEqual(network.score()['gross_debt'],2)
        self.assertEqual(result['cycles'],2)
        audit(edges,network,result)
        self.assertGreater(result['setup_messages'],0)
        self.assertGreater(network.by_kind['bf_report'],0)
        self.assertGreater(network.by_kind['quote_collect'],0)
        self.assertGreater(network.by_kind['bf_certificate'],0)

    def test_narrow_certifies_admissible_stall_without_claiming_hard_optimum(self):
        p=terms(0,limit=3)
        edges=[('a','b',-2,p,p),('b','c',-2,p,p),('c','a',0,p,p)]
        network=ExactNetwork(edges);result=network.clear_exact(10000)
        self.assertTrue(result['certified']);self.assertEqual(network.score()['gross_debt'],4)
        self.assertEqual(exhaustive(edges),2)
        self.assertEqual(result['certificate_scope'],'no admissible negative unit cycle')
        audit(edges,network,result)

    def test_exhaustive_four_node_static_graphs_match_all_integer_optima(self):
        p=terms(2,limit=2);pairs=[('a','b'),('b','c'),('c','d'),('d','a'),('a','c')]
        for seed in range(6):
            rng=random.Random(7100+seed)
            edges=[(a,b,rng.randint(-2,2),p,p) for a,b in pairs]
            with self.subTest(seed=seed):
                network=ExactNetwork(edges);result=network.clear_exact(20000)
                self.assertTrue(result['certified'])
                self.assertEqual(network.score()['gross_debt'],exhaustive(edges))
                audit(edges,network,result)

    def test_all_small_message_caps_leave_valid_partial_ledgers(self):
        p=terms(3,limit=3);edges=[('a','b',-2,p,p),('b','c',-2,p,p),('c','a',0,p,p)]
        for cap in range(0,151):
            with self.subTest(cap=cap):
                network=ExactNetwork(edges,message_sample_limit=8);result=network.clear_exact(cap)
                self.assertIn(result['status'],('certified','budget_exhausted'))
                self.assertEqual(result['certified'],result['status']=='certified')
                audit(edges,network,result)
                if not result['certified']:self.assertIsNone(result['certificate'])

    def test_tree_setup_reused_and_arrivals_invalidate_certificate(self):
        p=terms(4,limit=4);edges=[('a','b',-2,p,p),('b','c',-2,p,p),('c','a',0,p,p)]
        network=ExactNetwork(edges);first=network.clear_exact(10000)
        self.assertTrue(first['certified']);self.assertIsNotNone(network.last_certificate)
        self.assertTrue(network.transfer('a','b',1));self.assertIsNone(network.last_certificate)
        second=network.clear_exact(10000)
        self.assertTrue(second['certified']);self.assertEqual(second['setup_messages'],0)
        current=[(e['source'],e['target'],e['balance'],p,p) for e in network.snapshot()]
        self.assertEqual(network.score()['gross_debt'],exhaustive(current))
        self.assertTrue(all(a.distance==second['potentials'][name] for name,a in network.actors.items()))

    def test_budget_pause_then_new_epoch_can_finish_after_external_arrival(self):
        p=terms(5,limit=5);edges=[('a','b',-2,p,p),('b','c',-2,p,p),('c','a',0,p,p)]
        network=ExactNetwork(edges);first=network.clear_exact(40)
        self.assertFalse(first['certified']);self.assertTrue(first['quiescent'])
        self.assertTrue(network.transfer('a','b',-1))
        current=[(e['source'],e['target'],e['balance'],p,p) for e in network.snapshot()]
        result=network.clear_exact(10000)
        self.assertTrue(result['certified']);self.assertEqual(network.score()['gross_debt'],exhaustive(current))

    def test_partial_optin_restricts_exact_residual_graph(self):
        yes=terms(3,limit=3);no=terms(3,False,3)
        edges=[('a','b',-2,yes,yes),('b','c',-2,yes,yes),('c','a',0,yes,no)]
        network=ExactNetwork(edges);result=network.clear_exact(10000)
        self.assertTrue(result['certified']);self.assertEqual(network.moves,0)
        audit(edges,network,result)

    def test_actor_round_uses_only_links_and_received_messages(self):
        sent=[];finished=[]
        actor=ExactActor('a',7,lambda *args:sent.append(args),lambda *args:finished.append(args))
        actor.initialize_exact();actor.links['b']=[-1,terms(),terms()]
        actor.tree_seen=actor.tree_ready=True;actor.children=[]
        actor.start_round(1,1,'comfort_headroom')
        self.assertEqual(sent[0][:3],('a','b','bf_relax'))
        self.assertNotIn('actors',vars(actor));self.assertNotIn('network',vars(actor))
        actor.receive('b','bf_relax',dict(epoch=1,round=1,policy='comfort_headroom',distance=0,path=['b'],costs=[],eligible=True,cost=1))
        self.assertEqual(finished[-1][0],'bf_round')
        self.assertEqual(finished[-1][1]['report']['nodes'],1)

    def test_independent_certificate_audits_every_incidence_including_ineligible(self):
        from exact_headroom_audit import audit_certificate
        from comfort_curve_audit import initial,snapshot
        for width in (0,3):
            p=terms(width,limit=3)
            edges=[('a','b',-2,p,p),('b','c',-2,p,p),('c','a',0,p,p)]
            case=dict(nodes=['a','b','c'],edges=[dict(a=a,b=b,balance=value,own=own,peer=peer)
                                               for a,b,value,own,peer in edges])
            network=ExactNetwork(edges);result=network.clear_exact(10000)
            _,preferences=initial(case)
            certificate=audit_certificate(case,snapshot(network.snapshot()),preferences,result)
            self.assertEqual(certificate['verified_nodes'],3)
            for node in result['certificate']['nodes']:
                for arc in node['outgoing']:
                    self.assertIs(type(arc['cost']),int)
                    self.assertIs(type(arc['reduced_cost']),int)

    def test_zero_and_generous_caps_have_explicit_bounded_memory_accounting(self):
        p=terms(3,limit=3);edges=[('a','b',-2,p,p),('b','c',-2,p,p),('c','a',0,p,p)]
        network=ExactNetwork(edges,message_sample_limit=5)
        result=network.clear_exact(0);self.assertEqual(result['used_messages'],0);self.assertFalse(result['certified'])
        result=network.clear_exact(10000);self.assertTrue(result['certified'])
        self.assertEqual(len(network.message_records),5)
        self.assertTrue(network.score()['message_sample_truncated'])
        self.assertGreater(network.messages,5)


if __name__=='__main__':unittest.main()
