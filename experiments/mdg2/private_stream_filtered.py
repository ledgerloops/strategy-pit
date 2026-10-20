"""Uniform local pair-cost filtering for neighbour-private hashlock discovery.

Prospective research variant, chosen after the original development campaign
started. It changes discovery only, under exactly the original hash-bound
private-local-nonexpansion-v1 consent. Before forwarding a comfort probe, each
node uses its own incoming balance and candidate outgoing balance to reject a
pair which its eventual prepare_local would necessarily refuse. All admissible
neighbours remain uniformly shuffled; no debt-first priority or new consent rule.
This does not prove completeness, remove concurrency staleness, or relax the
origin's strict debt-reduction rule. Production and frozen baseline files remain
unchanged. The frozen baseline source is an explicit dependency.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import secrets
import tempfile

from private_stream import (PrivateStream, NonexpandingPrivateNode, LocalActor,
                            seeded, COMFORT_POLICY)
from comfort import comfort_move

DISCOVERY_VERSION = 'local-pair-filter-v1'
METHOD = 'private_nonexpansion_filtered'


class FilteredNonexpandingNode(NonexpandingPrivateNode):
    """Reads only own balances/preferences/reservations and received predecessor."""
    def comfort_candidate(self, amount, direction, exclude=None, strict=False):
        if strict or exclude is None:
            return super().comfort_candidate(amount,direction,exclude,strict)
        if exclude not in self.peers:
            raise ValueError('Incoming direct neighbour required')
        delta = direction*amount
        incoming = self.balance(exclude)
        incoming_cost = abs(incoming-delta)-abs(incoming)
        eligible = []
        for peer in sorted(self.peers):
            if peer == exclude or self.db.execute('SELECT 1 FROM reservations WHERE peer=?',(peer,)).fetchone():
                continue
            before,after = self.balance(peer),self.balance(peer)+delta
            if incoming_cost+abs(after)-abs(before) > 0:
                continue
            try:
                term = self.edge_terms(peer,before,after)
            except ValueError:
                continue
            if comfort_move(before,after,term['own_preferences'],term['peer_preferences']):
                eligible.append(peer)
        self.choice_rng.shuffle(eligible)
        return eligible[0] if eligible else None


class FilteredPrivateStream(PrivateStream):
    """Same async transport/journal; only construction chooses the filtered node.

    __init__ is a static copy of the frozen adapter initializer, with the named
    method validated, original consent mode retained internally, and NodeClass
    selected at construction. There is no object-class patch or module-global
    factory mutation. All inherited scheduling/accounting stays unchanged.
    """
    def __init__(self, edges, seed=0, method='private_nonexpansion_filtered', *,
                 wake_mean=1., wire_delay=(.005,.015), retry_delay=.05,
                 discovery_until=30., message_cap=250000, directory=None,
                 drop_request_ids=(), drop_ack_ids=()):
        if method != 'private_nonexpansion_filtered':
            raise ValueError('Filtered adapter requires its named research method')
        method = 'private_nonexpansion'  # Same local consent automation/policy.
        if (wake_mean <= 0 or retry_delay <= 0 or len(wire_delay) != 2
                or not 0 <= wire_delay[0] <= wire_delay[1] or wire_delay[1] <= 0
                or type(message_cap) is not int or message_cap < 0):
            raise ValueError('Invalid finite transport configuration')
        self.method, self.seed = method, seed
        self.wake_mean, self.wire_delay, self.retry_delay = wake_mean, wire_delay, retry_delay
        self.discovery_until, self.message_cap = discovery_until, message_cap
        self._temporary = tempfile.TemporaryDirectory(prefix='ledgerloops-private-') if directory is None else None
        self.directory = Path(self._temporary.name if self._temporary else directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        if any(self.directory.glob('*.sqlite')):
            raise ValueError('Research adapter requires a fresh isolated directory')
        self.edges = [(str(a),str(b),balance,deepcopy(pa),deepcopy(pb)) for a,b,balance,pa,pb in edges]
        if not self.edges:
            raise ValueError('At least one trustline required')
        self.initial_balances, own = {}, {}
        pairs = set()
        for a,b,balance,pa,pb in self.edges:
            pair = tuple(sorted((a,b)))
            if a == b or pair in pairs or type(balance) is not int:
                raise ValueError('Distinct integer-valued trustlines required')
            pairs.add(pair)
            self.initial_balances.setdefault(a,{})[b] = balance
            self.initial_balances.setdefault(b,{})[a] = -balance
            own.setdefault(a,{})[b] = pa
            own.setdefault(b,{})[a] = pb
        self.initial_preferences = own
        self.actors = {}
        self.queue, self.serial = [], 0
        self.now, self.events, self.trace = 0., [], []
        self.messages, self.message_bytes, self.delivered, self.delivery_failures = 0,0,0,0
        self.acks, self.ack_bytes, self.delivered_acks, self.dropped_requests, self.dropped_acks = 0,0,0,0,0
        self.message_kinds = Counter()
        self.inflight = set()
        self.drop_request_ids, self.drop_ack_ids = set(drop_request_ids), set(drop_ack_ids)
        self.sent_per_id = Counter()
        self.censored, self.closed, self.runtime_seconds = False,False,0.
        self.offered_ids = set()
        self.endpoint_balances = deepcopy(self.initial_balances)
        self.node_stats = {}
        self._receipt_rowid, self._obligation_seen = {}, {}
        self.initialized_preferences = {}
        NodeClass = FilteredNonexpandingNode
        for name, balances in sorted(self.initial_balances.items()):
            config = dict(node=name, mode='testnet', token=secrets.token_hex(32), peers={
                peer:dict(balance=balance,url='http://isolated.invalid',key=secrets.token_hex(32))
                for peer,balance in balances.items()})
            database = self.directory / (hashlib.sha256(name.encode()).hexdigest()+'.sqlite')
            node = NodeClass(config,str(database),rng=seeded(seed,name,'choice'))
            self.actors[name] = LocalActor(node,seed,method,discovery_until)
            self._receipt_rowid[name] = 0
            self._obligation_seen[name] = {}
            self.initialized_preferences[name] = {}
            for peer,preferences in sorted(own[name].items()):
                values = {key:preferences[key] for key in ('credit_limit','comfort_min','comfort_max','auto_adjust')}
                node.set_preferences(peer,dict(values,expected_revision=1))
                self.initialized_preferences[name][peer] = dict(values,revision=2)
            self._capture(name, {})
        self._record(dict(kind='initial',time=0.))
        for name, actor in self.actors.items():
            self._schedule(actor.next_wakeup(wake_mean),'wake',name)
            self._pump(name)

    def result(self):
        result = super().result()
        result.update(method=METHOD,policy=COMFORT_POLICY,discovery_version=DISCOVERY_VERSION)
        return result
