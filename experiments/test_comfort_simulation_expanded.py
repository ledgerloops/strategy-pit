import copy
import unittest
from comfort_simulation_expanded import PreferenceActor, PreferenceNetwork, fixture, independent_audit


def pref(low=-3,high=3,cap=3,auto=True,available=True):
    return dict(credit_limit=cap,comfort_min=low,comfort_max=high,auto_adjust=auto,available=available)


class ExpandedComfortTest(unittest.TestCase):
    def test_missing_preferences_block_comfort_not_debt_cancellation(self):
        actor=PreferenceActor(0)
        actor.links[1]=[-1,pref(available=False),pref()]
        self.assertFalse(actor.eligible(1,'comfort'))
        self.assertTrue(actor.eligible(1,'cancellation'))
        net=PreferenceNetwork([(0,1,-1,pref(available=False),pref())])
        self.assertEqual(net.score()['missing_zones'],1)
        self.assertEqual(net.score()['empty_zones'],0)

    def test_empty_zones_not_silently_converted_to_zero_preferences(self):
        net=PreferenceNetwork([(0,1,0,pref(2,3),pref(2,3))])
        self.assertEqual(net.score()['empty_zones'],1)
        self.assertFalse(net.actors[0].eligible(1,'comfort'))

    def test_asymmetric_zone_can_prefer_more_debt(self):
        actor=PreferenceActor(0)
        actor.links[1]=[0,pref(1,3),pref(-3,-1)]
        self.assertTrue(actor.eligible(1,'comfort',start=True))
        actor.links[1][1]['auto_adjust']=False
        self.assertFalse(actor.eligible(1,'comfort',start=True))

    def test_new_contacts_and_blocked_arrivals_count(self):
        edges=[(0,1,0,pref(),pref()),(1,2,0,pref(),pref())]
        net=PreferenceNetwork(edges)
        net.add_contact(0,2,pref(cap=1),pref(cap=1))
        self.assertFalse(net.transfer(0,2,3))
        self.assertTrue(net.transfer(0,2,1))
        audit=independent_audit(edges,net.audit,'comfort')
        self.assertEqual(audit['offered_transfers'],2)
        self.assertEqual(audit['accepted_transfers'],1)
        self.assertEqual(audit['blocked_value'],3)
        self.assertEqual(audit['accepted_value'],1)

    def test_independent_audit_rejects_tampered_settlement(self):
        from comfort_simulation import illustrative
        edges=[(a,b,v,dict(own,available=True),dict(peer,available=True))
               for a,b,v,own,peer in illustrative()]
        net=PreferenceNetwork(edges)
        net.clear('comfort')
        independent_audit(edges,net.audit,'comfort')
        bad=copy.deepcopy(net.audit)
        change=list(bad[0]['changes'][0])
        change[3]+=1
        bad[0]['changes'][0]=change
        with self.assertRaises(AssertionError):
            independent_audit(edges,bad,'comfort')

    def test_all_families_both_policies_replay_and_preserve_net(self):
        for family in ('asymmetric','partial','tight','missing','incompatible'):
            edges,events=fixture(7,family)
            for policy in ('cancellation','comfort'):
                net=PreferenceNetwork(edges,7)
                for e in events:
                    if e['kind']=='contact':
                        net.add_contact(e['a'],e['b'],e['own'],e['peer'])
                    else:
                        net.transfer(e['a'],e['b'],e['amount'])
                        net.clear(policy,net.messages+100)
                audit=independent_audit(edges,net.audit,policy)
                for k,v in audit['final'].items():
                    self.assertEqual(net.score()[k],v)
                expected=dict(net.initial_nets)
                for a,b,value in net.external:
                    expected[a]+=value
                    expected[b]-=value
                self.assertEqual(net.nets(),expected)
                self.assertEqual(audit['offered_transfers'],40)
                self.assertEqual(audit['accepted_transfers']+audit['blocked_transfers'],40)


if __name__=='__main__': unittest.main()
