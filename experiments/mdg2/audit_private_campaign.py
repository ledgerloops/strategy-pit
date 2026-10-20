"""Post-measurement validation, including the separately frozen local-filter followup."""
import hashlib
import json
from pathlib import Path

from private_stream_post_audit import audit_run, load_run, compact
from private_residual_diagnostic import diagnose
from private_stream_benchmark import manifest as base_manifest
from private_filter_benchmark import manifest as filter_manifest

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'artifacts/mdg2-private-stream-2026-10-20'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    cases = {c['name']: c for c in json.loads((HERE/'private-stream-workloads.json').read_text())['cases']}
    audits, diagnostics = [], []
    expected = {
        'results.json': {(c, m) for c in cases for m in ('randomized_cancellation', 'private_nonexpansion')}
                        | {('private32-seed601', 'faithful_comfort')},
        'filtered-results.json': {(c, 'private_nonexpansion_filtered') for c in cases}}
    for filename, current in [('results.json', base_manifest()),
                              ('filtered-results.json', filter_manifest())]:
        index = json.loads((OUT/filename).read_text())
        assert index['complete'] and index['freeze'] == current
        assert {(e['case'], e['method']) for e in index['runs']} == expected[filename]
        assert len(index['runs']) == len(expected[filename])
        for entry in index['runs']:
            run = load_run(entry, OUT)
            case = cases[run['case']]
            assert run['freeze'] == current and run['case_sha256'] == case['sha256']
            assert hashlib.sha256(compact({k: v for k, v in case.items() if k != 'sha256'})).hexdigest() == case['sha256']
            assert run['offers'] == case['offers']
            assert run['initial_edges'] == [[e['a'], e['b'], e['balance'], e['own'], e['peer']] for e in case['edges']]
            assert run['original_trustlines'] == 96
            offered = [e for e in run['events'] if e['kind'] == 'offer']
            assert [{k: e[k] for k in ('time', 'a', 'b', 'amount', 'offer_id')} for e in offered] == case['offers'][:len(offered)]
            if not run['censored']:
                assert len(offered) == 1000
            audit = audit_run(run)
            audits.append(dict(case=run['case'], method=run['method'], raw_sha256=entry['sha256'], **audit))
            if run['final']['mirror_mismatches']:
                diagnostic = dict(unavailable='Pending endpoint mismatch; no averaged ledger was substituted')
            else:
                diagnostic = diagnose(run['final_balances'], run['initial_preferences'])
            diagnostics.append(dict(case=run['case'], method=run['method'], **diagnostic))
            print(run['case'], run['method'], 'PASS' if audit['independent_audit_passed'] else audit['failures'], flush=True)
    post_sources = ['private_stream_post_audit.py', 'audit_private_campaign.py',
                    'private_residual_diagnostic.py', 'test_private_residual_diagnostic.py']
    result = dict(independent_audit_passed=all(a['independent_audit_passed'] for a in audits),
                  runs_checked=len(audits), run_audits=audits,
                  index_hashes={name: sha(OUT/name) for name in expected},
                  postmeasurement_sources={f'experiments/mdg2/{name}': sha(HERE/name) for name in post_sources},
                  provenance='Actor/observer and base auditor pins remain unchanged. The additional post-measurement validator adds compressed-file/index guards, offered-to-posted matching and shadow reconstruction checks; residual witnesses are offline only.')
    (OUT/'independent-audit.json').write_text(json.dumps(result, indent=2)+'\n')
    (OUT/'residual-diagnostics.json').write_text(json.dumps(diagnostics, indent=2)+'\n')
    assert result['independent_audit_passed']


if __name__ == '__main__':
    main()
