"""Focused correctness tests only, not performance workloads."""
import hashlib
import json
from pathlib import Path
import random
import sys
import unittest

HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0,str(HERE))
from private_stream import (PrivateStream, NonexpandingPrivateNode, RandomizedPrivateNode,
                            COMFORT_POLICY, COMFORT_SCHEME, hash_comfort_condition)
from private_stream_audit import endpoint_metrics, verify_local_receipt, check_wire
from private_stream_observer import Observer


def prefs(width=100, auto=True):
    return dict(credit_limit=100,comfort_min=-width,comfort_max=width,auto_adjust=auto)


def ring(values):
    return [(str(i),str((i+1)%len(values)),value,prefs(),prefs()) for i,value in enumerate(values)]


class PrivateStreamTests(unittest.TestCase):
    def audit_basic(self,result,edges):
        balances=json.loads(json.dumps(result['initial_balances']))
        requests={}
        approvals=set()
        receipts=[]
        neighbours={a:set(links) for a,links in balances.items()}
        self.assertEqual(result['messages'],sum(e['kind']=='request' for e in result['events']))
        self.assertEqual(result['message_bytes'],sum(e['bytes'] for e in result['events'] if e['kind']=='request'))
        self.assertEqual(result['ack_body_bytes'],sum(e['bytes'] for e in result['events'] if e['kind']=='ack_request'))
        for index,event in enumerate(result['events']):
            if event['kind']=='request':
                requests[event['attempt']]=event
                self.assertEqual(json.loads(event['raw_json']),event['payload'])
                self.assertEqual(len(event['raw_json'].encode()),event['bytes'])
                check_wire(event['source'],event['target'],event['payload'],neighbours)
            elif event['kind']=='message':
                request=requests[event['attempt']]
                self.assertEqual(request['raw_json'],event['raw_json'])
            elif event['kind']=='local_approval':
                approvals.add((event['node'],event['id'],event['digest']))
            for item in event.get('local_receipts',[]):
                receipt=item['receipt']
                verify_local_receipt(receipt)
                self.assertIn((item['node'],receipt['id'],receipt['digest']),approvals)
                receipts.append(receipt)
            for change in event.get('balance_changes',[]):
                self.assertEqual(balances[change['node']][change['peer']],change['before'])
                balances[change['node']][change['peer']]=change['after']
            point=result['trace'][index]
            self.assertEqual(point['event_end_index'],index+1)
            for key,value in endpoint_metrics(balances).items():
                if key!='original_trustlines':
                    self.assertEqual(point[key],value)
        self.assertEqual(balances,result['final_balances'])
        observer=Observer(edges)
        for event in result['events']:
            observer.observe_event(event,message_count=event['messages'])
        return observer.result(),receipts

    def test_actual_hashlock_cancellation_triangle(self):
        edges=ring([-2,-2,-2])
        with PrivateStream(edges,seed=4,discovery_until=15) as stream:
            result=stream.run(25)
            shadow,receipts=self.audit_basic(result,edges)
            self.assertTrue(receipts)
            self.assertEqual(result['final']['debt'],0)
            self.assertEqual(result['final']['mirror_mismatches'],0)
            self.assertEqual(result['final']['reservations'],0)
            self.assertEqual(shadow['final']['causal_fully_applied_gross'],0)
            self.assertEqual(result['delivery_failures'],0)
            self.assertGreater(result['ack_body_bytes'],0)
            # Default-spaced stored JSON is counted, not compact reserialization.
            request=next(e for e in result['events'] if e['kind']=='request')
            self.assertGreater(request['bytes'],len(json.dumps(request['payload'],separators=(',',':')).encode()))

    def test_private_headroom_helper_and_nonexpansion(self):
        edges=ring([-2,-2,0])
        with PrivateStream(edges,seed=7,method='private_nonexpansion',discovery_until=15) as stream:
            result=stream.run(25)
            shadow,receipts=self.audit_basic(result,edges)
            self.assertTrue(receipts)
            self.assertEqual(result['final']['debt'],2)
            self.assertEqual(result['final']['mirror_mismatches'],0)
            for receipt in receipts:
                self.assertEqual(receipt['policy'],COMFORT_POLICY)
                self.assertEqual(receipt['hashlock_scheme'],COMFORT_SCHEME)
                self.assertLessEqual(sum(abs(c['after'])-abs(c['before']) for c in receipt['changes']),0)
            self.assertEqual(shadow['final']['gross_saving'],2)

    def test_faithful_broad_comfort_has_no_origin_trigger(self):
        edges=ring([-2,-2,-2])
        with PrivateStream(edges,seed=9,method='faithful_comfort',discovery_until=8) as stream:
            result=stream.run(10)
            self.assertFalse(any(e['kind']=='discover' for e in result['events']))
            self.assertEqual(result['final']['debt'],6)
            self.assertEqual(result['messages'],12)  # 2 revisions × 2 incidences × 3 edges
            self.audit_basic(result,edges)

    def test_random_candidates_remove_lexical_starvation(self):
        edges=[('root',peer,-2,prefs(),prefs()) for peer in ('a','b','c')]
        with PrivateStream(edges,seed=1,discovery_until=0) as stream:
            stream.run(1)
            node=stream.actors['root'].node
            self.assertIsInstance(node,RandomizedPrivateNode)
            seen={node.candidate(1) for _ in range(40)}
            self.assertEqual(seen,{'a','b','c'})
            self.assertNotIn('a',{node.candidate(1,exclude='a') for _ in range(10)})
            with node.db:
                node.db.execute('INSERT INTO reservations VALUES(?,?)',('b','reserved-test'))
            self.assertEqual(node.candidate(1,exclude='a'),'c')

    def test_private_policy_incomplete_on_adjacent_helper_cycle(self):
        edges=ring([-1,-1,-1,0,0])
        with PrivateStream(edges,seed=3,method='private_nonexpansion',discovery_until=8) as stream:
            result=stream.run(15)
            self.assertTrue(any(e['kind']=='discover' for e in result['events']))
            self.assertFalse(any(e.get('local_receipts') for e in result['events']))
            self.assertEqual(result['final']['debt'],3)
            self.audit_basic(result,edges)

    def test_bilateral_arrivals_are_counted_and_actual(self):
        edges=ring([0,0,0])
        with PrivateStream(edges,seed=10,discovery_until=0) as stream:
            stream.offer(0.2,'0','1',-3,'offer-a')
            stream.offer(0.21,'0','1',2,'offer-b')
            result=stream.run(5)
            shadow,_=self.audit_basic(result,edges)
            self.assertEqual(len(result['accepted_offers']),2)
            self.assertEqual(result['pending_offers'],[])
            self.assertEqual(result['final_balances']['0']['1'],-1)
            self.assertEqual(result['final_balances']['1']['0'],1)
            self.assertEqual(result['message_kinds']['obligation_offer'],2)
            self.assertEqual(shadow['final']['same_posted_no_clearing_gross'],1)
            self.assertEqual(shadow['final']['incorporated']['obligation'],2)
            self.assertTrue(any(p['mirror_mismatches'] for p in result['trace']))

    def test_lost_request_and_ack_retry_idempotently(self):
        edges=ring([-1,-1,-1])
        with PrivateStream(edges,seed=5,discovery_until=10,drop_request_ids=(1,),drop_ack_ids=(2,)) as stream:
            result=stream.run(20)
            self.audit_basic(result,edges)
            self.assertEqual(result['dropped_requests'],1)
            self.assertEqual(result['dropped_acknowledgements'],1)
            self.assertGreaterEqual(result['retried_requests'],2)
            self.assertEqual(result['final']['debt'],0)
            self.assertEqual(result['final']['reservations'],0)
            self.assertEqual(result['delivery_failures'],0)

    def test_fixed_window_retains_partial_settlement(self):
        edges=ring([-2,-2,-2])
        with PrivateStream(edges,seed=4,discovery_until=15) as stream:
            result=stream.run(0)
            self.assertEqual(result['delivered_messages'],0)
            self.assertGreater(result['final']['pending_messages'],0)
            self.assertEqual(result['final']['debt'],6)
            self.assertFalse(result['censored'])
            result=stream.run(25)
            self.assertEqual(result['final']['debt'],0)

    def test_cap_does_not_force_unlock_or_claim_completion(self):
        edges=ring([-2,-2,-2])
        for cap in (0,1,12,15,20):
            with self.subTest(cap=cap),PrivateStream(edges,seed=4,message_cap=cap,discovery_until=15) as stream:
                result=stream.run(25)
                self.assertEqual(result['messages'],cap)
                self.assertTrue(result['censored'])
                self.assertEqual(result['status'],'message_cap')
                self.assertGreater(result['pending_events'],0)
                self.audit_basic(result,edges)

    def test_cap_during_lost_request_retry_retains_logical_pending(self):
        from private_stream_audit import audit_run
        edges=[('a','b',-1,prefs(),prefs())]
        with PrivateStream(edges,message_cap=4,drop_request_ids=(1,),discovery_until=0) as stream:
            result=stream.run(5)
            self.assertTrue(result['censored'])
            self.assertGreater(result['final']['pending_messages'],0)
            audit=audit_run(result)
            self.assertTrue(audit['independent_audit_passed'],audit['failures'])

    def test_context_hash_is_versioned_and_fulfillment_verified(self):
        ident,secret='a'*64,'b'*64
        condition=hash_comfort_condition(ident,1,secret,1)
        context=dict(protocol='private-hashlock-v2',unit='TEST',id=ident,amount=1,
                     preimage=secret,clearing_mode='comfort',policy=COMFORT_POLICY,direction=1)
        self.assertEqual(hashlib.sha256(json.dumps(context,sort_keys=True,separators=(',',':')).encode()).hexdigest(),condition)
        with PrivateStream(ring([-1,-1,-1]),method='private_nonexpansion',discovery_until=0) as stream:
            node=stream.actors['0'].node
            value=dict(context,condition=condition)
            node.check_preimage(value)
            with self.assertRaises(ValueError):
                node.check_preimage(dict(value,preimage='c'*64))
            # A plain production comfort node must reject the distinct research policy.
            node=PrivateStream(ring([-1,-1,-1]),method='faithful_comfort',discovery_until=0)
            try:
                original=node.actors['1'].node
                wire={k:value[k] for k in ('protocol','id','amount','condition','clearing_mode','policy','direction')}
                wire.update(kind='ready',message_id='test')
                with self.assertRaisesRegex(ValueError,'Invalid comfort policy'):
                    original.receive('0',wire)
            finally:
                node.close()


if __name__=='__main__':
    unittest.main()
