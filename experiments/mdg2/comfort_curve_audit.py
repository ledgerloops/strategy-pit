"""Independent offline audit of signed comfort/headroom message-curve evidence.

No actor, benchmark replay, app comfort, NetworkX or oracle solver is imported.
Run only after results.json is complete; this does not run performance workloads.
"""
from collections import defaultdict
import argparse
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def canonical(a, b):
    assert a != b
    return ((a,b), 1) if a < b else ((b,a), -1)


def snapshot(items):
    ledger = {}
    for item in items:
        pair, sign = canonical(item['source'], item['target'])
        assert pair not in ledger and type(item['balance']) is int
        ledger[pair] = sign*item['balance']
    return ledger


def positions(ledger):
    result = defaultdict(int)
    for (a,b), balance in ledger.items():
        result[a] += balance
        result[b] -= balance
    return {node: amount for node, amount in result.items() if amount}


def bounds_zone(own, peer):
    lower, upper = -peer['credit_limit'], own['credit_limit']
    low = max(own['comfort_min'], -peer['comfort_max'], lower)
    high = min(own['comfort_max'], -peer['comfort_min'], upper)
    return lower, upper, low, high


def distance(balance, low, high):
    assert low <= high
    return max(low-balance, balance-high, 0)


def permitted(before, after, own, peer, policy):
    lower, upper, low, high = bounds_zone(own, peer)
    if not lower <= after <= upper:
        return False
    if policy == 'cancellation':
        return abs(after) < abs(before)
    assert policy == 'comfort_headroom'
    if low > high:
        return False
    old, new = distance(before,low,high), distance(after,low,high)
    if new > old:
        return False
    return not (new == old or abs(after) > abs(before)) or (own['auto_adjust'] and peer['auto_adjust'])


def initial(case):
    ledger, preferences = {}, {}
    for edge in case['edges']:
        pair, sign = canonical(edge['a'], edge['b'])
        assert pair not in ledger and type(edge['balance']) is int
        ledger[pair] = sign*edge['balance']
        preferences[pair] = (edge['own'], edge['peer']) if sign == 1 else (edge['peer'], edge['own'])
    return ledger, preferences


def view_preferences(preferences, a, b):
    pair, sign = canonical(a,b)
    own, peer = preferences[pair]
    return (own,peer) if sign == 1 else (peer,own)


def check_bounds(ledger, preferences):
    for pair, balance in ledger.items():
        own, peer = preferences[pair]
        assert -peer['credit_limit'] <= balance <= own['credit_limit']


def gross(ledger):
    return sum(abs(balance) for balance in ledger.values())


def discomfort(ledger, preferences):
    total = 0
    for pair, balance in ledger.items():
        _, _, low, high = bounds_zone(*preferences[pair])
        total += distance(balance, low, high)
    return total


def apply_receipt(ledger, preferences, receipt):
    path, changes, policy = receipt['path'], receipt['changes'], receipt['policy']
    assert len(path) >= 3 and len(set(path)) == len(path)
    assert len(changes) == len(path)
    assert abs(changes[0][3]) < abs(changes[0][2]), 'Initiation must use an actual debt-reducing edge'
    before_positions, before_gross = positions(ledger), gross(ledger)
    quotes, assisted, delta = [], False, 0
    for (a,b,old,new), (expected_a,expected_b) in zip(changes, zip(path,path[1:]+path[:1])):
        assert (a,b) == (expected_a,expected_b)
        pair, sign = canonical(a,b)
        assert pair in ledger and type(old) is int and type(new) is int
        assert old == sign*ledger[pair] and new == old+1
        own, peer = view_preferences(preferences,a,b)
        assert permitted(old,new,own,peer,policy), 'Tail rejected the advertised policy move'
        assert permitted(-old,-new,peer,own,policy), 'Head rejected the mirrored policy move'
        quotes.append(dict(source=a,target=b,before=old,after=new,own=own,other=peer))
        delta += abs(new)-abs(old)
        assisted |= abs(new)>abs(old)
        ledger[pair] = sign*new
    assert delta == receipt['gross_delta'] < 0
    assert gross(ledger)-before_gross == delta and positions(ledger) == before_positions
    check_bounds(ledger,preferences)
    transaction = dict(id=receipt['id'],policy=policy,path=path,quotes=quotes,gross_delta=delta)
    assert hashlib.sha256(compact(transaction)).hexdigest() == receipt['digest']
    return assisted


def apply_transfer(ledger, preferences, event):
    pair, sign = canonical(event['a'],event['b'])
    assert pair in ledger and type(event['amount']) is int and event['amount'] != 0
    ledger[pair] += sign*event['amount']
    check_bounds(ledger,preferences)


def certify_optimum(case, oracle):
    ledger, preferences = initial(case)
    if oracle['mode'] == 'arrivals':
        for arrival in case['arrivals']:
            apply_transfer(ledger,preferences,arrival)
    assert ledger == snapshot(oracle['reference'])
    optimum = snapshot(oracle['optimum'])
    assert set(optimum) == set(ledger) and positions(optimum) == positions(ledger)
    check_bounds(optimum,preferences)
    capacities = {}
    for (a,b), (own,peer) in preferences.items():
        capacities[b,a] = own['credit_limit']
        capacities[a,b] = peer['credit_limit']
    flows = dict.fromkeys(capacities,0)
    supplied = set()
    for arc in oracle['directed_flows']:
        pair = (arc['source'],arc['target'])
        assert pair in flows and pair not in supplied
        assert type(arc['amount']) is int and 0 < arc['amount'] <= capacities[pair]
        supplied.add(pair)
        flows[pair] = arc['amount']
    for a,b in ledger:
        assert not (flows[a,b] and flows[b,a])
        assert optimum[a,b] == flows[b,a]-flows[a,b]
    incoming = defaultdict(int)
    for (a,b), amount in flows.items():
        incoming[a] -= amount
        incoming[b] += amount
    assert {n:v for n,v in incoming.items() if v} == positions(ledger)
    assert sum(flows.values()) == gross(optimum) == oracle['minimum_gross']
    assert gross(ledger) == oracle['reference_gross']
    assert oracle['potential'] == gross(ledger)-gross(optimum) >= 0
    # Independent min-cost-flow dual certificate, retaining parallel residual arcs.
    residual = []
    for (a,b), capacity in capacities.items():
        if flows[a,b] < capacity:
            residual.append((a,b,1))
        if flows[a,b] > 0:
            residual.append((b,a,-1))
    potentials = {node:0 for node in case['nodes']}
    for iteration in range(len(potentials)):
        changed = False
        for a,b,cost in residual:
            if potentials[b] > potentials[a]+cost:
                potentials[b] = potentials[a]+cost
                changed = True
        if not changed:
            break
    else:
        raise AssertionError('Negative residual-cost cycle disproves oracle optimality')
    minimum = min((cost+potentials[a]-potentials[b] for a,b,cost in residual),default=0)
    assert minimum >= 0
    return dict(potentials=potentials,minimum_reduced_cost=minimum,residual_arcs=len(residual))


def check_score(score, ledger, preferences, moves, helpers):
    assert score['gross_debt'] == score['debt'] == gross(ledger)
    assert score['discomfort'] == discomfort(ledger,preferences) and score['empty_zones'] == 0
    assert score['moves'] == moves and score['assisted_moves'] == helpers
    assert score['messages'] == score['delivered_messages'] == sum(score['messages_by_kind'].values())
    assert score['message_bytes'] == sum(score['bytes_by_kind'].values())
    assert set(score['messages_by_kind']) == set(score['bytes_by_kind'])


def audit_run(case, run, oracle, plan):
    ledger, preferences = initial(case)
    reference = dict(ledger)
    events, services = run['audit_events'], run['service']
    offers = case['arrivals'] if run['mode'] == 'arrivals' else []
    end = plan['arrivals']['end_time']
    times = [event['time'] for event in offers]+[end] if run['mode']=='arrivals' else [0]
    assert len(services) == len(times)
    assert run['trustlines'] == len(ledger) == len(case['edges'])
    assert run['nodes'] == len(case['nodes'])
    budget = run['budget_per_trustline']*len(ledger)
    assert run['message_budget'] == budget
    index = moves = helpers = prior_messages = prior_bytes = 0
    identifiers = set()
    for service_index, (service,at) in enumerate(zip(services,times)):
        assert service['time'] == at
        earned = int(budget*at/end) if run['mode']=='arrivals' else budget
        assert service['earned_allowance'] == earned
        while index<len(events) and events[index]['kind']=='settlement' and events[index]['time']==at:
            receipt = events[index]['receipt']
            assert receipt['policy'] == run['policy'] and receipt['id'] not in identifiers
            identifiers.add(receipt['id'])
            helpers += apply_receipt(ledger,preferences,receipt)
            moves += 1
            index += 1
        check_score(service['score'],ledger,preferences,moves,helpers)
        messages = service['messages']
        assert messages == service['score']['messages'] <= earned
        assert service['used'] == messages-prior_messages >= 0
        assert service['score']['message_bytes'] >= prior_bytes
        prior_messages, prior_bytes = messages, service['score']['message_bytes']
        assert positions(ledger) == positions(reference)
        if service_index<len(offers):
            event, offer = events[index], offers[service_index]
            assert event == dict(kind='transfer',**offer,accepted=True)
            apply_transfer(ledger,preferences,event)
            apply_transfer(reference,preferences,event)
            index += 1
    assert index == len(events)
    assert ledger == snapshot(run['snapshot']) and reference == snapshot(oracle['reference'])
    check_score(run['final'],ledger,preferences,moves,helpers)
    assert run['final'] == services[-1]['score']
    assert run['pending_messages'] == run['pending_reservations'] == 0
    assert run['offered'] == run['accepted'] == len(offers)
    assert run['accepted_value'] == sum(abs(event['amount']) for event in offers)
    assert run['blocked'] == run['blocked_value'] == 0
    assert run['unused_budget'] == budget-prior_messages >= 0
    assert run['actual_messages_per_trustline'] == prior_messages/len(ledger)
    assert run['reference_gross'] == oracle['reference_gross']
    assert run['oracle_minimum_gross'] == oracle['minimum_gross']
    assert run['clearing_potential'] == oracle['potential']
    savings = gross(reference)-gross(ledger)
    assert run['snapshot_savings'] == savings and gross(ledger) >= oracle['minimum_gross']
    expected_percent = 100*savings/oracle['potential'] if oracle['potential'] else None
    assert run['clearing_potential_achieved_percent'] == expected_percent
    if expected_percent is not None:
        assert expected_percent <= 100
    return dict(settlements=moves,assisted_settlements=helpers,accepted_transfers=len(offers),
                snapshot_savings=savings,negative_savings=savings<0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    data = json.loads(args.results.read_text())
    assert data['complete'] is True, 'Campaign incomplete; do not audit while performance runs are active'
    plan_path, input_path = HERE/'comfort-curve-plan.json', HERE/'comfort-curve-workloads.json'
    plan, workload = json.loads(plan_path.read_text()), json.loads(input_path.read_text())
    assert plan == data['plan']
    assert workload['plan_sha256'] == data['freeze']['plan_sha256'] == sha256(plan_path)
    assert data['freeze']['workload_sha256'] == sha256(input_path)
    for name, expected in data['freeze']['sources'].items():
        assert sha256(ROOT/name) == expected, f'Source changed: {name}'
    cases = {case['name']:case for case in workload['cases']}
    assert len(cases) == len(workload['cases'])
    paired = {}
    for case in cases.values():
        unsigned = {key:value for key,value in case.items() if key!='sha256'}
        assert hashlib.sha256(compact(unsigned)).hexdigest() == case['sha256']
        ledger, preferences = initial(case)
        check_bounds(ledger,preferences)
        assert gross(ledger)+sum(abs(event['amount']) for event in case['arrivals']) < plan['hard_credit_grant_each_endpoint']
        assert all(own['auto_adjust'] and peer['auto_adjust'] for own,peer in preferences.values())
        signature = (ledger,case['arrivals'])
        key = (case['family'],case['seed'])
        if key in paired:
            assert signature == paired[key]
        paired[key] = signature
    oracles, certificates = {}, {}
    for oracle in data['oracles']:
        key = (oracle['case'],oracle['mode'])
        assert key not in oracles and key[0] in cases and key[1] in plan['modes']
        certificates['|'.join(key)] = certify_optimum(cases[key[0]],oracle)
        oracles[key] = oracle
    assert len(oracles) == len(cases)*len(plan['modes'])
    seen, details, groups = set(), [], defaultdict(list)
    for run in data['runs']:
        key = (run['case'],run['mode'],run['policy'],run['budget_per_trustline'])
        assert key not in seen
        seen.add(key)
        assert key[0] in cases and key[1] in plan['modes'] and key[2] in plan['policies']
        assert key[3] in plan['message_budgets_per_original_trustline']
        case = cases[key[0]]
        assert (run['family'],run['profile'],run['seed']) == (case['family'],case['profile'],case['seed'])
        result = audit_run(case,run,oracles[key[:2]],plan)
        details.append(dict(case=key[0],mode=key[1],policy=key[2],budget=key[3],**result))
        groups[(run['family'],run['profile'],key[1],key[2],key[3])].append(run)
    assert len(seen) == data['expected_runs'] == plan['expected_runs'] == len(cases)*len(plan['modes'])*len(plan['policies'])*len(plan['message_budgets_per_original_trustline'])
    aggregates = []
    for (family,profile,mode,policy,budget), runs in sorted(groups.items()):
        assert sorted(run['seed'] for run in runs) == sorted(plan['seeds'])
        savings, potential = sum(run['snapshot_savings'] for run in runs),sum(run['clearing_potential'] for run in runs)
        aggregates.append(dict(family=family,profile=profile,mode=mode,policy=policy,budget_per_trustline=budget,
            graphs=len(runs),mean_actual_messages_per_trustline=sum(run['actual_messages_per_trustline'] for run in runs)/len(runs),
            savings=savings,potential=potential,percent=100*savings/potential if potential else None,
            total_messages=sum(run['final']['messages'] for run in runs),
            total_json_bytes=sum(run['final']['message_bytes'] for run in runs)))
    result = dict(independent_audit_passed=True,results_sha256=sha256(args.results),
        auditor_sha256=sha256(Path(__file__)),runs_checked=len(seen),oracles_certified=len(oracles),
        settlements_replayed=sum(item['settlements'] for item in details),
        assisted_settlements_replayed=sum(item['assisted_settlements'] for item in details),
        transfer_events_replayed=sum(item['accepted_transfers'] for item in details),
        negative_snapshot_savings_runs=sum(item['negative_savings'] for item in details),
        original_trustline_counting='Each undirected original pair counted once, including zero balances.',
        oracle_certificate='Independent feasible-flow and Bellman–Ford nonnegative reduced-residual-cost dual certificate; no external solver imported.',
        communication_scope='Aggregate count/byte/by-kind consistency checked against frozen source encoder; full payload wire logs were not saved, so bytes are not independently re-encoded here.',
        model_limits='Broad comfort: exact hard-bound netting optimum. Narrow comfort: common relaxed hard-bound upper ceiling, not exact preference-constrained reachability. Finite serial service; no concurrency, crashes, losses or private-route guarantee.',
        aggregates=aggregates,run_audits=details,oracle_dual_certificates=certificates)
    output = args.output or args.results.with_name('independent-audit.json')
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:result[key] for key in ('independent_audit_passed','runs_checked','oracles_certified',
        'settlements_replayed','assisted_settlements_replayed','transfer_events_replayed','negative_snapshot_savings_runs')},indent=2))


if __name__ == '__main__':
    main()
