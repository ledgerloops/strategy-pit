"""Prospectively pinned, serial private-hashlock stream measurements."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import time

from private_stream import PrivateStream
from private_stream_observer import Observer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLAN = HERE / 'private-stream-plan.json'
INPUT = HERE / 'private-stream-workloads.json'
FREEZE = HERE / 'private-stream-freeze.json'
OUT = ROOT / 'artifacts/mdg2-private-stream-2026-10-20'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest():
    names = ['private_stream.py', 'private_stream_benchmark.py',
             'private_stream_observer.py', 'private_stream_audit.py',
             'make_private_stream_workloads.py']
    paths = [HERE / name for name in names]
    paths += sorted(HERE.glob('test_private_stream*.py'))
    paths += [ROOT / 'app' / name for name in
              ['private_node.py', 'node.py', 'obligations.py', 'comfort.py']]
    return dict(sources={str(p.relative_to(ROOT)): sha(p) for p in paths},
                plan_sha256=sha(PLAN), workloads_sha256=sha(INPUT))


def run_case(case, method, plan):
    edges = [(e['a'], e['b'], e['balance'], e['own'], e['peer'])
             for e in case['edges']]
    schedule = plan['scheduling']
    last = case['offers'][-1]['time']
    start = time.perf_counter()
    stream = PrivateStream(
        edges, seed=case['seed'], method=method,
        wake_mean=schedule['wake_mean'], wire_delay=schedule['wire_delay'],
        retry_delay=schedule['retry_delay'],
        discovery_until=last+schedule['discovery_tail'],
        message_cap=schedule['message_cap'])
    initialization_seconds = time.perf_counter()-start
    try:
        for offer in case['offers']:
            stream.offer(offer['time'], offer['a'], offer['b'],
                         offer['amount'], offer['offer_id'])
        raw = stream.run(last+schedule['discovery_tail']+schedule['settlement_tail'])
    finally:
        stream.close()
    raw.update(case=case['name'], case_sha256=case['sha256'],
               initialization_seconds=initialization_seconds,
               offers=case['offers'], initial_edges=edges,
               last_offer_time=last,
               local_discovery_until=last+schedule['discovery_tail'])
    # No observer information is fed back to any node or scheduler.
    observer = Observer(edges)
    for event in raw['events']:
        count = event['messages'] + event['acknowledgements']
        if event.get('local_receipts') or event.get('local_obligations'):
            observer.observe_event(event, message_count=count)
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
            raise SystemExit('A prospective freeze already exists; never overwrite measured pins.')
        FREEZE.write_text(json.dumps(manifest(), indent=2)+'\n')
        print(FREEZE, flush=True)
    if not args.run:
        return
    frozen = json.loads(FREEZE.read_text())
    if frozen != manifest():
        raise SystemExit('Measured source/input differs from prospective freeze.')
    plan = json.loads(PLAN.read_text())
    inputs = json.loads(INPUT.read_text())
    if inputs['plan_sha256'] != sha(PLAN):
        raise SystemExit('Workload plan pin mismatch.')
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [(case, method) for case in inputs['cases'] for method in plan['methods']]
    control = plan['negative_control']
    jobs += [(next(c for c in inputs['cases'] if c['seed'] == control['seed']),
              control['method'])]
    assert len(jobs) == plan['expected_runs']
    metadata = dict(freeze=frozen, python=platform.python_version(),
                    sqlite=sqlite3.sqlite_version, platform=platform.platform(),
                    complete=False, runs=[])
    for case, method in jobs:
        destination = OUT / f"{case['name']}-{method}.json.gz"
        if destination.exists():
            with gzip.open(destination, 'rt') as handle:
                run = json.load(handle)
            if run['freeze'] != frozen or run['case_sha256'] != case['sha256']:
                raise SystemExit('Existing result has different source/input pins.')
        else:
            print(f"START {case['name']} {method}", flush=True)
            run = run_case(case, method, plan)
            run['freeze'] = frozen
            temp = destination.with_suffix(destination.suffix+'.tmp')
            with temp.open('wb') as handle:
                with gzip.GzipFile(fileobj=handle, mode='wb', mtime=0) as compressed:
                    compressed.write(json.dumps(run, separators=(',', ':')).encode())
            temp.replace(destination)
        entry = dict(case=case['name'], seed=case['seed'], method=method,
                     file=destination.name, sha256=sha(destination),
                     runtime_seconds=run['runtime_seconds'],
                     initialization_seconds=run['initialization_seconds'],
                     messages=run['messages'], acknowledgements=run['acknowledgements'],
                     message_bytes=run['message_bytes'], ack_body_bytes=run['ack_body_bytes'],
                     delivery_failures=run['delivery_failures'],
                     retried_requests=run['retried_requests'],
                     censored=run['censored'], final=run['final'],
                     observer_final=run['observer']['final'])
        metadata['runs'].append(entry)
        (OUT / 'results.json').write_text(json.dumps(metadata, indent=2)+'\n')
        print(f"DONE {method} seed={case['seed']} "
              f"debt={run['final']['debt']} requests={run['messages']} "
              f"runtime={run['runtime_seconds']:.2f}s "
              f"posted={run['observer']['final']['incorporated']['obligation']}", flush=True)
    metadata['complete'] = True
    (OUT / 'results.json').write_text(json.dumps(metadata, indent=2)+'\n')


if __name__ == '__main__':
    main()
