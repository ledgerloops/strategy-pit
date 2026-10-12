"""Expanded preference fixtures; serialized adapter, no fault-safety claims.
Missing comfort preferences retain separately known bilateral hard grants.
"""
import argparse
import hashlib
import json
import random
from pathlib import Path
from comfort_simulation import Actor, Network, shared_comfort, distance


class PreferenceActor(Actor):
    def allowed(self, peer, delta, policy, start=False):
        _, own, other = self.links[peer]
        if policy == 'comfort' and not (own['available'] and other['available']):
            return False
        return super().allowed(peer, delta, policy, start)


class PreferenceNetwork(Network):
    def __init__(self, edges, seed=0):
        super().__init__(edges, seed)
        for node, old in list(self.actors.items()):
            actor = PreferenceActor(seed * 1009 + node)
            actor.links, actor.rng = old.links, old.rng
            self.actors[node] = actor
        self.audit = []

    def score(self):
        result = super().score()
        result['discomfort'] = result['empty_zones'] = result['missing_zones'] = 0
        for a, b in self.edges:
            balance, own, peer = self.actors[a].links[b]
            if not (own['available'] and peer['available']):
                result['missing_zones'] += 1
                continue
            zone = shared_comfort(own, peer)
            if zone['empty']:
                result['empty_zones'] += 1
            else:
                result['discomfort'] += distance(balance, zone)
        return result

    def probe(self, root, first, policy, budget):
        closed = super().probe(root, first, policy, budget)
        if closed:
            self.audit.append(dict(kind='settlement', changes=self.receipts[-1]))
        return closed

    def transfer(self, a, b, amount):
        accepted = super().transfer(a, b, amount)
        self.audit.append(dict(kind='transfer', a=a, b=b, amount=amount, accepted=accepted))
        return accepted

    def add_contact(self, a, b, own, peer):
        assert a != b and b not in self.actors[a].links
        self.edges.append((a, b))
        self.actors[a].links[b] = [0, own, peer]
        self.actors[b].links[a] = [0, peer, own]
        self.audit.append(dict(kind='contact', a=a, b=b, own=own, peer=peer))


def pref(rng, family):
    cap = rng.randint(2, 5) if family == 'tight' else 12
    center = rng.randint(-4, 4)
    width = rng.randint(0, 4)
    return dict(credit_limit=cap, comfort_min=center-width, comfort_max=center+width,
                auto_adjust=rng.random() < (.5 if family == 'partial' else 1),
                available=rng.random() >= (.3 if family == 'missing' else 0))


def preferences(rng, family):
    a, b = pref(rng, family), pref(rng, family)
    if family == 'incompatible':
        a.update(comfort_min=2, comfort_max=5)
        b.update(comfort_min=2, comfort_max=5)
    return a, b


def fixture(seed, family, size=12):
    rng = random.Random(seed)
    pairs = {tuple(sorted((n, (n+1) % size))) for n in range(size)}
    pairs.update((a,b) for a in range(size) for b in range(a+1,size) if rng.random()<.22)
    edges = []
    for a,b in sorted(pairs):
        own,peer = preferences(rng,family)
        balance = rng.randint(-min(6,peer['credit_limit']),min(6,own['credit_limit']))
        edges.append((a,b,balance,own,peer))
    absent = [(a,b) for a in range(size) for b in range(a+1,size) if (a,b) not in pairs]
    rng.shuffle(absent)
    events=[]
    live=sorted(pairs)
    for tick in range(40):
        if tick % 8 == 0 and absent:
            a,b=absent.pop()
            own,peer=preferences(rng,family)
            events.append(dict(kind='contact',a=a,b=b,own=own,peer=peer))
            live.append((a,b))
            # The same tick introduces a real external transfer on the new link.
        else:
            a,b=rng.choice(live)
        events.append(dict(kind='transfer',a=a,b=b,amount=rng.choice([-6,-3,-1,1,3,6])))
    return edges,events


def independent_audit(edges, events, policy):
    """Replay with independent arithmetic, no actor/decision/model calls."""
    ledger={(a,b):[value,own,peer] for a,b,value,own,peer in edges}
    baseline={(a,b):value for a,b,value,_,_ in edges}
    offered=accepted=blocked_value=accepted_value=0
    discomfort_worsening_edge_updates = 0
    def zone(own,peer):
        if not (own['available'] and peer['available']):
            return 'missing'
        low=max(own['comfort_min'],-peer['comfort_max'],-peer['credit_limit'])
        high=min(own['comfort_max'],-peer['comfort_min'],own['credit_limit'])
        return 'empty' if low>high else (low,high)
    def dist(value,z):
        return max(z[0]-value,value-z[1],0)
    for event in events:
        kind=event['kind']
        if kind=='contact':
            key=(event['a'],event['b'])
            assert key not in ledger and key[::-1] not in ledger
            ledger[key]=[0,event['own'],event['peer']]
            baseline[key]=0
        elif kind=='transfer':
            key=(event['a'],event['b'])
            value,own,peer=ledger[key]
            amount=event['amount']
            permitted=-peer['credit_limit'] <= value+amount <= own['credit_limit']
            assert event['accepted']==permitted
            offered+=1
            if permitted:
                ledger[key][0]+=amount
                baseline[key]+=amount
                accepted+=1
                accepted_value+=abs(amount)
            else:
                blocked_value+=abs(amount)
        else:
            changes=event['changes']
            assert len(changes)>=3
            nodes=[a for a,_,_,_ in changes]
            assert len(nodes)==len(set(nodes))
            deltas={}
            gain=0
            for a,b,old,new in changes:
                key=(a,b) if (a,b) in ledger else (b,a)
                sign=1 if key==(a,b) else -1
                value,first,second=ledger[key]
                own,peer=(first,second) if sign==1 else (second,first)
                assert old==value*sign and new-old==1
                assert -peer['credit_limit']<=new<=own['credit_limit']
                deltas[a]=deltas.get(a,0)+new-old
                deltas[b]=deltas.get(b,0)-new+old
                if policy=='cancellation':
                    assert abs(new)<abs(old)
                    z=zone(own,peer)
                    if isinstance(z,tuple) and dist(new,z)>dist(old,z):
                        discomfort_worsening_edge_updates += 1
                else:
                    z=zone(own,peer)
                    assert isinstance(z,tuple)
                    before,after=dist(old,z),dist(new,z)
                    assert after<=before
                    if after==before or abs(new)>abs(old):
                        assert own['auto_adjust'] and peer['auto_adjust']
                    gain+=before-after
                ledger[key][0]=new*sign
            assert all(value==0 for value in deltas.values())
            assert policy=='cancellation' or gain>0
    def score(values):
        debt=discomfort=empty=missing=0
        for key,value in values.items():
            _,own,peer=ledger[key]
            z=zone(own,peer)
            debt+=abs(value)
            if z=='missing': missing+=1
            elif z=='empty': empty+=1
            else: discomfort+=dist(value,z)
        return dict(debt=debt,discomfort=discomfort,empty_zones=empty,missing_zones=missing)
    values={key:record[0] for key,record in ledger.items()}
    final=score(values)
    # Matching posted-transfer reference, not a hard-cap-feasible alternative.
    reference=score(baseline)
    return dict(final=final,posted_stream_reference=reference,offered_transfers=offered,
                accepted_transfers=accepted,blocked_transfers=offered-accepted,
                blocked_value=blocked_value,accepted_value=accepted_value,
                discomfort_worsening_edge_updates=discomfort_worsening_edge_updates)


def run():
    rows=[]
    for family in ('asymmetric','partial','tight','missing','incompatible'):
        for seed in range(8):
            edges,events=fixture(seed,family)
            fixture_hash=hashlib.sha256(json.dumps([edges,events],sort_keys=True).encode()).hexdigest()
            for temporal in (False,True):
                for policy in ('cancellation','comfort'):
                    net=PreferenceNetwork(edges,seed)
                    initial=net.score()
                    if temporal:
                        net.clear(policy,200)
                        for event in events:
                            if event['kind']=='contact':
                                net.add_contact(event['a'],event['b'],event['own'],event['peer'])
                            else:
                                net.transfer(event['a'],event['b'],event['amount'])
                                net.clear(policy,net.messages+200)
                    else:
                        net.clear(policy,8200)
                    audit=independent_audit(edges,net.audit,policy)
                    assert all(net.score()[key]==value for key,value in audit['final'].items())
                    expected=dict(net.initial_nets)
                    for a,b,amount in net.external:
                        expected[a]+=amount
                        expected[b]-=amount
                    assert net.nets()==expected
                    rows.append(dict(family=family,seed=seed,temporal=temporal,policy=policy,
                                     initial=initial,final=net.score(),audit=audit,events=net.audit,
                                     fixture_sha256=fixture_hash))
    root=Path(__file__).resolve().parents[1]
    paths=['experiments/comfort_simulation_expanded.py','experiments/comfort_simulation.py','app/comfort.py']
    return dict(schema=1,complete=True,source_hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths},
                config=dict(seeds=list(range(8)),nodes=12,static_budget=8200,temporal_transfers=40,
                            new_contacts=5,per_service_budget=200,unit_move=1,
                            faults='none; serialized reliable simulator; fixed preferences'),rows=rows)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,default=Path('experiments/results/comfort-simulation-expanded.json'))
    args=p.parse_args()
    args.output.write_text(json.dumps(run(),indent=2)+'\n')
