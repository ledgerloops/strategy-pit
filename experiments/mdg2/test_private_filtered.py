"""Tiny local/correctness fixtures, no performance workload or parameter search."""
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0,str(HERE))
from private_stream import PrivateStream, COMFORT_POLICY
from private_stream_filtered import FilteredPrivateStream, FilteredNonexpandingNode, METHOD, DISCOVERY_VERSION
from private_stream_audit import audit_run


def pref(auto=True):
    return dict(credit_limit=100,comfort_min=-100,comfort_max=100,auto_adjust=auto)


def links(values):
    return [('x',peer,value,pref(),pref()) for peer,value in values.items()]


def ring(values):
    return [(str(i),str((i+1)%len(values)),value,pref(),pref()) for i,value in enumerate(values)]


class FilteredPrivateStreamTests(unittest.TestCase):
    def synced(self,edges):
        stream=FilteredPrivateStream(edges,discovery_until=0)
        self.addCleanup(stream.close)
        stream.run(.1)
        return stream

    def test_increasing_pair_filtered_before_forward(self):
        stream=self.synced(links(dict(prev=-2,bad=0,good=-2)))
        node=stream.actors['x'].node
        self.assertIsInstance(node,FilteredNonexpandingNode)
        # Incoming -2 -> -3 costs+1, requiring outgoing cost<=-1.
        self.assertEqual({node.comfort_candidate(1,1,'prev') for _ in range(30)},{'good'})

    def test_helper_outgoing_retained_when_incoming_reduces(self):
        stream=self.synced(links(dict(prev=2,helper_a=0,helper_b=1)))
        node=stream.actors['x'].node
        # Incoming2 ->1 costs-1; both outgoing helper increases cost+1.
        seen={node.comfort_candidate(1,1,'prev') for _ in range(60)}
        self.assertEqual(seen,{'helper_a','helper_b'})
        self.assertTrue(all(abs(node.balance(peer)+1)>abs(node.balance(peer)) for peer in seen))

    def test_direction_minus_one_and_cross_zero_amount(self):
        stream=self.synced(links(dict(prev=3,bad=0,good=3)))
        node=stream.actors['x'].node
        # Incoming3 ->5 costs+2; outgoing3 ->1 costs-2.
        self.assertEqual({node.comfort_candidate(2,-1,'prev') for _ in range(20)},{'good'})
        stream2=self.synced(links(dict(prev=-1,bad=0,neutral=-1)))
        node2=stream2.actors['x'].node
        # Incoming -1 ->-3 costs2; crossing -1 ->+1 costs0, insufficient.
        self.assertIsNone(node2.comfort_candidate(2,1,'prev'))

    def test_origin_selection_and_rng_same_as_baseline(self):
        edges=links(dict(a=-3,b=-2,c=0,d=2))
        filtered=self.synced(edges)
        baseline=PrivateStream(edges,seed=0,method='private_nonexpansion',discovery_until=0)
        self.addCleanup(baseline.close)
        baseline.run(.1)
        a,b=filtered.actors['x'].node,baseline.actors['x'].node
        for direction in (1,-1):
            self.assertEqual([a.comfort_candidate(1,direction,strict=True) for _ in range(30)],
                             [b.comfort_candidate(1,direction,strict=True) for _ in range(30)])
        self.assertEqual(a.choice_rng.getstate(),b.choice_rng.getstate())

    def test_reservation_and_bilateral_opt_in_still_enforced(self):
        edges=links(dict(prev=2,helper=0))
        stream=self.synced(edges)
        node=stream.actors['x'].node
        with node.db:
            node.db.execute('INSERT INTO reservations VALUES(?,?)',('helper','other-operation'))
        self.assertIsNone(node.comfort_candidate(1,1,'prev'))
        with node.db:
            node.db.execute('DELETE FROM reservations')
        own=dict(pref(False),expected_revision=2)
        node.set_preferences('helper',own)
        self.assertIsNone(node.comfort_candidate(1,1,'prev'))

    def test_settlement_and_actual_bilateral_arrivals_audit(self):
        edges=ring([-2,-2,0])
        with FilteredPrivateStream(edges,seed=7,discovery_until=8) as stream:
            stream.offer(.2,'0','1',-1,'offer-a')
            result=stream.run(18)
            audit=audit_run(result)
            self.assertTrue(audit['independent_audit_passed'],audit['failures'])
            self.assertEqual(result['method'],METHOD)
            self.assertEqual(result['discovery_version'],DISCOVERY_VERSION)
            self.assertEqual(result['policy'],COMFORT_POLICY)
            self.assertEqual(len(result['accepted_offers']),1)
            self.assertGreater(audit['completed_hashlock_cycles'],0)
            self.assertEqual(result['final']['mirror_mismatches'],0)
            self.assertEqual(result['final']['reservations'],0)

    def test_cap_and_lost_ack_inherited_unchanged(self):
        for cap in (0,1,12,20):
            with self.subTest(cap=cap),FilteredPrivateStream(ring([-1,-1,-1]),seed=5,
                    discovery_until=8,message_cap=cap,drop_ack_ids=(1,)) as stream:
                result=stream.run(18)
                audit=audit_run(result)
                self.assertTrue(audit['independent_audit_passed'],audit['failures'])
                self.assertEqual(result['messages'],cap)
                self.assertTrue(result['censored'])

    def test_only_constructor_and_result_override_transport(self):
        # Protect against accidentally adding alternate settlement/scheduler logic.
        self.assertEqual(set(FilteredPrivateStream.__dict__)-{'__module__','__doc__'},
                         {'__init__','result'})
        self.assertEqual(set(FilteredNonexpandingNode.__dict__)-{'__module__','__doc__'},
                         {'comfort_candidate'})
        self.assertIs(FilteredPrivateStream.run,PrivateStream.run)
        self.assertIs(FilteredPrivateStream._local_automation,PrivateStream._local_automation)
        self.assertIs(FilteredNonexpandingNode.prepare_local,
                      FilteredNonexpandingNode.__bases__[0].prepare_local)


if __name__=='__main__':
    unittest.main()
