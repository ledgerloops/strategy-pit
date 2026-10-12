"""Serialized neighbour-local comfort experiment, not production settlement.
Actors see own links and opaque probes only. Adapter provides reliable delivery
and atomic settlement of locally chosen successors; receipts are offline only.
"""
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from comfort import shared_comfort


def terms(width=0, auto=True):
    return dict(credit_limit=100, comfort_min=-width, comfort_max=width, auto_adjust=auto)


def distance(balance, zone):
    return None if zone['empty'] else max(zone['min']-balance, 0, balance-zone['max'])


class Actor:
    def __init__(self, seed):
        self.links = {}
        self.probes = {}
        self.rng = random.Random(seed)

    def eligible(self, peer, policy, start=False):
        return self.allowed(peer, 1, policy, start)

    def allowed(self, peer, delta, policy, start=False):
        b, own, other = self.links[peer]
        zone = shared_comfort(own, other)
        if not zone['hard_min'] <= b+delta <= zone['hard_max']:
            return False
        if policy == 'cancellation':
            return abs(b+delta) < abs(b)
        if zone['empty']:
            return False
        old, new = distance(b, zone), distance(b+delta, zone)
        return (new <= old and (not start or new < old) and
                ((new < old and abs(b+delta) <= abs(b)) or
                 (own['auto_adjust'] and other['auto_adjust'])))

    def candidates(self, policy, parent=None):
        peers = [p for p in self.links if p != parent and self.eligible(p, policy)]
        self.rng.shuffle(peers)
        return peers

    def receive(self, token, sender, kind, policy):
        state = self.probes.get(token)
        if kind == 'probe':
            if sender not in self.links or not self.allowed(sender, -1, policy):
                return 'reject', sender
            if state is not None:
                return ('closed', None) if state['root'] else ('reject', sender)
            state = dict(root=False, parent=sender, next=None,
                         todo=self.candidates(policy, sender))
            self.probes[token] = state
        if state['todo']:
            state['next'] = state['todo'].pop()
            return 'probe', state['next']
        state['next'] = None
        return ('failed', None) if state['root'] else ('reject', state['parent'])


class Network:
    def __init__(self, edges, seed=0):
        self.actors, self.edges = {}, []
        self.messages = self.moves = self.assisted_moves = self.serial = 0
        self.receipts, self.external = [], []
        for a, b, balance, own, peer in edges:
            if a == b or (a,b) in self.edges or (b,a) in self.edges:
                raise ValueError('simple graph required')
            zone = shared_comfort(own, peer)
            if not zone['hard_min'] <= balance <= zone['hard_max']:
                raise ValueError('initial hard bound exceeded')
            self.edges.append((a,b))
            for n in (a,b):
                self.actors.setdefault(n, Actor(seed*1009+n))
            self.actors[a].links[b] = [balance, own, peer]
            self.actors[b].links[a] = [-balance, peer, own]
        self.initial_nets = self.nets()

    def nets(self):
        return {n: sum(v[0] for v in a.links.values()) for n,a in self.actors.items()}

    def score(self):
        debt = discomfort = empty = 0
        for a,b in self.edges:
            balance, own, peer = self.actors[a].links[b]
            debt += abs(balance)
            d = distance(balance, shared_comfort(own,peer))
            empty += d is None
            discomfort += d or 0
        return dict(debt=debt, discomfort=discomfort, empty_zones=empty,
                    messages=self.messages, moves=self.moves, assisted_moves=self.assisted_moves)

    def probe(self, root, first, policy, budget):
        self.serial += 1
        token = str(self.serial)  # opaque ID: no root, route, or hop count
        self.actors[root].probes[token] = dict(root=True, parent=None, next=first, todo=[])
        sender, recipient, kind = root, first, 'probe'
        closed = False
        while self.messages < budget:
            self.messages += 1
            answer, target = self.actors[recipient].receive(token,sender,kind,policy)
            if answer == 'closed':
                closed = True
                break
            if target is None:
                break
            sender, recipient, kind = recipient, target, answer
        if closed:
            # Simulator installs the local successor decisions atomically. This
            # is an adapter, NOT evidence of distributed commit or recovery.
            edges, n = [], root
            while True:
                nxt = self.actors[n].probes[token]['next']
                edges.append((n,nxt))
                n = nxt
                if n == root:
                    break
                assert len(edges) <= len(self.actors)
            assert len(edges) >= 3  # offline audit; actors never receive count
            before, nets = self.score(), self.nets()
            changes = []
            for a,b in edges:
                assert self.actors[a].eligible(b,policy,start=a==root)
                old = self.actors[a].links[b][0]
                changes.append((a,b,old,old+1))
            for a,b,old,new in changes:
                self.actors[a].links[b][0] = new
                self.actors[b].links[a][0] = -new
            assert self.nets() == nets
            if policy == 'comfort':
                assert self.score()['discomfort'] < before['discomfort']
            self.moves += 1
            self.assisted_moves += any(abs(new)>abs(old) for _,_,old,new in changes)
            self.receipts.append(changes)
        for actor in self.actors.values():
            actor.probes.pop(token,None)
        return closed

    def clear(self, policy, budget=10250):
        # Simulator round robin; does not establish local fairness.
        while self.messages < budget:
            progressed = False
            for root, actor in self.actors.items():
                for first in actor.candidates(policy):
                    if actor.eligible(first,policy,start=True):
                        progressed |= self.probe(root,first,policy,budget)
                    if self.messages >= budget:
                        return
            if not progressed:
                return

    def transfer(self,a,b,amount):
        old,own,peer = self.actors[a].links[b]
        zone = shared_comfort(own,peer)
        if not zone['hard_min'] <= old+amount <= zone['hard_max']:
            return False
        self.actors[a].links[b][0] += amount
        self.actors[b].links[a][0] -= amount
        self.external.append((a,b,amount))
        return True


def illustrative():
    return [(0,1,-2,terms(),terms()),(1,2,0,terms(2),terms(2)),
            (2,0,0,terms(2),terms(2))]


def fixture(seed,size=12):
    rng = random.Random(seed)
    pairs = {tuple(sorted((i,(i+1)%size))) for i in range(size)}
    pairs.update((a,b) for a in range(size) for b in range(a+1,size) if rng.random()<.2)
    edges = [(a,b,rng.randint(-6,6),terms(rng.choice([0,2,4])),terms(rng.choice([0,2,4])))
             for a,b in sorted(pairs)]
    arrivals = [(a,b,rng.choice([-2,-1,1,2]))
                for a,b in (rng.choice(sorted(pairs)) for _ in range(40))]
    return edges,arrivals


def run():
    rows = []
    for seed in range(8):
        edges,arrivals = fixture(seed)
        for temporal in (False,True):
            for policy in ('cancellation','comfort'):
                net = Network(edges,seed)
                initial = net.score()
                rejected = 0
                if temporal:
                    net.clear(policy,250)
                    for a,b,amount in arrivals:
                        rejected += not net.transfer(a,b,amount)
                        net.clear(policy,net.messages+250)
                else:
                    net.clear(policy,10250)
                expected = dict(net.initial_nets)
                for a,b,amount in net.external:
                    expected[a] += amount
                    expected[b] -= amount
                assert net.nets() == expected
                rows.append(dict(seed=seed,temporal=temporal,policy=policy,initial=initial,
                                 final=net.score(),rejected_transfers=rejected,
                                 offered_transfers=len(arrivals) if temporal else 0,
                                 accepted_transfers=len(net.external),
                                 fixture_sha256=hashlib.sha256(json.dumps([edges,arrivals],sort_keys=True).encode()).hexdigest(),
                                 receipt_sha256=hashlib.sha256(json.dumps(net.receipts).encode()).hexdigest()))
    examples = {}
    for policy in ('cancellation','comfort'):
        net = Network(illustrative())
        initial = net.score()
        net.clear(policy)
        examples[policy] = dict(initial=initial,final=net.score(),receipts=net.receipts)
    return dict(schema=1,complete=True,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                model_sha256=hashlib.sha256((Path(__file__).resolve().parents[1]/'app/comfort.py').read_bytes()).hexdigest(),
                config=dict(seeds=list(range(8)),nodes=12,static_budget=10250,temporal_arrivals=40,
                            per_arrival_budget=250,unit_move=1,faults='none; serialized reliable simulator'),
                illustrative=examples,rows=rows)


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,default=Path('experiments/results/comfort-simulation.json'))
    args=p.parse_args()
    args.output.write_text(json.dumps(run(),indent=2)+'\n')
