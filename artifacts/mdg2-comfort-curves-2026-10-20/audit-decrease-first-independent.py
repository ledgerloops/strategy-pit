#!/usr/bin/env python3
"""Post-campaign validation using the independent signed-ledger auditor.

No performance actor, benchmark runner, oracle solver or published gate helper is
imported. The signed-ledger checker was frozen before candidate measurements.
"""
import hashlib
import json
from pathlib import Path
import sys

DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parents[1]
HERE = ROOT/'experiments/mdg2'
sys.path.insert(0,str(HERE))
from comfort_curve_audit import audit_run, certify_optimum


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    result_path = DIRECTORY/'decrease-first-results.json'
    data = json.loads(result_path.read_text())
    assert data['complete'] is True, 'Wait for the performance campaign to finish'
    plan_path = HERE/'decrease-first-plan.json'
    workload_path = HERE/'decrease-first-workloads.json'
    base_plan_path = HERE/'comfort-curve-plan.json'
    original_path = DIRECTORY/'results.json'
    plan = json.loads(plan_path.read_text())
    workload = json.loads(workload_path.read_text())
    base_plan = json.loads(base_plan_path.read_text())
    original = json.loads(original_path.read_text())
    assert data['plan'] == plan and data['base_plan'] == base_plan
    assert data['freeze']['plan_sha256'] == workload['plan_sha256'] == sha256(plan_path)
    assert data['freeze']['workload_sha256'] == sha256(workload_path)
    assert data['freeze']['base_plan_sha256'] == workload['base_plan_sha256'] == sha256(base_plan_path)
    assert data['freeze']['original_workloads_sha256'] == workload['original_workloads_sha256'] == sha256(HERE/'comfort-curve-workloads.json')
    assert data['freeze']['base_freeze_sha256'] == sha256(HERE/'comfort-curve-freeze.json')
    assert data['original_results_sha256'] == sha256(original_path) and original['complete']
    for file, expected in data['freeze']['sources'].items():
        assert sha256(ROOT/file) == expected, f'Frozen source changed: {file}'
    original_workload = json.loads((HERE/'comfort-curve-workloads.json').read_text())
    assert workload['extension_cases'] == original_workload['cases']
    cases = {}
    expected_keys = set()
    for phase in ('extension','heldout'):
        for case in workload[phase+'_cases']:
            key = (phase,case['name'])
            assert key not in cases
            cases[key] = case
            unsigned = {field:value for field,value in case.items() if field!='sha256'}
            assert hashlib.sha256(json.dumps(unsigned,sort_keys=True,separators=(',',':')).encode()).hexdigest() == case['sha256']
            for mode in plan[phase]['modes']:
                for method in plan[phase]['methods']:
                    for budget in plan[phase]['budgets_per_original_trustline']:
                        expected_keys.add((phase,case['name'],mode,method,budget))
    assert {case['seed'] for case in workload['extension_cases']}.isdisjoint(case['seed'] for case in workload['heldout_cases'])
    oracles, certificates = {}, {}
    for oracle in data['oracles']:
        key = (oracle['phase'],oracle['case'],oracle['mode'])
        assert key not in oracles
        certificates['|'.join(key)] = certify_optimum(cases[key[:2]],oracle)
        oracles[key] = oracle
    assert len(oracles) == len(cases)*2 == 36
    details = []
    seen = set()
    for run in data['runs']:
        key = (run['phase'],run['case'],run['mode'],run['method'],run['budget_per_trustline'])
        assert key in expected_keys and key not in seen
        seen.add(key)
        case = cases[key[:2]]
        assert run['case_sha256'] == case['sha256'] and run['policy'] == 'comfort_headroom'
        result = audit_run(case,run,oracles[key[:3]],base_plan)
        assert run['independent_audit_passed'] is True and run['independent_audit'] == result
        details.append(dict(phase=key[0],case=key[1],mode=key[2],method=key[3],budget=key[4],**result))
    assert seen == expected_keys and len(seen) == data['expected_runs'] == plan['expected_runs'] == 168
    selected = [run for run in data['runs'] if run['phase']=='heldout' and run['budget_per_trustline']==1024]
    candidate = [run for run in selected if run['method']=='decrease_first']
    control = [run for run in selected if run['method']=='comfort_headroom']
    assert len(candidate) == len(control) == 12
    gain_minimum = plan['gate']['pooled_snapshot_savings_gain_minimum_fraction']
    cost_ceiling = plan['gate']['cost_ceiling_ratio']
    proposed = sum(run['snapshot_savings'] for run in candidate)
    baseline = sum(run['snapshot_savings'] for run in control)
    checks = dict(positive_baseline=baseline>0,pooled_gain=baseline>0 and proposed >= (1+gain_minimum)*baseline)
    cells = []
    for profile in ('broad','narrow'):
        for mode in ('static','arrivals'):
            new = sum(run['snapshot_savings'] for run in candidate if (run['profile'],run['mode'])==(profile,mode))
            old = sum(run['snapshot_savings'] for run in control if (run['profile'],run['mode'])==(profile,mode))
            minimum = old-.05*abs(old)
            cells.append(dict(profile=profile,mode=mode,candidate_savings=new,baseline_savings=old,
                              minimum=minimum,passed=new>=minimum))
    checks['cells'] = all(cell['passed'] for cell in cells)
    costs = {}
    for name, getter in [('messages',lambda run:run['final']['messages']),
                         ('json_bytes',lambda run:run['final']['message_bytes']),
                         ('runtime_seconds',lambda run:run['runtime_seconds'])]:
        new, old = sum(map(getter,candidate)), sum(map(getter,control))
        passed = new <= cost_ceiling*old if old else new==0
        costs[name] = dict(candidate=new,baseline=old,ratio=new/old if old else None,passed=passed)
        checks[name] = passed
    checks['all_replays'] = len(details)==168
    gate = dict(passed=all(checks.values()),checks=checks,candidate_savings=proposed,baseline_savings=baseline,
                pooled_gain_fraction=proposed/baseline-1 if baseline>0 else None,cells=cells,costs=costs)
    assert gate['passed'] == data['gate']['passed']
    assert proposed == data['gate']['candidate_snapshot_savings']
    assert baseline == data['gate']['baseline_snapshot_savings']
    assert checks['pooled_gain'] == data['gate']['pooled_gain_passed']
    for name, cost in costs.items():
        assert cost['candidate'] == data['gate']['costs'][name]['candidate']
        assert cost['baseline'] == data['gate']['costs'][name]['control']
        assert cost['passed'] == data['gate']['costs'][name]['passed']
    output = dict(independent_audit_passed=True,results_sha256=sha256(result_path),
        auditor_sha256=sha256(Path(__file__)),frozen_ledger_auditor_sha256=sha256(HERE/'comfort_curve_audit.py'),
        original_results_unchanged=True,runs_checked=len(details),oracles_certified=len(oracles),
        settlements_replayed=sum(item['settlements'] for item in details),
        assisted_settlements_replayed=sum(item['assisted_settlements'] for item in details),
        accepted_transfers_replayed=sum(item['accepted_transfers'] for item in details),
        negative_snapshot_savings_runs=sum(item['negative_savings'] for item in details),
        fresh_underlying_graph_seeds=plan['heldout']['seeds'],
        sampling_scope='Three fresh graph/arrival seeds, each tested under two preference profiles and two modes; budget points are not independent samples.',
        gate=gate,run_audits=details,oracle_dual_certificates=certificates)
    destination = DIRECTORY/'decrease-first-independent-audit.json'
    destination.write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({key:output[key] for key in ('independent_audit_passed','runs_checked','oracles_certified',
        'settlements_replayed','assisted_settlements_replayed','negative_snapshot_savings_runs','gate')},indent=2))


if __name__=='__main__':
    main()
