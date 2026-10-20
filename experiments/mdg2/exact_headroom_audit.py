"""Independent epoch/certificate audit for deterministic residual clearing.

Reuses the previously frozen independent signed-ledger checks; imports no actor,
benchmark runner, Bellman–Ford implementation, or optimization solver.
"""
from collections import defaultdict
import argparse
import hashlib
import json
from pathlib import Path

from comfort_curve_audit import (apply_receipt, apply_transfer, canonical, certify_optimum,
    check_bounds, check_score, compact, gross, initial, permitted, positions, snapshot,
    view_preferences)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normal_potentials(values, nodes):
    assert len(values) == len(nodes)
    expected = {str(node) for node in nodes}
    assert {str(node) for node in values} == expected
    normalized = {str(node):value for node,value in values.items()}
    assert all(type(value) is int for value in normalized.values())
    return {node:normalized[str(node)] for node in nodes}


def audit_certificate(case, ledger, preferences, clear):
    assert clear['certified'] is True and clear['status'] == 'certified'
    certificate = clear['certificate']
    nodes = case['nodes']
    potential = normal_potentials(clear['potentials'],nodes)
    assert potential == normal_potentials(certificate['potentials'],nodes)
    assert certificate['known_nodes'] == certificate['reported_nodes'] == len(nodes)
    assert certificate['policy'] == 'comfort_headroom'
    local_reports = {report['node']:report for report in certificate['nodes']}
    assert len(local_reports) == len(certificate['nodes']) and set(local_reports) == set(nodes)
    expected_neighbors = defaultdict(set)
    for a,b in ledger:
        expected_neighbors[a].add(b)
        expected_neighbors[b].add(a)
    minimum, eligible_arcs = None, 0
    for node in nodes:
        report = local_reports[node]
        assert report['potential'] == potential[node]
        outgoing = {arc['peer']:arc for arc in report['outgoing']}
        assert len(outgoing) == len(report['outgoing'])
        assert set(outgoing) == expected_neighbors[node], 'Certificate omitted a trustline incidence'
        for peer, arc in outgoing.items():
            pair, sign = canonical(node,peer)
            old = sign*ledger[pair]
            own, other = view_preferences(preferences,node,peer)
            eligible = permitted(old,old+1,own,other,'comfort_headroom')
            assert eligible == permitted(-old,-old-1,other,own,'comfort_headroom')
            cost = abs(old+1)-abs(old)
            reduced = cost+potential[node]-potential[peer]
            assert arc['before'] == old and arc['after'] == old+1
            assert arc['eligible'] is eligible
            assert arc['peer_potential'] == potential[peer]
            assert arc['cost'] == cost and arc['reduced_cost'] == reduced
            if eligible:
                assert reduced >= 0, 'An eligible negative reduced-cost arc invalidates the potential'
                minimum = reduced if minimum is None else min(minimum,reduced)
                eligible_arcs += 1
    expected_minimum = minimum if minimum is not None else 0
    assert certificate['min_reduced_cost'] == expected_minimum
    return dict(verified_nodes=len(nodes),eligible_residual_arcs=eligible_arcs,
                minimum_reduced_cost=expected_minimum)


def audit_run(case, run, plan):
    assert run['case'] == case['name'] and run['case_sha256'] == case['sha256']
    assert (run['seed'],run['profile']) == (case['seed'],case['profile'])
    assert run['method'] in ('exact','decrease_first') and run['mode'] in ('static','arrivals')
    assert run['nodes'] == len(case['nodes']) == plan['nodes']
    ledger, preferences = initial(case)
    reference = dict(ledger)
    assert run['trustlines'] == len(ledger) == plan['trustlines']
    offers = case['arrivals'] if run['mode']=='arrivals' else []
    count, batch = len(offers),plan['arrivals']['epoch_size']
    prefixes = [0]+list(range(batch,count+1,batch)) if offers else [0]
    if prefixes[-1] != count:
        prefixes.append(count)
    assert not offers or count == plan['arrivals']['count']
    assert len(run['epochs']) == len(prefixes)
    cap = (plan['exact_total_message_safety_ceiling'] if run['method']=='exact'
           else plan['control_total_messages_per_trustline']*len(ledger))
    assert run['message_safety_ceiling'] == cap
    assert gross(ledger)+sum(abs(offer['amount']) for offer in offers) < plan['hard_credit_grant_each_endpoint']
    events = run['audit_events']
    cursor = prior_prefix = moves = helpers = prior_messages = prior_bytes = 0
    receipt_ids = set()
    certificates = []
    certified_broad = certified_narrow = incomplete_exact = 0
    for epoch_index, (epoch,prefix) in enumerate(zip(run['epochs'],prefixes)):
        at = offers[prefix-1]['time'] if prefix else 0
        assert epoch['index'] == epoch_index and epoch['prefix_count'] == prefix and epoch['time'] == at
        for offer in offers[prior_prefix:prefix]:
            assert cursor < len(events)
            event = events[cursor]
            assert event == dict(kind='transfer',**offer,accepted=True)
            apply_transfer(ledger,preferences,event)
            apply_transfer(reference,preferences,event)
            cursor += 1
        end = epoch['event_end_index']
        assert cursor <= end <= len(events)
        cycle_count = 0
        while cursor < end:
            event = events[cursor]
            assert event['kind'] == 'settlement' and event['time'] == at
            receipt = event['receipt']
            assert receipt['id'] not in receipt_ids and receipt['policy'] == 'comfort_headroom'
            receipt_ids.add(receipt['id'])
            helpers += apply_receipt(ledger,preferences,receipt)
            moves += 1
            cycle_count += 1
            cursor += 1
        assert ledger == snapshot(epoch['snapshot'])
        assert positions(ledger) == positions(reference)
        check_score(epoch['score'],ledger,preferences,moves,helpers)
        score, clear = epoch['score'],epoch['clear_result']
        allowance = cap if run['method']=='exact' else cap*(epoch_index+1)//len(prefixes)
        assert epoch['earned_allowance'] == allowance
        assert epoch['used_messages'] == clear['used_messages'] == score['messages']-prior_messages >= 0
        assert prior_messages <= score['messages'] <= allowance
        assert score['message_bytes'] >= prior_bytes
        if 'phase_messages' in score:
            assert sum(score['phase_messages'].values()) == score['messages']
        if 'phase_bytes' in score:
            assert sum(score['phase_bytes'].values()) == score['message_bytes']
        if run['method']=='exact':
            assert clear['budget'] == allowance-prior_messages
            assert clear['quiescent'] is True
            assert clear['pending_messages'] == clear['pending_reservations'] == 0
            assert clear['cycles'] == cycle_count
            assert 0 <= clear['setup_messages'] <= clear['used_messages']
            if epoch_index:
                assert clear['setup_messages'] == 0, 'Static trustline setup was unexpectedly repeated'
            if clear['certified']:
                cert = audit_certificate(case,ledger,preferences,clear)
                certificates.append(dict(epoch=epoch_index,prefix=prefix,**cert))
                if run['profile']=='broad':
                    certified_broad += 1
                else:
                    certified_narrow += 1
            else:
                assert clear['status'] == 'budget_exhausted'
                incomplete_exact += 1
        else:
            assert clear['status'] == 'finite_budget_control' and clear['certified'] is False
        oracle = epoch['oracle']
        assert oracle['case'] == case['name']
        assert oracle['mode'] == ('arrivals' if prefix else 'static')
        certify_optimum(dict(case,arrivals=offers[:prefix]),oracle)
        assert snapshot(oracle['reference']) == reference
        assert gross(ledger) >= oracle['minimum_gross']
        savings = gross(reference)-gross(ledger)
        assert epoch['snapshot_savings'] == savings
        expected_percent = 100*savings/oracle['potential'] if oracle['potential'] else None
        assert epoch['clearing_potential_achieved_percent'] == expected_percent
        if clear['certified'] and run['profile']=='broad':
            assert gross(ledger) == oracle['minimum_gross'], 'Broad completion disagrees with certified global optimum'
            assert expected_percent in (100,None)
        prior_prefix, prior_messages, prior_bytes = prefix,score['messages'],score['message_bytes']
    assert cursor == len(events) and prior_prefix == count
    assert run['offered'] == run['accepted'] == count and run['blocked'] == 0
    assert run['touched_trustlines'] == len({(offer['a'],offer['b']) for offer in offers})
    assert run['snapshot'] == run['epochs'][-1]['snapshot']
    assert run['final'] == run['epochs'][-1]['score']
    assert run['actual_messages_per_trustline'] == prior_messages/len(ledger)
    assert run['pending_messages'] == run['pending_reservations'] == 0
    return dict(independent_audit_passed=True,epochs=len(prefixes),settlements_replayed=moves,
                assisted_settlements_replayed=helpers,transfers_replayed=count,
                oracle_optima_certified=len(prefixes),broad_epochs_certified_globally_optimal=certified_broad,
                narrow_epochs_certified_currently_locally_optimal=certified_narrow,
                incomplete_exact_epochs=incomplete_exact,residual_certificate_checks=certificates)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    data = json.loads(args.results.read_text())
    assert data['complete'] is True, 'Performance campaign incomplete'
    plan_path, workload_path = HERE/'exact-headroom-plan.json',HERE/'exact-headroom-workloads.json'
    plan, workload = json.loads(plan_path.read_text()),json.loads(workload_path.read_text())
    assert data['plan'] == plan and workload['plan_sha256'] == sha256(plan_path)
    assert data['freeze']['plan_sha256'] == sha256(plan_path)
    assert data['freeze']['workloads_sha256'] == sha256(workload_path)
    for file, expected in data['freeze']['sources'].items():
        assert sha256(ROOT/file) == expected, f'Frozen source changed: {file}'
    cases = {case['name']:case for case in workload['cases']}
    assert len(cases) == len(workload['cases'])
    expected = set()
    for case in cases.values():
        unsigned = {key:value for key,value in case.items() if key!='sha256'}
        assert hashlib.sha256(compact(unsigned)).hexdigest() == case['sha256']
        for mode in plan['exact_modes'][case['profile']]:
            expected.add((case['name'],'exact',mode))
        for mode in plan['control_modes'].get(case['profile'],[]):
            expected.add((case['name'],'decrease_first',mode))
    seen, summaries = set(),[]
    for run in data['runs']:
        key = (run['case'],run['method'],run['mode'])
        assert key in expected and key not in seen
        seen.add(key)
        summary = audit_run(cases[key[0]],run,plan)
        assert run['independent_audit'] == summary
        summaries.append(dict(case=key[0],method=key[1],mode=key[2],**summary))
    assert seen == expected and len(seen) == data['expected_runs'] == plan['expected_runs']
    totals = {field:sum(item[field] for item in summaries) for field in
        ('epochs','settlements_replayed','assisted_settlements_replayed','transfers_replayed',
         'oracle_optima_certified','broad_epochs_certified_globally_optimal',
         'narrow_epochs_certified_currently_locally_optimal','incomplete_exact_epochs')}
    result = dict(independent_audit_passed=True,results_sha256=sha256(args.results),
        auditor_sha256=sha256(Path(__file__)),runs_checked=len(seen),**totals,run_audits=summaries,
        certificate_scope='Every supplied actor potential is checked on every eligible unit residual arc; broad certified epochs must also match a separately certified hard-bound L1 optimum.',
        limits='Narrow completion certifies only current admissible residual optimality. Grouped arrivals are buffered during static epochs. Timing and budgets are unmatched between exact completion and finite-budget control. Full wire payloads are not independently re-encoded.')
    output = args.output or args.results.with_name('independent-audit.json')
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:result[key] for key in ('independent_audit_passed','runs_checked',*totals)},indent=2))


if __name__=='__main__':
    main()
