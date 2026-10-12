#!/usr/bin/env python3
"""Check local receipt hash/accounting consistency; not signatures or remote finality."""
import argparse
import hashlib
import json
from pathlib import Path
from comfort import comfort_move, shared_comfort, discomfort


def verify(value):
    receipt = value.get('receipt', value)
    if not isinstance(receipt, dict):
        raise ValueError('Receipt must be an object')
    comfort=receipt.get('clearing_mode') == 'comfort'
    scheme='sha256-comfort-v1' if comfort else 'sha256-context-v2'
    expected = {'protocol': 'private-hashlock-v2', 'hashlock_scheme': scheme,
                'mode': 'testnet', 'unit': 'TEST', 'status': 'committed', 'local_fulfilled': True}
    for field, wanted in expected.items():
        if receipt.get(field) != wanted:
            raise ValueError(f'Unsupported or unfulfilled receipt: {field}')
    for field in ('id', 'condition', 'preimage'):
        text = receipt.get(field)
        if not isinstance(text, str) or len(text) != 64 or any(c not in '0123456789abcdef' for c in text):
            raise ValueError(f'Invalid canonical {field}')
    amount = receipt.get('amount')
    if type(amount) is not int or not 0 < amount <= 10**12:
        raise ValueError('Invalid amount')
    context = {key: receipt[key] for key in ('amount', 'id', 'preimage', 'protocol', 'unit')}
    if comfort:
        if receipt.get('policy') != 'bilateral-comfort-v1' or type(receipt.get('direction')) is not int or receipt['direction'] not in (-1,1):
            raise ValueError('Invalid comfort policy context')
        context.update(clearing_mode='comfort',policy=receipt['policy'],direction=receipt['direction'])
    elif any(key in receipt for key in ('clearing_mode','policy','direction')):
        raise ValueError('Unexpected cancellation policy context')
    digest = hashlib.sha256(json.dumps(context, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest()
    if digest != receipt['condition']:
        raise ValueError('Preimage does not fulfill the context-bound hashlock')
    changes = receipt.get('changes')
    if not isinstance(changes, list) or len(changes) != 2:
        raise ValueError('Expected two local balance changes')
    peers, deltas = set(), []
    for index,change in enumerate(changes):
        peer = change.get('peer')
        if not isinstance(peer, str) or not peer or peer in peers:
            raise ValueError('Expected distinct local neighbours')
        peers.add(peer)
        before, after = change.get('before'), change.get('after')
        if type(before) is not int or type(after) is not int or max(abs(before), abs(after)) > 10**12:
            raise ValueError('Invalid local balance')
        if abs(after-before) != amount:
            raise ValueError('Change amount differs from authorization')
        if comfort:
            expected_delta=(-1 if index == 0 else 1)*receipt['direction']*amount
            if after-before != expected_delta:
                raise ValueError('Local edge direction differs from hashlock authorization')
            quote_key='incoming_quote' if index == 0 else 'outgoing_quote'
            if receipt.get(quote_key) != change:
                raise ValueError('Local change differs from pinned edge quote')
            own,remote=change.get('own_preferences'),change.get('peer_preferences')
            for field in ('own_revision','peer_revision'):
                if type(change.get(field)) is not int or not 1 <= change[field] <= 10**12:
                    raise ValueError('Invalid preference revision')
            if any(not isinstance(p,dict) or type(p.get('revision')) is not int or not 1 <= p['revision'] <= 10**12 for p in (own,remote)):
                raise ValueError('Invalid pinned preference revision')
            if not comfort_move(before,after,own,remote):
                raise ValueError('Change violates pinned comfort permissions')
            zone=shared_comfort(own,remote)
            if change.get('shared_comfort') != zone or change.get('discomfort_before') != discomfort(before,zone) or change.get('discomfort_after') != discomfort(after,zone):
                raise ValueError('Comfort snapshot mismatch')
            if change.get('own_revision') != own.get('revision') or change.get('peer_revision') != remote.get('revision'):
                raise ValueError('Preference revision mismatch')
        elif abs(before) - abs(after) != amount or before * after < 0:
            raise ValueError('Change must reduce the same debt by the authorized amount')
        deltas.append(after-before)
    if sum(deltas) != 0:
        raise ValueError('Local signed net position changed')
    return {'valid': True, 'id': receipt['id'], 'scope': 'Hashlock and local accounting consistency only; no signature, actual-application or whole-loop proof.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt', type=Path)
    args = parser.parse_args()
    try:
        result = verify(json.loads(args.receipt.read_text()))
    except (ValueError, TypeError, KeyError, AttributeError, OSError) as error:
        parser.exit(1, f'INVALID: {error}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
