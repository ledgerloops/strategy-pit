import unittest
from concurrent_headroom import Search
from concurrent_decrease_first import DecreaseFirstHeadroom
from temporal_episodes import Episode
from temporal_benchmark import synthetic
from test_concurrent_headroom_audit import audit_signed_ledger


class DecreaseFirstTests(unittest.TestCase):
    def test_direction_before_capacity_then_largest(self):
        sim=DecreaseFirstHeadroom()
        sim.stop_searches()
        sim.add_transfer('a','b',2)
        sim.add_transfer('a','c',5)
        sim.add_transfer('d','a',1)
        sim.run(0)
        actor=sim.nodes['a']
        actor.episodes['d'].ceiling=100
        sent=[]
        sim.send=lambda *args:sent.append(args)
        actor.search(Search(('a',1),['a'],{'a'}))
        self.assertEqual(sent[0][1],'c')
        actor.episodes['c'].live=False
        sent.clear()
        actor.search(Search(('a',2),['a'],{'a'}))
        self.assertEqual(sent[0][1],'b')

    def test_signed_ledger_with_loss_and_sleep(self):
        sim=DecreaseFirstHeadroom(seed=201,loss=.3)
        sim.add_sleep(0,100,80)
        for e in synthetic('bursts',12,201):
            sim.add_transfer(e.source,e.target,e.amount,at=e.time)
        sim.run(800)
        sim.drain()
        audit_signed_ledger(sim)


if __name__=='__main__':unittest.main()
