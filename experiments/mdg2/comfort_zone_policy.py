"""Conditional local consent for comfort-zone clearing; research only.

No discovery, settlement, aggregate-benefit oracle or historical gain budget.
An agreed zero-balance direct trustline can supply headroom. A true predicate
is not authorization to release a hashlock: the full loop must also improve
total debt and use valid immutable quotes/reservations. Existing automatic-
assistance opt-outs are respected. Production modules are unchanged.
"""
from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[2] / 'app'
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))
from comfort import MAX_AMOUNT, shared_comfort, validate_preferences

POLICY = 'comfort-zone-conditional-v1'


def locally_willing(changes):
    """Two own incident-edge changes, with published bilateral preferences.

    Caller obtains edges/balances from its own authenticated local records.
    Consent imposes no nonexpansion or historical-balance restriction. Both
    endpoints must have enabled automatic assistance; interval permission alone
    does not override an existing opt-out. No remote path data is accepted.
    """
    if len(changes) != 2 or changes[0]['peer'] == changes[1]['peer']:
        return False
    if any(type(c[key]) is not int or abs(c[key]) > MAX_AMOUNT
           for c in changes for key in ('before', 'after')):
        return False
    if any(c['before'] == c['after'] for c in changes):
        return False
    if sum(c['after'] - c['before'] for c in changes) != 0:
        return False
    for c in changes:
        own = validate_preferences(c['own_preferences'])
        peer = validate_preferences(c['peer_preferences'])
        zone = shared_comfort(own, peer)
        if not own['auto_adjust'] or not peer['auto_adjust']:
            return False
        if zone['empty'] or not zone['min'] <= c['after'] <= zone['max']:
            return False
    return True


def local_exposure_delta(changes):
    """Actual finite change; marginal unit costs cannot price a zero crossing."""
    return sum(abs(c['after']) - abs(c['before']) for c in changes)
