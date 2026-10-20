"""Prospectively fixed decrease-first follow-up, preserving the original evidence."""
from collections import defaultdict
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import networkx as nx
import comfort_curve_benchmark as base
import comfort_curve_audit as independent
from comfort_headroom import Network
from comfort_decrease_first import DecreaseFirstNetwork

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PLAN=HERE/'decrease-first-plan.json'
WORKLOAD=HERE/'decrease-first-workloads.json'
FREEZE=HERE/'decrease-first-freeze.json'
BASE_RESULTS=ROOT/'artifacts/mdg2-comfort-curves-2026-10-20/results.json'
DEFAULT_OUTPUT=ROOT/'artifacts/mdg2-comfort-curves-2026-10-20/decrease-first-results.json'


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources():
    paths=[Path(__file__),HERE/'make_decrease_first_workloads.py',HERE/'comfort_decrease_first.py',
           HERE/'comfort_curve_audit.py',HERE/'comfort_curve_benchmark.py',HERE/'comfort_headroom.py',
           HERE/'make_comfort_curve_workloads.py',ROOT/'app/comfort.py']
    return {str(p.relative_to(ROOT)):fingerprint(p) for p in paths}


def freeze_value():
    return dict(sources=sources(),plan_sha256=fingerprint(PLAN),workload_sha256=fingerprint(WORKLOAD),
        base_plan_sha256=fingerprint(base.PLAN),original_workloads_sha256=fingerprint(base.WORKLOAD),
        base_freeze_sha256=fingerprint(HERE/'comfort-curve-freeze.json'))


def run_selected(case,mode,method,budget,base_plan):
    constructor={'comfort_headroom':Network,'decrease_first':DecreaseFirstNetwork}[method]
    previous=base.Network
    base.Network=constructor
    try:
        return base.run_case(case,mode,'comfort_headroom',budget,base_plan)
    finally:
        base.Network=previous


def fractional_metric(candidate,control,ceiling):
    return dict(candidate=candidate,control=control,ratio=candidate/control if control else None,
                passed=candidate<=ceiling*control if control else candidate==0)


def gate(runs,plan):
    selected=[r for r in runs if r['phase']=='heldout' and r['budget_per_trustline']==1024]
    by_method={method:[r for r in selected if r['method']==method] for method in plan['methods']}
    candidate,control=by_method['decrease_first'],by_method['comfort_headroom']
    complete=len(candidate)==len(control)==12
    proposed=sum(r['snapshot_savings'] for r in candidate);baseline=sum(r['snapshot_savings'] for r in control)
    gain=proposed/baseline-1 if baseline>0 else None
    pooled_pass=baseline>0 and proposed>=1.05*baseline
    cells=[]
    for profile in ('broad','narrow'):
        for mode in ('static','arrivals'):
            a=sum(r['snapshot_savings'] for r in candidate if (r['profile'],r['mode'])==(profile,mode))
            b=sum(r['snapshot_savings'] for r in control if (r['profile'],r['mode'])==(profile,mode))
            cells.append(dict(profile=profile,mode=mode,candidate_savings=a,baseline_savings=b,
                relative_change=(a-b)/abs(b) if b else None,minimum=b-.05*abs(b),passed=a>=b-.05*abs(b)))
    costs={
        'messages':fractional_metric(sum(r['final']['messages'] for r in candidate),sum(r['final']['messages'] for r in control),1.25),
        'json_bytes':fractional_metric(sum(r['final']['message_bytes'] for r in candidate),sum(r['final']['message_bytes'] for r in control),1.25),
        'runtime_seconds':fractional_metric(sum(r['runtime_seconds'] for r in candidate),sum(r['runtime_seconds'] for r in control),1.25)}
    safety=all(r.get('independent_audit_passed') and r['accepted']==r['offered'] and r['blocked']==0
               and r['pending_messages']==r['pending_reservations']==0 for r in runs)
    return dict(phase='heldout',budget_per_original_trustline=1024,complete=complete,
        candidate_snapshot_savings=proposed,baseline_snapshot_savings=baseline,
        pooled_gain_fraction=gain,pooled_gain_passed=pooled_pass,positive_baseline=baseline>0,
        cells=cells,costs=costs,all_runs_accepted_and_audited=safety,
        passed=complete and pooled_pass and all(c['passed'] for c in cells) and all(c['passed'] for c in costs.values()) and safety)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument('--freeze',action='store_true',help='Write a prospective manifest only; no performance runs')
    args=parser.parse_args()
    plan=json.loads(PLAN.read_text());workloads=json.loads(WORKLOAD.read_text());base_plan=json.loads(base.PLAN.read_text())
    if workloads['plan_sha256']!=fingerprint(PLAN) or nx.__version__!='3.5':
        raise AssertionError('Plan or NetworkX differs')
    if args.freeze:
        if FREEZE.exists():raise SystemExit('Refusing to overwrite prospective freeze')
        FREEZE.write_text(json.dumps(freeze_value(),indent=2)+'\n')
        print(FREEZE);return
    if args.output.exists():raise SystemExit('Existing follow-up evidence is never overwritten')
    freeze=json.loads(FREEZE.read_text())
    if freeze!=freeze_value():raise AssertionError('Source, plan or workload differs from prospective freeze')
    original=json.loads(BASE_RESULTS.read_text())
    if original.get('complete') is not True or len(original['runs'])!=240:
        raise AssertionError('Wait until the first comfort-curve performance campaign is complete')
    original_hash=fingerprint(BASE_RESULTS)
    report=dict(complete=False,expected_runs=168,expected_extension_runs=120,expected_heldout_runs=48,
        plan=plan,base_plan=base_plan,freeze=freeze,original_results_sha256=original_hash,
        python=platform.python_version(),networkx=nx.__version__,platform=platform.platform(),
        oracles=[],runs=[],oracle_certificates={},gate=None)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    def check():
        assert freeze==freeze_value(),'Frozen source/input changed during follow-up'
        assert fingerprint(BASE_RESULTS)==original_hash,'Original result evidence changed'
    def save():
        temporary=args.output.with_suffix(args.output.suffix+'.tmp')
        temporary.write_text(json.dumps(report,separators=(',',':'))+'\n')
        temporary.replace(args.output)
    save();lookup={}
    for phase in ('extension','heldout'):
        for case in workloads[phase+'_cases']:
            for mode in base_plan['modes']:
                check();oracle=base.oracle(case,mode)
                certificate=independent.certify_optimum(case,oracle)
                lookup[case['name'],mode]=oracle
                report['oracles'].append(dict(oracle,phase=phase))
                report['oracle_certificates'][case['name']+'|'+mode]=certificate
    save()
    for phase in ('extension','heldout'):
        spec=plan[phase]
        for budget in spec['budgets_per_original_trustline']:
            for case_index,case in enumerate(workloads[phase+'_cases']):
                for mode_index,mode in enumerate(spec['modes']):
                    methods=spec['methods'] if (case_index+mode_index)%2==0 else list(reversed(spec['methods']))
                    for method in methods:
                        check();result=run_selected(case,mode,method,budget,base_plan)
                        oracle=lookup[case['name'],mode]
                        savings=oracle['reference_gross']-result['final']['gross_debt']
                        result.update(method=method,phase=phase,case_sha256=case['sha256'],
                            reference_gross=oracle['reference_gross'],oracle_minimum_gross=oracle['minimum_gross'],
                            clearing_potential=oracle['potential'],snapshot_savings=savings,
                            clearing_potential_achieved_percent=100*savings/oracle['potential'] if oracle['potential'] else None)
                        audit=independent.audit_run(case,result,oracle,base_plan)
                        result.update(independent_audit_passed=True,independent_audit=audit)
                        report['runs'].append(result);save()
                        print(f'{len(report["runs"])}/168 {phase} {case["name"]} {mode} {method} '
                              f'budget/line={budget} messages={result["final"]["messages"]} '
                              f'savings={savings} potential%={result["clearing_potential_achieved_percent"]}',flush=True)
    check()
    assert len(report['runs'])==168
    assert sum(r['phase']=='extension' for r in report['runs'])==120
    assert sum(r['phase']=='heldout' for r in report['runs'])==48
    report['gate']=gate(report['runs'],plan)
    report['complete']=True;save()
    print('COMPLETE',json.dumps(report['gate'],sort_keys=True),flush=True)


if __name__=='__main__':main()
