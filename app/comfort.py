"""Pure bilateral signed-balance preferences; amounts are integer TEST units."""
MAX_AMOUNT = 10**12
FIELDS = ('credit_limit', 'comfort_min', 'comfort_max', 'auto_adjust')


def validate_preferences(value):
    if not isinstance(value, dict) or any(key not in value for key in FIELDS):
        raise ValueError('Complete credit limit, comfort interval and auto-adjust preference required')
    for key in FIELDS[:3]:
        if type(value[key]) is not int or abs(value[key]) > MAX_AMOUNT:
            raise ValueError('Preferences must use bounded integer TEST units')
    if value['credit_limit'] < 0 or value['comfort_min'] > value['comfort_max']:
        raise ValueError('Credit limit must be nonnegative and comfort interval ordered')
    if type(value['auto_adjust']) is not bool:
        raise ValueError('auto_adjust must be boolean')
    return {key: value[key] for key in FIELDS}


def shared_comfort(own, peer):
    own, peer = validate_preferences(own), validate_preferences(peer)
    hard_min, hard_max = -peer['credit_limit'], own['credit_limit']
    lower = max(own['comfort_min'], -peer['comfort_max'], hard_min)
    upper = min(own['comfort_max'], -peer['comfort_min'], hard_max)
    return dict(hard_min=hard_min, hard_max=hard_max, min=lower, max=upper, empty=lower > upper)


def allows_balance(before, after, own, peer=None):
    """Hard bounds, permitting strictly reducing an existing out-of-limit debt."""
    own = validate_preferences(own)
    if type(before) is not int or type(after) is not int or max(abs(before),abs(after)) > MAX_AMOUNT:
        return False
    if (before > 0 and 0 <= after < before) or (before < 0 and before < after <= 0):
        return True
    lower = -validate_preferences(peer)['credit_limit'] if peer is not None else 0
    return lower <= after <= own['credit_limit']


def discomfort(balance, zone):
    if zone['empty']:
        raise ValueError('Empty shared comfort interval')
    return max(zone['min']-balance, balance-zone['max'], 0)


def comfort_move(before, after, own, peer, strict=False):
    """Explicit bilateral assistance eligibility; never substitutes manual approval."""
    if peer is None or not allows_balance(before,after,own,peer):
        return False
    zone=shared_comfort(own,peer)
    if zone['empty']:
        return False
    old,new=discomfort(before,zone),discomfort(after,zone)
    if new > old or (strict and new >= old):
        return False
    if new == old or abs(after) > abs(before):
        return own['auto_adjust'] and peer['auto_adjust']
    return True
