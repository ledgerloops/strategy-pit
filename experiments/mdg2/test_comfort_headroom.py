"""Independent economics and hard-budget checks, not a performance campaign."""
import copy
import collections
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from comfort_headroom import Actor,Network,digest_transaction


def terms(width=3,auto=True,limit=30):
    return dict(credit_limit=limit,comfort_min=-width,comfort_max=width,auto_adjust=auto)


def improving():
    return [('a','b',-2,terms(0),terms(0)),('b','c',-2,terms(0),terms(0)),('c','a',0,terms(2),terms(2))]


def audit(edges,net):
    replay={(a,b):balance for a,b,balance,_,_ in edges}
    for receipt in net.receipts:
        deltas=collections.Counter();gross=0
        assert len(receipt['path'])>=3 and len(set(receipt['path']))==len(receipt['path'])
        for a,b,old,new in receipt['changes']:
            key=(a,b) if (a,b) in replay else (b,a)
            sign=1 if key==(a,b) else -1
            assert old==sign*replay[key] and new==old+1
            replay[key]=sign*new
            deltas[a]+=1;deltas[b]-=1;gross+=abs(new)-abs(old)
        assert all(value==0 for value in deltas.values())
        assert gross<0 and gross==receipt['gross_delta']
    assert replay=={(e['source'],e['target']):e['balance'] for e in net.snapshot()}
    assert net.messages==net.delivered==len(net.message_records)
    assert net.message_bytes==sum(m['bytes'] for m in net.message_records)==sum(net.bytes_by_kind.values())
    assert net.messages==sum(net.by_kind.values())
    assert not net.queue and not any(a.reservations for a in net.actors.values())
    for a,actor in net.actors.items():
        for b,(balance,own,peer) in actor.links.items():
            assert balance==-net.actors[b].links[a][0]
            assert -peer['credit_limit']<=balance<=own['credit_limit']


class ComfortHeadroomTests(unittest.TestCase):
    def test_headroom_reduces_gross_with_helper_while_cancellation_is_stuck(self):
        edges=improving();plain=Network(edges);helped=Network(edges)
        expected=helped.nets()
        plain.clear('cancellation',100,max_hops=3)
        helped.clear('comfort_headroom',100,max_hops=3)
        self.assertEqual(plain.score()['gross_debt'],4)
        self.assertEqual(helped.score()['gross_debt'],2)
        self.assertEqual(helped.score()['discomfort'],0)
        self.assertEqual(helped.assisted_moves,2)
        self.assertEqual(helped.nets(),expected)
        audit(edges,plain);audit(edges,helped)
        # Every completed triangle has one lap each of admission, commit, cleanup.
        self.assertEqual(sum(helped.by_kind[k] for k in ('prepare','ready')),3*helped.moves)
        self.assertEqual(sum(helped.by_kind[k] for k in ('commit','committed')),3*helped.moves)
        self.assertEqual(sum(helped.by_kind[k] for k in ('cleanup','done')),3*helped.moves)

    def test_classic_discomfort_only_move_is_rejected_when_gross_increases(self):
        edges=improving();edges[1]=('b','c',0,terms(2),terms(2))
        net=Network(edges);net.clear('comfort_headroom',150,max_hops=3)
        self.assertEqual(net.moves,0);self.assertEqual(net.score()['gross_debt'],2)
        self.assertEqual(net.score()['discomfort'],2);audit(edges,net)

    def test_root_does_not_require_strict_discomfort_improvement(self):
        edges=[('a','b',-2,terms(4),terms(4)),('b','c',-2,terms(4),terms(4)),('c','a',0,terms(4),terms(4))]
        net=Network(edges);self.assertEqual(net.score()['discomfort'],0)
        net.clear('comfort_headroom',150,max_hops=3)
        self.assertGreater(net.moves,0);self.assertLess(net.score()['gross_debt'],4);audit(edges,net)

    def test_helper_needs_both_optins_and_must_stay_inside_shared_comfort(self):
        for side in (3,4):
            edges=improving();helper=list(edges[2]);helper[side]=terms(2,False);edges[2]=tuple(helper)
            net=Network(edges);net.clear('comfort_headroom',150,max_hops=3)
            self.assertEqual(net.moves,0);audit(edges,net)
        edges=improving();edges[2]=('c','a',0,terms(0),terms(0))
        net=Network(edges);net.clear('comfort_headroom',150,max_hops=3)
        self.assertEqual(net.moves,0);audit(edges,net)

    def test_grants_and_no_new_contacts_for_external_arrivals(self):
        net=Network(improving());before=net.nets()
        self.assertTrue(net.transfer('a','b',3))
        after=net.nets();self.assertEqual(after['a'],before['a']+3);self.assertEqual(after['b'],before['b']-3)
        self.assertFalse(net.transfer('a','b',100))
        with self.assertRaises(ValueError):net.transfer('a','unknown',1)
        with self.assertRaises(ValueError):net.transfer('a','b',True)
        self.assertEqual(net.external,[('a','b',3)])
        self.assertEqual(net.actors['a'].links['b'][0],-net.actors['b'].links['a'][0])

    def test_all_small_budgets_finish_without_overshoot_or_reservations(self):
        for policy in ('cancellation','comfort_headroom'):
            for budget in range(0,61):
                with self.subTest(policy=policy,budget=budget):
                    edges=improving();net=Network(edges,seed=998)
                    result=net.clear(policy,budget,max_hops=3)
                    self.assertLessEqual(result['used_messages'],budget)
                    self.assertEqual(result['unused_budget'],budget-result['used_messages'])
                    audit(edges,net)

    def test_no_messages_on_zero_credit_then_more_credit_still_works(self):
        net=Network(improving());self.assertEqual(net.clear('comfort_headroom',0)['used_messages'],0)
        self.assertEqual(net.clear('comfort_headroom',5)['used_messages'],0)
        first=net.clear('comfort_headroom',20,max_hops=3)
        second=net.clear('comfort_headroom',100,max_hops=3)
        self.assertLessEqual(first['used_messages'],20);self.assertLessEqual(second['used_messages'],100)
        self.assertEqual(net.score()['gross_debt'],2)

    def test_actor_search_decision_has_only_own_links_and_received_token(self):
        sent=[];finished=[];actor=Actor('a',7,lambda *args:sent.append(args),lambda *args:finished.append(args))
        actor.links['b']=[-2,terms(),terms()]
        actor.start('x','comfort_headroom',10,3)
        self.assertEqual(sent[0][0:3],('a','b','probe'))
        self.assertNotIn('actors',vars(actor));self.assertNotIn('network',vars(actor))

    def test_stale_prepare_rejects_and_unwinds_actual_locks(self):
        edges=improving();net=Network(edges);net._limit=100
        root=net.actors['a'];token=dict(id='manual',policy='comfort_headroom',path=['a','b','c'],
            quotes=[net.actors['a'].quote('b'),net.actors['b'].quote('c'),net.actors['c'].quote('a')],gross_delta=-1,prepared=[])
        token=copy.deepcopy(token)  # Actual transport similarly isolates every received quote.
        token['digest']=digest_transaction(token)
        self.assertTrue(root.prepare_local(token));token['prepared'].append('a')
        # A stale recipient's independently held quote fails before any commit.
        net.actors['b'].links['c'][1]['auto_adjust']=False
        net._send('a','b','prepare',copy.deepcopy(token))
        while net.queue:
            import json
            w=json.loads(net.queue.popleft());net.delivered+=1
            net.actors[w['target']].receive(w['source'],w['kind'],w['payload'])
        self.assertEqual(net._result[0],'failed')
        self.assertFalse(any(a.reservations for a in net.actors.values()))
        self.assertEqual(net.snapshot(),[dict(source=a,target=b,balance=z) for a,b,z,_,_ in edges])
        self.assertGreater(net.by_kind['abort'],0)

    def test_random_small_ledgers_preserve_economics_and_budget(self):
        for seed in range(5):
            rng=random.Random(seed+1200);pairs={(i,(i+1)%6) for i in range(6)}
            for i in range(6):
                for j in range(i+1,6):
                    if (j,i) not in pairs and rng.random()<.2:pairs.add((i,j))
            edges=[(a,b,rng.randint(-3,3),terms(3),terms(3)) for a,b in sorted(pairs)]
            for policy in ('cancellation','comfort_headroom'):
                net=Network(edges,seed=seed);before=net.nets();initial=net.score()
                result=net.clear(policy,300,max_hops=6)
                self.assertEqual(net.nets(),before)
                self.assertLessEqual(net.score()['gross_debt'],initial['gross_debt'])
                self.assertLessEqual(result['used_messages'],300)
                if policy=='comfort_headroom':self.assertLessEqual(net.score()['discomfort'],initial['discomfort'])
                audit(edges,net)


if __name__=='__main__':unittest.main()
