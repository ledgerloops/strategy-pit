"""Independent signed-ledger audit for concurrent Headroom.

Do not import the implementation's transition helpers: reconstruct caps and
balances from ordered economic events and verify completed transaction nets.
"""
from collections import Counter
import unittest


def nonzero(mapping):
    return {key: value for key, value in mapping.items() if value}


def audit_signed_ledger(sim):
    graph, pairs, generations, revisions = {}, {}, Counter(), Counter()
    posted_net, transaction_net, transaction_gain = Counter(), {}, Counter()
    applied = set()
    previous_time = -1
    for order, record in enumerate(sim.ledger_records):
        assert record['order'] == order
        assert record['time'] >= previous_time
        previous_time = record['time']
        a, b, delta = record['source'], record['target'], record['delta']
        key = tuple(sorted((a, b)))
        sign = 1 if a == key[0] else -1
        old, cap = pairs.get(key, (0, 0))
        if record['kind'] == 'transfer':
            assert delta > 0
            new = old + sign * delta
            posted_net[a] -= delta
            posted_net[b] += delta
            if not old or old * new < 0:
                new_cap = abs(new)
            elif new:
                new_cap = cap + abs(new) - abs(old)
            else:
                new_cap = 0
        else:
            assert record['kind'] == 'commit'
            assert old != 0, 'commit cannot restore a closed relationship'
            # Economic event is recorded against its existing debtor owner.
            assert old * sign > 0, 'commit must quote current debtor direction'
            ident = record['txid']
            ident = tuple(ident) if isinstance(ident, list) else ident
            marker = ident, key
            assert marker not in applied, 'pair commit applied twice'
            applied.add(marker)
            new = old + sign * delta
            assert old * new >= 0, 'clearing cannot reverse debt direction'
            new_cap = cap if new else 0
            assert abs(new) <= cap, 'restoration exceeds consent ceiling'
            txnet = transaction_net.setdefault(ident, Counter())
            txnet[a] -= delta
            txnet[b] += delta
            transaction_gain[ident] -= delta
        opening = bool(new) and (not old or old * new < 0)
        if opening:
            generations[key] += 1
            revisions[key] = 0
        else:
            revisions[key] += 1
        pairs[key] = new, new_cap
        graph[key] = max(new, 0)
        graph[key[::-1]] = max(-new, 0)
        assert abs(new) <= new_cap
    assert nonzero(graph) == sim.graph_snapshot()
    net = Counter()
    for (a, b), value in graph.items():
        net[a] -= value
        net[b] += value
    assert nonzero(net) == nonzero(posted_net), 'drained settlement changes net positions'
    for ident, net in transaction_net.items():
        assert not nonzero(net), ('incomplete/nonconserving cycle', ident, net)
        assert transaction_gain[ident] > 0, 'accepted cycle did not reduce debt'
    for key, (balance, cap) in pairs.items():
        a, b = key
        for node, peer, value in [(a,b,balance),(b,a,-balance)]:
            ep = sim.nodes[node].episodes[peer]
            assert ep.balance == value
            assert ep.ceiling == cap
            assert ep.live == bool(value)
            assert ep.number == generations[key]
            assert ep.revision == revisions[key]
    assert not sim.pending
    assert sim.pending_reservations == 0
    assert not any(sim.transfer_queues.values())
    return dict(transactions=len(transaction_net), restored_volume=sum(
        r['delta'] for r in sim.ledger_records if r['kind']=='commit' and r['delta']>0))


def propose(sim, nodes, directions, sequence=1000):
    from concurrent_headroom import Search, Proposal
    arcs = []
    for a,b,direction in zip(nodes,nodes[1:]+nodes[:1],directions):
        ep = sim.nodes[a].episodes[b]
        arcs.append((a,b,direction,sim.nodes[a].capacity(b,direction),ep.number,ep.revision))
    token = Search((nodes[0],sequence),list(nodes),set(nodes),arcs=arcs[:-1])
    sim.nodes[nodes[0]].active = True
    # The forced route stands in for a token that already visited each actor.
    for node in nodes:
        sim.nodes[node].admitted_tokens.add(token.ident)
    tx = Proposal(token,list(nodes),arcs,min(a[3] for a in arcs),proposed_at=sim.time)
    sim.send(nodes[-1],nodes[0],'hprepare',tx)
    return tx


class ConcurrentHeadroomAuditTests(unittest.TestCase):
    def quiet(self, **kwargs):
        from concurrent_headroom import ConcurrentHeadroom
        sim=ConcurrentHeadroom(max_delay=1,retransmit=2,**kwargs)
        sim.stop_searches()
        return sim

    def alice(self, ac=6, **kwargs):
        sim=self.quiet(**kwargs)
        for a,b,v in [('a','b',7),('a','c',ac),('d','a',5),('c','d',5),('b','c',3)]:
            sim.add_transfer(a,b,v)
        sim.drain()
        propose(sim,['a','c','d'],[1,1,1])
        sim.drain()
        return sim

    def test_live_mixed_cycle_has_positive_gain_and_preserves_net(self):
        sim=self.alice()
        self.assertEqual(sim.graph_snapshot(),{('a','b'):7,('a','c'):1,('b','c'):3})
        propose(sim,['c','a','b'],[-1,1,1],1001)
        sim.drain()
        self.assertEqual(sim.graph_snapshot(),{('a','b'):4,('a','c'):4})
        audit=audit_signed_ledger(sim)
        self.assertEqual(audit,dict(transactions=2,restored_volume=3))

    def test_zero_closed_original_cannot_be_restored(self):
        sim=self.alice(5)
        self.assertEqual(sim.nodes['c'].capacity('a',-1),0)
        propose(sim,['c','a','b'],[-1,1,1],1001)
        sim.drain()
        self.assertEqual(sim.graph_snapshot(),{('a','b'):7,('b','c'):3})
        self.assertEqual(audit_signed_ledger(sim)['restored_volume'],0)

    def test_mixed_cycle_survives_data_ack_loss_and_sleep(self):
        sim=self.alice(loss=.3,ack_loss=.4,seed=12)
        sim.add_sleep('a',sim.time+1,40)
        propose(sim,['c','a','b'],[-1,1,1],1001)
        sim.drain()
        self.assertEqual(sim.graph_snapshot(),{('a','b'):4,('a','c'):4})
        self.assertGreater(sim.metrics['retransmissions'],0)
        self.assertEqual(audit_signed_ledger(sim)['restored_volume'],3)

    def test_reverse_transfer_waits_for_restoration_pair_lock(self):
        sim=self.alice()
        propose(sim,['c','a','b'],[-1,1,1],1001)
        sim.run(sim.time+1)
        self.assertTrue(sim.nodes['c'].locked('a'))
        prior_posts=len(sim.transfer_records)
        sim.add_transfer('c','a',8)
        sim.run(sim.time)
        self.assertEqual(len(sim.transfer_records),prior_posts)
        self.assertTrue(any(sim.transfer_queues.values()))
        sim.drain()
        self.assertEqual(sim.graph_snapshot(),{('a','b'):4,('c','a'):4})
        ep=sim.nodes['c'].episodes['a']
        self.assertEqual((ep.balance,ep.ceiling),(4,4))
        self.assertGreater(sim.metrics['transfer_deferrals'],0)
        audit_signed_ledger(sim)

    def test_dropped_prepare_and_commit_reordered_transport(self):
        from concurrent_headroom import ConcurrentHeadroom
        class ForcedDrops(ConcurrentHeadroom):
            def __init__(self, **kwargs):
                self.dropped=set()
                self.delivery_ids=[]
                super().__init__(**kwargs)
            def _delivery(self, ident):
                envelope=self.pending.get(ident)
                if envelope:
                    kind=envelope.kind
                    if kind in ('hprepare','hcommit') and kind not in self.dropped:
                        self.dropped.add(kind)
                        return
                    self.delivery_ids.append(ident)
                return super()._delivery(ident)
        sim=ForcedDrops(max_delay=8,retransmit=3,ack_loss=.3,seed=7)
        sim.stop_searches()
        for a,b,v in [('a','b',7),('a','c',6),('d','a',5),('c','d',5),('b','c',3)]:
            sim.add_transfer(a,b,v)
        sim.drain()
        propose(sim,['a','c','d'],[1,1,1])
        sim.drain()
        propose(sim,['c','a','b'],[-1,1,1],1001)
        sim.drain()
        self.assertEqual(sim.dropped,{'hprepare','hcommit'})
        self.assertTrue(any(a>b for a,b in zip(sim.delivery_ids,sim.delivery_ids[1:])))
        self.assertEqual(sim.graph_snapshot(),{('a','b'):4,('a','c'):4})
        self.assertEqual(audit_signed_ledger(sim)['restored_volume'],3)

    def test_actors_cannot_read_global_graph(self):
        from test_temporal_adversarial import NodeLocalFacade
        class ResidualFacade(NodeLocalFacade):
            allowed=NodeLocalFacade.allowed | {'restoration'}
        sim=self.alice()
        for node in sim.nodes.values():
            node.sim=ResidualFacade(sim)
        for forbidden in ('nodes','channels','open_channels','graph_snapshot','pending'):
            with self.assertRaises(AssertionError):
                getattr(sim.nodes['a'].sim,forbidden)
        propose(sim,['c','a','b'],[-1,1,1],1001)
        sim.drain()
        self.assertEqual(audit_signed_ledger(sim)['restored_volume'],3)

    def test_concurrent_discovery_random_dynamic_inputs(self):
        import random
        from concurrent_headroom import ConcurrentHeadroom
        for restoration in (False,True):
            sim=ConcurrentHeadroom(restoration=restoration,loss=.2,ack_loss=.2,
                                   seed=41,retry_interval=12,max_delay=3,retransmit=6)
            rng=random.Random(104)
            for time in range(0,300,5):
                a,b=rng.sample(range(8),2)
                sim.add_transfer(a,b,rng.randint(1,9),at=time)
            sim.add_sleep(0,80,40)
            sim.add_sleep(2,150,60)
            sim.run(800)
            sim.drain()
            audit_signed_ledger(sim)


if __name__ == '__main__': unittest.main()
