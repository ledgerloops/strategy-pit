"""Bounded-surplus headroom policy for honest neighbour-private participants.

This is an intentionally incomplete sufficient test for collective improvement.
The origin retains a strict reduction. Every other exposure-increasing participant
must consume a previously earned Boolean surplus; additional savings are discarded.
No total cost, remote identity or loop length is carried. Protocol code must bind
the transitions to immutable quotes and conditional hashlock approval.
"""
from comfort import MAX_AMOUNT, shared_comfort, validate_preferences


def _valid_amount(amount):
    return type(amount) is int and 0 < amount <= MAX_AMOUNT


def edge_allowed(before, after, own, remote):
    """Bilateral automatic comfort permission without crossing through zero.

    An endpoint at zero is allowed; a step through zero is not. Consequently the
    finite change of absolute exposure is exactly plus or minus the step amount.
    """
    if any(type(value) is not int or abs(value) > MAX_AMOUNT for value in (before, after)):
        return False
    if not _valid_amount(abs(after-before)) or before * after < 0:
        return False
    try:
        own, remote = validate_preferences(own), validate_preferences(remote)
        zone = shared_comfort(own, remote)
    except ValueError:
        return False
    return (own['auto_adjust'] and remote['auto_adjust'] and not zone['empty']
            and zone['min'] <= after <= zone['max'])


def advance_surplus(incoming, cost, amount, origin=False):
    """Return the outgoing surplus bit or reject an unsupported transition.

    Origin savings are never offered as surplus: this leaves a strict reduction
    after matching every accepted helper increase. An origin evaluating closure
    may receive either bit; it starts a new outgoing traversal with False.
    """
    if type(incoming) is not bool or type(origin) is not bool or not _valid_amount(amount):
        raise ValueError('Boolean surplus and bounded integer amount required')
    if type(cost) is not int or cost not in (-2*amount, 0, 2*amount):
        raise ValueError('Unsupported local exposure change')
    if origin:
        if cost != -2*amount:
            raise ValueError('Origin must retain a strict local reduction')
        return False
    if cost < 0:
        return True
    if cost > 0:
        if not incoming:
            raise ValueError('No surplus available for increased exposure')
        return False
    return incoming


def pair_surplus(changes, amount, incoming=False, origin=False):
    """Validate two incident-edge quotes and compute their surplus transition."""
    if not _valid_amount(amount) or not isinstance(changes, (list, tuple)) or len(changes) != 2:
        raise ValueError('Two edge quotes and bounded integer amount required')
    required = {'peer', 'before', 'after', 'own_preferences', 'peer_preferences'}
    if any(not isinstance(change, dict) or not required <= change.keys() for change in changes):
        raise ValueError('Complete local edge quotes required')
    peers = [change['peer'] for change in changes]
    if any(not isinstance(peer, str) or not peer for peer in peers) or peers[0] == peers[1]:
        raise ValueError('Distinct direct neighbours required')
    for change in changes:
        if not edge_allowed(change['before'], change['after'],
                            change['own_preferences'], change['peer_preferences']):
            raise ValueError('Outside bilateral headroom permission')
        if abs(change['after']-change['before']) != amount:
            raise ValueError('Quote amount mismatch')
    if sum(change['after']-change['before'] for change in changes) != 0:
        raise ValueError('Local net position must be conserved')
    cost = sum(abs(change['after'])-abs(change['before']) for change in changes)
    return advance_surplus(incoming, cost, amount, origin)
