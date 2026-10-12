import unittest
from comfort_simulation import Actor, Network, distance, fixture, illustrative, run, terms
from comfort import shared_comfort


class ComfortSimulationTest(unittest.TestCase):
    def test_mirrored_intersection(self):
        own=dict(credit_limit=20,comfort_min=-5,comfort_max=15,auto_adjust=True)
        peer=dict(credit_limit=10,comfort_min=-10,comfort_max=8,auto_adjust=True)
        zone=shared_comfort(own,peer)
        self.assertEqual((zone['min'],zone['max']),(-5,10))

    def test_help_increases_debt_and_clears_discomfort(self):
        net=Network(illustrative())
        before=net.nets()
        net.clear('comfort')
        self.assertEqual(net.nets(),before)
        self.assertEqual(net.score()['discomfort'],0)
        self.assertEqual(net.score()['debt'],4)
        self.assertEqual(net.assisted_moves,2)
        baseline=Network(illustrative())
        baseline.clear('cancellation')
        self.assertEqual(baseline.score()['discomfort'],2)

    def test_no_assistance_without_both_permissions(self):
        edges=illustrative()
        edges[1]=(1,2,0,terms(2,False),terms(2))
        net=Network(edges)
        net.clear('comfort')
        self.assertEqual(net.moves,0)

    def test_neutral_debt_reduction_requires_bilateral_permission(self):
        actor=Actor(0)
        actor.links[1]=[-1,terms(2,False),terms(2)]
        self.assertFalse(actor.eligible(1,'comfort'))
        self.assertTrue(actor.eligible(1,'cancellation'))
        actor.links[1]=[-1,terms(0,False),terms(0)]
        self.assertTrue(actor.eligible(1,'comfort',start=True))

    def test_empty_zone_and_hard_cap(self):
        actor=Actor(0)
        own=dict(credit_limit=1,comfort_min=1,comfort_max=2,auto_adjust=True)
        peer=dict(credit_limit=1,comfort_min=1,comfort_max=2,auto_adjust=True)
        actor.links[1]=[0,own,peer]
        self.assertFalse(actor.eligible(1,'comfort'))
        actor.links[1]=[1,terms(2),terms(2)]
        actor.links[1][1]=dict(terms(2),credit_limit=1)
        self.assertFalse(actor.eligible(1,'comfort'))

    def test_two_nodes_cannot_close(self):
        net=Network([(0,1,-2,terms(),terms())])
        net.clear('comfort')
        self.assertEqual(net.moves,0)

    def test_receipts_independently_replay_all_seeds(self):
        for seed in range(8):
            edges,_=fixture(seed)
            net=Network(edges,seed)
            initial=net.score()['discomfort']
            replay={(a,b):balance for a,b,balance,_,_ in edges}
            net.clear('comfort')
            for receipt in net.receipts:
                delta={n:0 for n in net.actors}
                self.assertGreaterEqual(len(receipt),3)
                for a,b,old,new in receipt:
                    key=(a,b) if (a,b) in replay else (b,a)
                    sign=1 if key==(a,b) else -1
                    self.assertEqual(old,sign*replay[key])
                    replay[key]=sign*new
                    delta[a]+=new-old
                    delta[b]-=new-old
                self.assertTrue(all(v==0 for v in delta.values()))
            self.assertLessEqual(net.score()['discomfort'],initial)
            for (a,b),value in replay.items():
                self.assertEqual(value,net.actors[a].links[b][0])

    def test_arrivals_conservation_and_rejection(self):
        net=Network(illustrative())
        self.assertFalse(net.transfer(0,1,200))
        self.assertEqual(net.external,[])
        before=net.nets()
        self.assertTrue(net.transfer(0,1,1))
        net.clear('comfort')
        after=net.nets()
        self.assertEqual(after,{0:before[0]+1,1:before[1]-1,2:before[2]})

    def test_receiver_rejects_unacceptable_incoming_change(self):
        actor=Actor(0)
        actor.links[1]=[-1,terms(),terms()]
        self.assertEqual(actor.receive('opaque',1,'probe','comfort'),('reject',1))
        self.assertEqual(actor.probes,{})

    def test_actor_state_no_graph_or_remote_membership(self):
        actor=Actor(0)
        actor.links[1]=[1,terms(),terms()]
        actor.links[2]=[-1,terms(),terms()]
        self.assertEqual(actor.receive('opaque',1,'probe','comfort'),('probe',2))
        self.assertEqual(set(actor.probes['opaque']),{'root','parent','next','todo'})
        self.assertEqual(set(vars(actor)),{'links','probes','rng'})


if __name__=='__main__': unittest.main()
