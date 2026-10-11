#!/usr/bin/env python3
"""Check local receipt hash/accounting consistency; not signatures or remote finality."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(value):
    receipt = value.get('receipt', value)
    if not isinstance(receipt, dict):
        raise ValueError('Receipt must be an object')
    expected = {'protocol': 'private-hashlock-v2', 'hashlock_scheme': 'sha256-context-v2',
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
    digest = hashlib.sha256(json.dumps(context, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest()
    if digest != receipt['condition']:
        raise ValueError('Preimage does not fulfill the context-bound hashlock')
    changes = receipt.get('changes')
    if not isinstance(changes, list) or len(changes) != 2:
        raise ValueError('Expected two local balance changes')
    peers, deltas = set(), []
    for change in changes:
        peer = change.get('peer')
        if not isinstance(peer, str) or not peer or peer in peers:
            raise ValueError('Expected distinct local neighbours')
        peers.add(peer)
        before, after = change.get('before'), change.get('after')
        if type(before) is not int or type(after) is not int or max(abs(before), abs(after)) > 10**12:
            raise ValueError('Invalid local balance')
        if abs(before) - abs(after) != amount or before * after < 0:
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
