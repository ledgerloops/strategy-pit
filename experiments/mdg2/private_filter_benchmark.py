"""Paired development followup; original seven runs and source pins are retained."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import time

from private_stream_benchmark import manifest as base_manifest, FREEZE as BASE_FREEZE
from private_stream_filtered import FilteredPrivateStream
from private_stream_observer import Observer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLAN = HERE / 'private-filter-plan.json'
FREEZE = HERE / 'private-filter-freeze.json'
OUT = ROOT / 'artifacts/mdg2-private-stream-2026-10-20'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest():
    base = json.loads(BASE_FREEZE.read_text())
    assert base == base_manifest(), 'Original frozen source/input changed'
    return dict(base_freeze=base, plan_sha256=sha(PLAN),
                sources={str(path.relative_to(ROOT)): sha(path) for path in [
                    HERE/'private_stream_filtered.py', HERE/'test_private_filtered.py',
                    HERE/'private_filter_benchmark.py']})


def run_case(case, plan):
    edges = [(e['a'], e['b'], e['balance'], e['own'], e['peer']) for e in case['edges']]
    schedule = plan['scheduling']
    last = case['offers'][-1]['time']
    start = time.perf_counter()
    stream = FilteredPrivateStream(
        edges, seed=case['seed'], wake_mean=schedule['wake_mean'],
        wire_delay=schedule['wire_delay'], retry_delay=schedule['retry_delay'],
        discovery_until=last+schedule['discovery_tail'], message_cap=schedule['message_cap'])
    initialization_seconds = time.perf_counter()-start
    try:
        for offer in case['offers']:
            stream.offer(offer['time'], offer['a'], offer['b'], offer['amount'], offer['offer_id'])
        raw = stream.run(last+schedule['discovery_tail']+schedule['settlement_tail'])
    finally:
        stream.close()
    raw.update(case=case['name'], case_sha256=case['sha256'],
               initialization_seconds=initialization_seconds,
               offers=case['offers'], initial_edges=edges,
               last_offer_time=last, local_discovery_until=last+schedule['discovery_tail'])
    observer = Observer(edges)
    for event in raw['events']:
        if event.get('local_receipts') or event.get('local_obligations'):
            observer.observe_event(event, message_count=event['messages']+event['acknowledgements'])
    observer._clock(raw['time'], raw['messages']+raw['acknowledgements'])
    raw['observer'] = observer.result()
    return raw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.freeze:
        if FREEZE.exists():
            raise SystemExit('Never overwrite an existing followup freeze')
        FREEZE.write_text(json.dumps(manifest(), indent=2)+'\n')
        print(FREEZE, flush=True)
    if not args.run:
        return
    frozen = json.loads(FREEZE.read_text())
    assert frozen == manifest()
    followup = json.loads(PLAN.read_text())
    plan = json.loads((HERE/'private-stream-plan.json').read_text())
    inputs = json.loads((HERE/'private-stream-workloads.json').read_text())
    cases = [c for c in inputs['cases'] if c['seed'] in followup['seeds']]
    assert len(cases) == followup['expected_runs']
    metadata = dict(freeze=frozen, python=platform.python_version(), sqlite=sqlite3.sqlite_version,
                    platform=platform.platform(), complete=False, runs=[])
    for case in cases:
        destination = OUT / f"{case['name']}-{followup['method']}.json.gz"
        if destination.exists():
            with gzip.open(destination, 'rt') as handle:
                run = json.load(handle)
            assert run['freeze'] == frozen and run['case_sha256'] == case['sha256']
        else:
            print(f"START {case['name']} {followup['method']}", flush=True)
            run = run_case(case, plan)
            run['freeze'] = frozen
            temp = destination.with_suffix('.gz.tmp')
            with temp.open('wb') as handle:
                with gzip.GzipFile(fileobj=handle, mode='wb', mtime=0) as compressed:
                    compressed.write(json.dumps(run, separators=(',', ':')).encode())
            temp.replace(destination)
        metadata['runs'].append(dict(case=case['name'], seed=case['seed'], method=run['method'],
            file=destination.name, sha256=sha(destination),
            **{key: run[key] for key in ['messages', 'acknowledgements', 'message_bytes',
                'ack_body_bytes', 'runtime_seconds', 'initialization_seconds', 'censored', 'final']}))
        (OUT/'filtered-results.json').write_text(json.dumps(metadata, indent=2)+'\n')
        print(f"DONE filtered seed={case['seed']} debt={run['final']['debt']} "
              f"requests={run['messages']} runtime={run['runtime_seconds']:.2f}s "
              f"posted={run['observer']['final']['incorporated']['obligation']}", flush=True)
    metadata['complete'] = True
    (OUT/'filtered-results.json').write_text(json.dumps(metadata, indent=2)+'\n')


if __name__ == '__main__':
    main()
