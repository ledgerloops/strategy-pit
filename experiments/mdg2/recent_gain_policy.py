"""Local conditional willingness to give back clearing gains, research only.

This is a serial settled-ledger model, not a settlement engine. A true result
means the node is willing IF aggregate improvement is privately established.
It does not authorize settlement, verify a hashlock, discover a loop or inspect
other nodes. Production integration, durable reservations and private benefit
verification remain separate work.
"""
from copy import deepcopy
from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[2] / 'app'
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))
from comfort import MAX_AMOUNT, comfort_move, validate_preferences


class RecentGainConsent:
    """Each direct trustline remembers its signed pre-clearing balance.

    No time expiry. Transactions/settings changes reset that edge's baseline.
    Clearing cannot raise a baseline, transfer allowance to another edge or
    recreate debt in the opposite direction. Current comfort/credit rules apply.
    Inputs contain only this node's incident balances and bilateral preferences.
    """

    def __init__(self, edges):
        self.edges = {}
        self.completed = {}
        for peer, (balance, own, remote) in edges.items():
            self._set_edge(peer, balance, own, remote)

    def _set_edge(self, peer, balance, own, remote):
        if type(balance) is not int or abs(balance) > MAX_AMOUNT:
            raise ValueError('Bounded integer balance required')
        self.edges[peer] = dict(balance=balance, baseline=balance,
                                own=validate_preferences(own),
                                remote=validate_preferences(remote))

    def willing(self, changes):
        """Check local conditional consent for a two-edge circulation step."""
        if len(changes) != 2 or any(peer not in self.edges for peer in changes):
            return False
        if any(type(after) is not int for after in changes.values()):
            return False
        if sum(after-self.edges[peer]['balance'] for peer, after in changes.items()) != 0:
            return False
        if any(after == self.edges[peer]['balance'] for peer, after in changes.items()):
            return False
        for peer, after in changes.items():
            edge = self.edges[peer]
            baseline = edge['baseline']
            if not min(0, baseline) <= after <= max(0, baseline):
                return False
            if not comfort_move(edge['balance'], after, edge['own'], edge['remote']):
                return False
        return True

    def observe_completed(self, operation_id, changes):
        """Replay an already completed clearing; not an approval/commit API.

        Callers must establish actual completion separately. Fixtures supply
        known transitions, never a graph-wide answer to a runtime participant.
        """
        if not isinstance(operation_id, str) or not operation_id:
            raise ValueError('Operation identifier required')
        if operation_id in self.completed:
            if self.completed[operation_id] != changes:
                raise ValueError('Operation identifier reused with different changes')
            return
        if not self.willing(changes):
            raise ValueError('Outside local conditional willingness')
        for peer, after in changes.items():
            self.edges[peer]['balance'] = after
        self.completed[operation_id] = deepcopy(changes)

    def observe_transaction(self, peer, balance):
        """A posted transaction starts a new epoch on this edge only.

        Caller supplies ordered, deduplicated postings; this model is not a
        wire-message ingestion API and does not authenticate external events.
        """
        edge = self.edges[peer]
        self._set_edge(peer, balance, edge['own'], edge['remote'])

    def update_preferences(self, peer, own, remote):
        """An effective change to either endpoint's settings resets allowance."""
        edge = self.edges[peer]
        own, remote = validate_preferences(own), validate_preferences(remote)
        if own != edge['own'] or remote != edge['remote']:
            self._set_edge(peer, edge['balance'], own, remote)
