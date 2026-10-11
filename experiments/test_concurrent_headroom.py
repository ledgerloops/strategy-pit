import random
import unittest
from concurrent_headroom import ConcurrentHeadroom, Search, Proposal


def propose(sim,nodes,directions,ident):
    arcs=[]
    for a,b,d in zip(nodes,nodes[1:]+nodes[:1],directions):
        node=sim.nodes[a];ep=node.episodes[b]
        arcs.append((a,b,d,node.capacity(b,d),ep.number,ep.revision))
    token=Search((nodes[0],ident),list(nodes),set(nodes),arcs=arcs[:-1])
    tx=Proposal(token,list(nodes),arcs,min(a[3] for a in arcs))
    sim.send(nodes[-1],nodes[0],'hprepare',tx)
    sim.drain()


class ConcurrentTests(unittest.TestCase):
    def test_live_mixed_and_closed_prohibited(self):
        for ac in (5,6):
            sim=ConcurrentHeadroom(seed=1,loss=.2,ack_loss=.3)
            sim.stop_searches()
            for a,b,x in [('a','b',7),('a','c',ac),('d','a',5),('c','d',5),('b','c',3)]:
                sim.add_transfer(a,b,x)
            sim.drain()
            propose(sim,['a','c','d'],[1,1,1],1)
            if ac==5:
                self.assertEqual(sim.nodes['c'].capacity('a',-1),0)
            else:
                propose(sim,['c','a','b'],[-1,1,1],2)
                self.assertEqual(sim.graph_snapshot(),{('a','b'):4,('a','c'):4})
                self.assertEqual(sim.metrics['mixed_cycles'],1)
                self.assertEqual(sim.metrics['restored_volume'],3)

    def test_random_dynamic_loss_sleep_conservation(self):
        for seed in range(12):
            rng=random.Random(seed)
            sim=ConcurrentHeadroom(seed=seed,loss=.3,ack_loss=.3,retry_interval=15)
            expected={i:0 for i in range(8)}
            for i in range(80):
                a,b=rng.sample(range(8),2);v=rng.randrange(1,15)
                expected[a]+=v;expected[b]-=v
                sim.add_transfer(a,b,v,at=3*i)
            for n in range(8):sim.add_sleep(n,rng.randrange(60),rng.randrange(10,70))
            sim.run(500);sim.drain()
            actual={i:0 for i in range(8)}
            for (a,b),v in sim.graph_snapshot().items():actual[a]+=v;actual[b]-=v
            self.assertEqual(actual,expected)
            self.assertFalse(sim.pending_reservations)
            for node in sim.nodes.values():
                for ep in node.episodes.values():self.assertLessEqual(abs(ep.balance),ep.ceiling)
            self.assertTrue(all(sum(c['directions'])>0 for c in sim.cycle_records))

    def test_signed_exposure_observer(self):
        from concurrent_headroom_benchmark import observe
        records=[]
        for a,b,v in [('a','c',1),('a','b',7),('b','c',3)]:
            records.append(dict(time=0,kind='transfer',source=a,target=b,delta=v))
        for time,a,b,v in [(1,'a','c',3),(2,'a','b',-3),(3,'b','c',-3)]:
            records.append(dict(time=time,kind='commit',source=a,target=b,delta=v,txid=('a',1)))
        observed=observe(records,4)
        self.assertEqual(observed['posted_debt_area'],44)
        self.assertEqual(observed['partial_settlement_exposure_area'],6)
        self.assertEqual(observed['peak_partial_settlement_exposure'],3)
        self.assertEqual(observed['final_partial_settlement_exposure'],0)

    def test_restoration_control_disabled(self):
        sim=ConcurrentHeadroom(restoration=False,seed=3)
        for a,b,x in [('a','b',6),('b','c',5),('c','a',5)]:sim.add_transfer(a,b,x)
        sim.run(200);sim.drain()
        self.assertEqual(sim.graph_snapshot(),{('a','b'):1})
        self.assertEqual(sim.nodes['b'].capacity('a',-1),0)

if __name__=='__main__':unittest.main()
