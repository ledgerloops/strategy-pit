"""Independent offline checks for actual neighbour-private v2 stream evidence.

This module imports neither participant code nor its receipt verifier.  Global
endpoint/receipt matching here is observational audit, never a routing input.
"""
from collections import defaultdict
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path

POLICIES = {'bilateral-comfort-v1': 'sha256-comfort-v1',
            'private-local-nonexpansion-v1': 'sha256-private-local-nonexpansion-v1'}


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def canonical_hex(value):
    return isinstance(value, str) and len(value) == 64 and set(value) <= set('0123456789abcdef')


def endpoint_metrics(balances):
    """Count debtor-owned local balances, retaining non-atomic mirror gaps."""
    debt = 0
    pairs = {}
    for node, links in balances.items():
        for peer, balance in links.items():
            assert node != peer and peer in balances and node in balances[peer]
            assert type(balance) is int
            debt += max(-balance, 0)
            pair = tuple(sorted((node, peer)))
            pairs[pair] = balances[pair[0]][pair[1]] + balances[pair[1]][pair[0]]
    return dict(debt=debt, original_trustlines=len(pairs),
                mirror_mismatches=sum(value != 0 for value in pairs.values()),
                absolute_mirror_gap=sum(abs(value) for value in pairs.values()))


def check_wire(source, target, payload, neighbours):
    """Allowlist actual v2 content; transport endpoint metadata stays external."""
    assert target in neighbours[source] and source in neighbours[target]
    assert payload.get('protocol') == 'private-hashlock-v2'
    assert isinstance(payload.get('message_id'), str) and 1 <= len(payload['message_id']) <= 128
    if payload.get('kind') == 'preferences':
        assert set(payload) == {'kind', 'protocol', 'preferences', 'message_id'}
        preferences(payload['preferences'])
        return
    if str(payload.get('kind', '')).startswith('obligation_'):
        check_obligation_wire(source, target, payload)
        return
    allowed = {'kind', 'id', 'condition', 'amount', 'protocol', 'message_id',
               'preimage', 'clearing_mode', 'policy', 'direction', 'edge_quote'}
    assert not set(payload) - allowed, 'Unexpected protocol-visible fields'
    assert payload.get('kind') in {'probe', 'probe_rejected', 'prepare', 'ready', 'reject', 'abort', 'fulfill'}
    assert canonical_hex(payload.get('id')) and canonical_hex(payload.get('condition'))
    assert type(payload.get('amount')) is int and 0 < payload['amount'] <= 10**12
    comfort = payload.get('clearing_mode') == 'comfort'
    if comfort:
        assert payload.get('policy') in POLICIES
        assert type(payload.get('direction')) is int and payload['direction'] in (-1, 1)
        assert ('edge_quote' in payload) == (payload['kind'] in {'probe', 'prepare'})
        if 'edge_quote' in payload:
            quote = payload['edge_quote']
            assert set(quote) == {'before', 'after', 'own_revision', 'peer_revision'}
            assert all(type(value) is int for value in quote.values())
            assert quote['after'] - quote['before'] == payload['direction'] * payload['amount']
    else:
        assert not set(payload) & {'clearing_mode', 'policy', 'direction', 'edge_quote'}
    assert ('preimage' in payload) == (payload['kind'] == 'fulfill')
    if payload['kind'] == 'fulfill':
        check_hashlock(payload)


def preferences(value):
    assert isinstance(value, dict)
    assert set(value) == {'revision', 'credit_limit', 'comfort_min', 'comfort_max', 'auto_adjust'}
    assert all(type(value[key]) is int for key in ('revision', 'credit_limit', 'comfort_min', 'comfort_max'))
    assert 1 <= value['revision'] <= 10**12 and 0 <= value['credit_limit'] <= 10**12
    assert -10**12 <= value['comfort_min'] <= value['comfort_max'] <= 10**12
    assert type(value['auto_adjust']) is bool


def economic_terms(before, after, own, peer):
    preferences(own)
    preferences(peer)
    reducing = (before > 0 and 0 <= after < before) or (before < 0 and before < after <= 0)
    assert reducing or -peer['credit_limit'] <= after <= own['credit_limit']
    low = max(own['comfort_min'], -peer['comfort_max'], -peer['credit_limit'])
    high = min(own['comfort_max'], -peer['comfort_min'], own['credit_limit'])
    assert low <= high
    old = max(low-before, before-high, 0)
    new = max(low-after, after-high, 0)
    assert new <= old
    assert not (new == old or abs(after) > abs(before)) or (own['auto_adjust'] and peer['auto_adjust'])
    return dict(hard_min=-peer['credit_limit'], hard_max=own['credit_limit'], min=low, max=high, empty=False), old, new


def check_hashlock(value):
    assert all(canonical_hex(value.get(key)) for key in ('id', 'condition', 'preimage'))
    assert value.get('protocol') == 'private-hashlock-v2'
    assert type(value.get('amount')) is int and 0 < value['amount'] <= 10**12
    context = {key: value[key] for key in ('id', 'amount', 'preimage', 'protocol')}
    context['unit'] = 'TEST'
    if value.get('clearing_mode') == 'comfort':
        assert value.get('policy') in POLICIES
        assert type(value.get('direction')) is int and value['direction'] in (-1, 1)
        context.update(clearing_mode='comfort', policy=value['policy'], direction=value['direction'])
    assert hashlib.sha256(compact(context)).hexdigest() == value['condition'], 'Invalid context-bound preimage'


def verify_local_receipt(receipt):
    check_hashlock(receipt)
    comfort = receipt.get('clearing_mode') == 'comfort'
    assert receipt.get('hashlock_scheme') == (POLICIES[receipt['policy']] if comfort else 'sha256-context-v2')
    assert receipt.get('status') == 'committed' and receipt.get('local_fulfilled') is True
    assert receipt.get('mode') == 'testnet' and receipt.get('unit') == 'TEST'
    assert isinstance(receipt.get('node'), str)
    changes = receipt.get('changes')
    assert isinstance(changes, list) and len(changes) == 2
    assert len({change['peer'] for change in changes}) == 2
    amount, delta_sum = receipt['amount'], 0
    for index, change in enumerate(changes):
        before, after = change['before'], change['after']
        assert type(before) is int and type(after) is int
        assert max(abs(before), abs(after)) <= 10**12 and abs(after-before) == amount
        if comfort:
            assert after-before == (-1 if index == 0 else 1)*receipt['direction']*amount
            assert receipt['incoming_quote' if index == 0 else 'outgoing_quote'] == change
            own, peer = change['own_preferences'], change['peer_preferences']
            assert change['own_revision'] == own['revision'] and change['peer_revision'] == peer['revision']
            zone, old, new = economic_terms(before, after, own, peer)
            assert change['shared_comfort'] == zone
            assert (change['discomfort_before'], change['discomfort_after']) == (old, new)
        else:
            assert abs(before)-abs(after) == amount and before*after >= 0
        delta_sum += after-before
    assert delta_sum == 0, 'Local net position changed'
    if receipt.get('policy') == 'private-local-nonexpansion-v1':
        assert sum(abs(c['after'])-abs(c['before']) for c in changes) <= 0, 'Local nonexpansion policy violated'
    # These fields are added only after the immutable proposal was approved.
    added = {'digest', 'status', 'node', 'mode', 'unit', 'local_fulfilled', 'decided_at', 'preimage'}
    proposal = {key: value for key, value in receipt.items() if key not in added}
    assert hashlib.sha256(compact(proposal)).hexdigest() == receipt.get('digest'), 'Approval digest does not bind receipt terms'
    return dict(id=receipt['id'], node=receipt['node'], local_net_delta=delta_sum)


def check_obligation_wire(source, target, payload):
    kind = payload['kind']
    expected = {'kind', 'protocol', 'id', 'digest', 'message_id'}
    if kind == 'obligation_offer':
        expected.add('terms')
    elif kind == 'obligation_reject':
        expected.add('reason')
        assert isinstance(payload['reason'], str) and len(payload['reason']) <= 200
    else:
        assert kind in {'obligation_accept', 'obligation_commit', 'obligation_settled'}
    assert set(payload) == expected
    assert canonical_hex(payload['id']) and canonical_hex(payload['digest'])
    if kind == 'obligation_offer':
        terms = payload['terms']
        assert set(terms) == {'scheme', 'protocol', 'unit', 'id', 'origin', 'recipient', 'amount',
                              'direction', 'description', 'before', 'after', 'origin_revision',
                              'recipient_revision', 'created_at'}
        assert terms['scheme'] == 'bilateral-obligation-v1'
        assert terms['protocol'] == 'private-hashlock-v2' and terms['unit'] == 'TEST'
        assert terms['id'] == payload['id'] and (terms['origin'], terms['recipient']) == (source, target)
        assert type(terms['amount']) is int and 0 < terms['amount'] <= 10**12
        assert type(terms['before']) is int and type(terms['after']) is int
        assert terms['direction'] in ('i_owe', 'peer_owes')
        assert terms['after']-terms['before'] == (-1 if terms['direction'] == 'i_owe' else 1)*terms['amount']
        assert hashlib.sha256(compact(terms)).hexdigest() == payload['digest']


def verify_local_obligation(node, value, terms, digest):
    """Verify an actually-applied endpoint against the bilateral offer context."""
    assert node in (terms['origin'], terms['recipient'])
    origin = node == terms['origin']
    peer = terms['recipient'] if origin else terms['origin']
    sign = 1 if origin else -1
    assert value['id'] == terms['id'] and value['peer'] == peer
    assert value['origin'] is origin and value['approved'] is True
    assert value['applied_at'] is not None and value['status'] in ('committing', 'committed')
    assert value['digest'] == digest == hashlib.sha256(compact(terms)).hexdigest()
    assert value['before'] == sign*terms['before'] and value['after'] == sign*terms['after']
    assert value['amount'] == terms['amount'] and value['description'] == terms['description']
    assert value['unit'] == 'TEST'
    expected_direction = terms['direction'] if origin else ('peer_owes' if terms['direction'] == 'i_owe' else 'i_owe')
    assert value['direction'] == expected_direction
    return dict(node=node, peer=peer, before=value['before'], after=value['after'])


def match_fulfilled_operations(receipts):
    """Offline-only: distinguish fully matched local evidence from partial work."""
    groups = defaultdict(dict)
    for receipt in receipts:
        verify_local_receipt(receipt)
        group = groups[receipt['id']]
        assert receipt['node'] not in group, 'Duplicate local application'
        group[receipt['node']] = receipt
    completed, partial = [], []
    for ident, group in groups.items():
        complete = True
        for node, receipt in group.items():
            for change in receipt['changes']:
                other = group.get(change['peer'])
                if other is None:
                    complete = False
                    continue
                reverse = [c for c in other['changes'] if c['peer'] == node]
                assert len(reverse) == 1
                assert reverse[0]['before'] == -change['before'] and reverse[0]['after'] == -change['after']
                assert (receipt['condition'], receipt['amount'], receipt['preimage']) == (other['condition'], other['amount'], other['preimage'])
        if complete:
            assert len(group) >= 3, 'A complete operation must have at least three distinct honest identities'
            seen, pending = set(), [next(iter(group))]
            while pending:
                node = pending.pop()
                if node in seen:
                    continue
                seen.add(node)
                pending.extend(change['peer'] for change in group[node]['changes'])
            assert seen == set(group), 'One opaque operation cannot comprise disconnected cycles'
            if next(iter(group.values())).get('policy') == 'private-local-nonexpansion-v1':
                assert sum(abs(c['after'])-abs(c['before']) for r in group.values() for c in r['changes']) < 0, 'Completed research operation must strictly reduce gross debt'
        (completed if complete else partial).append(ident)
    return dict(completed_operations=completed, partial_operations=partial)


def audit_run(run):
    """Replay actual endpoint journals and transport, without a global commit.

    Returns failures rather than hiding incomplete financial operations.  Pending
    reservations are observations: stage snapshots are not part of this journal.
    """
    failures = []
    ledger = deepcopy(run['initial_balances'])
    neighbours = {node: set(links) for node, links in ledger.items()}
    metrics = endpoint_metrics(ledger)
    assert metrics['mirror_mismatches'] == 0
    assert metrics['original_trustlines'] == run['original_trustlines']
    for node, links in run['initial_preferences'].items():
        assert set(links) == neighbours[node]
        for value in links.values():
            preferences(value)
    events, trace = run['events'], run['trace']
    if len(events) != len(trace):
        failures.append('Event and trace lengths differ')
    requests, delivered, acknowledgements, ack_requests = {}, {}, {}, {}
    successful_acks = set()
    sent_ids, inflight = defaultdict(int), set()
    approvals, obligation_approvals, submissions = {}, {}, {}
    terms_by_id, origins, offers, accepted = {}, {}, {}, {}
    applied_obligations, applied_receipts, receipts = set(), set(), []
    kinds = defaultdict(int)
    counts = dict(requests=0, request_bytes=0, deliveries=0, delivery_failures=0,
                  acknowledgements=0, acknowledgement_bytes=0, delivered_acknowledgements=0, lost_acknowledgements=0,
                  lost_requests=0, local_fulfillments=0, local_obligation_applications=0)
    previous_time = -1
    for index, event in enumerate(events):
        try:
            assert event['time'] >= previous_time
            previous_time = event['time']
            kind = event['kind']
            if kind in ('request', 'message'):
                source, target, payload = event['source'], event['target'], event['payload']
                assert json.loads(event['raw_json']) == payload
                assert len(event['raw_json'].encode('utf-8')) == event['bytes']
                check_wire(source, target, payload, neighbours)
                if kind == 'request':
                    counts['requests'] += 1
                    counts['request_bytes'] += event['bytes']
                    assert event['attempt'] == counts['requests']
                    requests[event['attempt']] = (source, target, event['raw_json'])
                    key = (source, payload['message_id'])
                    assert event['retry'] is (sent_ids[key] > 0)
                    sent_ids[key] += 1
                    inflight.add(key)
                    kinds[payload['kind']] += 1
                    if payload['kind'] == 'obligation_offer':
                        old = terms_by_id.setdefault(payload['id'], (payload['terms'], payload['digest']))
                        assert old == (payload['terms'], payload['digest'])
                else:
                    assert event['attempt'] in requests and event['attempt'] not in delivered
                    assert requests[event['attempt']] == (source, target, event['raw_json'])
                    delivered[event['attempt']] = event
                    assert type(event['ok']) is bool
                    counts['deliveries' if event['ok'] else 'delivery_failures'] += 1
                    if not event['ok']:
                        assert not event.get('balance_changes') and not event.get('local_receipts')
            elif kind in ('ack_request', 'ack'):
                assert event['attempt'] in delivered
                delivery = delivered[event['attempt']]
                assert (event['source'], event['target']) == (delivery['target'], delivery['source'])
                assert event['id'] == delivery['payload']['message_id'] and event['ok'] is delivery['ok']
                body = {'ok': True} if event['ok'] else {'error': delivery['error']}
                assert json.loads(event['raw_json']) == body
                assert len(event['raw_json'].encode('utf-8')) == event['bytes']
                if kind == 'ack_request':
                    assert event['attempt'] not in ack_requests
                    ack_requests[event['attempt']] = event
                    counts['acknowledgements'] += 1
                    counts['acknowledgement_bytes'] += event['bytes']
                else:
                    assert event['attempt'] in ack_requests and event['attempt'] not in acknowledgements
                    assert ack_requests[event['attempt']]['raw_json'] == event['raw_json']
                    acknowledgements[event['attempt']] = event
                    counts['lost_acknowledgements'] += int(event['lost'])
                    counts['delivered_acknowledgements'] += int(not event['lost'])
                    if event['ok'] and not event['lost']:
                        successful_acks.add((event['target'], event['id']))
            elif kind == 'outbox_acknowledged':
                key = (event['node'], event['id'])
                assert key in inflight
                assert key in successful_acks
                successful_acks.remove(key)
                inflight.remove(key)
            elif kind == 'request_lost':
                assert event['attempt'] in requests and event['attempt'] not in delivered
                assert requests[event['attempt']][0] == event['source']
                counts['lost_requests'] += 1
            elif kind == 'local_approval':
                assert event['accepted'] is True and canonical_hex(event['digest'])
                key = (event['node'], event['id'])
                assert key not in approvals
                approvals[key] = event['digest']
            elif kind == 'obligation_approval':
                assert event['accepted'] is True and canonical_hex(event['digest'])
                key = (event['node'], event['id'])
                assert key not in obligation_approvals
                obligation_approvals[key] = event['digest']
            elif kind == 'discover':
                assert event['id'] not in origins
                origins[event['id']] = event['node']
            elif kind == 'offer':
                assert event['offer_id'] not in offers and event['b'] in neighbours[event['a']]
                assert type(event['amount']) is int and event['amount'] != 0
                offers[event['offer_id']] = event
            elif kind == 'offer_attempt':
                assert event['offer_id'] in offers
                submissions[(event['node'], event['attempt_id'])] = event['digest']
            elif kind == 'offer_accepted':
                assert event['offer_id'] in offers and event['offer_id'] not in accepted
                accepted[event['offer_id']] = event['attempt_id']
            expected_changes = []
            for item in event.get('local_receipts', []):
                node, receipt = item['node'], item['receipt']
                assert node == receipt['node'] and node in neighbours
                verify_local_receipt(receipt)
                key = (node, receipt['id'])
                assert key not in applied_receipts and approvals.get(key) == receipt['digest']
                assert receipt['id'] in origins
                for change in receipt['changes']:
                    assert change['peer'] in neighbours[node]
                    expected_changes.append(dict(node=node, **{k: change[k] for k in ('peer', 'before', 'after')}))
                if receipt.get('policy') == 'private-local-nonexpansion-v1' and origins[receipt['id']] == node:
                    assert sum(abs(c['after'])-abs(c['before']) for c in receipt['changes']) < 0
                    assert abs(receipt['changes'][1]['after']) < abs(receipt['changes'][1]['before'])
                receipts.append(receipt)
                applied_receipts.add(key)
                counts['local_fulfillments'] += 1
            for item in event.get('local_obligations', []):
                node, value = item['node'], item['obligation']
                if value['applied_at'] is None:
                    continue
                key = (node, value['id'])
                assert value['id'] in terms_by_id
                terms, digest = terms_by_id[value['id']]
                change = verify_local_obligation(node, value, terms, digest)
                consent = submissions if value['origin'] else obligation_approvals
                assert consent.get(key) == digest, 'Missing prior exact local obligation consent'
                if key not in applied_obligations:
                    expected_changes.append(change)
                    applied_obligations.add(key)
                    counts['local_obligation_applications'] += 1
            changes = event.get('balance_changes', [])
            order = lambda value: (value['node'], value['peer'])
            assert sorted(changes, key=order) == sorted(expected_changes, key=order), 'Ledger change lacks actual local application evidence'
            for change in changes:
                node, peer = change['node'], change['peer']
                assert ledger[node][peer] == change['before'], 'Local journal before-state mismatch'
                ledger[node][peer] = change['after']
            row = trace[index]
            assert row['event_end_index'] == index+1 and row['time'] == event['time']
            for key, value in endpoint_metrics(ledger).items():
                if key != 'original_trustlines':
                    assert row[key] == value, 'Endpoint trace mismatch: '+key
            assert event['messages'] == row['messages'] == counts['requests']
            assert event['message_bytes'] == row['message_bytes'] == counts['request_bytes']
            assert event['acknowledgements'] == row['acknowledgements'] == counts['acknowledgements']
            assert event['ack_body_bytes'] == row['ack_body_bytes'] == counts['acknowledgement_bytes']
            assert row['delivered_messages'] == counts['deliveries']
            assert row['pending_messages'] == len(inflight)
            assert row['offered'] == len(offers) and row['accepted_offers'] == len(accepted)
            assert row['offer_backlog'] == len(offers)-len(accepted)
            for key in ('reservations', 'outbox', 'unresolved_proposals', 'unresolved_obligations'):
                assert type(row[key]) is int and row[key] >= 0
        except (AssertionError, KeyError, TypeError, ValueError) as error:
            if len(failures) < 100:
                failures.append(f'event {index} ({event.get("kind")}): {error or type(error).__name__}')
    try:
        assert ledger == run['final_balances']
        assert counts['requests'] == run['messages'] and counts['request_bytes'] == run['message_bytes']
        assert counts['deliveries'] == run['delivered_messages']
        assert counts['delivery_failures'] == run['delivery_failures']
        assert counts['acknowledgements'] == run['acknowledgements']
        assert counts['acknowledgement_bytes'] == run['ack_body_bytes']
        assert counts['delivered_acknowledgements'] == run['delivered_acknowledgements']
        assert counts['lost_acknowledgements'] == run['dropped_acknowledgements']
        assert counts['lost_requests'] <= run['dropped_requests']  # A request may be lost beyond the finite horizon.
        assert sum(max(0, value-1) for value in sent_ids.values()) == run['retried_requests']
        assert dict(kinds) == run['message_kinds']
        assert run['final'] == trace[-1]
        assert {item['offer_id']: item['attempt_id'] for item in run['accepted_offers']} == accepted
        matches = match_fulfilled_operations(receipts)
    except (AssertionError, KeyError, TypeError, ValueError) as error:
        failures.append('final: '+str(error or type(error).__name__))
        matches = dict(completed_operations=[], partial_operations=[])
    return dict(independent_audit_passed=not failures, failures=failures,
                events_checked=len(events), **counts,
                completed_hashlock_cycles=len(matches['completed_operations']),
                partial_hashlock_operations=len(matches['partial_operations']),
                fully_applied_obligations=sum(sum((node, ident) in applied_obligations for node in neighbours) == 2 for ident in terms_by_id),
                offers_observed=len(offers), client_accepted_offers=len(accepted),
                final_endpoint_metrics=endpoint_metrics(ledger),
                limits='Local-stage reservation/unresolved counts are observational. Receipt evidence assumes honest isolated-process journals, not signatures. Global matching is offline only; no optimality or anonymity certificate.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    results = json.loads(args.results.read_text())
    assert results.get('complete') is True
    audits = [audit_run(run) for run in results['runs']]
    result = dict(independent_audit_passed=all(a['independent_audit_passed'] for a in audits),
                  results_sha256=hashlib.sha256(args.results.read_bytes()).hexdigest(),
                  auditor_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  runs_checked=len(audits), run_audits=audits)
    destination = args.output or args.results.with_name('independent-audit.json')
    destination.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'run_audits'}, indent=2))
    if not result['independent_audit_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
