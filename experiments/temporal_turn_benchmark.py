"""Matched endpoint-local turns versus concurrent reliable transport.

Frozen baseline fixture and independent audit helpers are imported, never patched.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time

from temporal_benchmark import audit, hashes as baseline_hashes, sleeps_for, synthetic
from temporal_protocol import TemporalProtocol
from temporal_sarafu import Transfer, load_sarafu, net_graph
from temporal_turns import TurnTemporalProtocol

ROOT = Path(__file__).parent


def hashes():
    result = baseline_hashes()
    for name in ('local_turns.py', 'temporal_turns.py', 'temporal_turn_benchmark.py'):
        result[name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    return result


def run_case(events, *, algorithm, seed, loss, sleep, transport, horizon, event_budget=2_000_000):
    parameters = dict(retransmit=20, max_delay=5, retry_interval=50, max_hops=32, search_budget=96)
    cls = TurnTemporalProtocol if transport == 'local_turns' else TemporalProtocol
    sim = cls(algorithm=algorithm, seed=seed, loss=loss, transport=transport, **parameters)
    sleeps = sleeps_for(events, seed, sleep, horizon)
    for node, start, duration in sleeps:
        sim.add_sleep(node, start, duration)
    for event in events:
        if event.amount and event.source != event.target:
            sim.add_transfer(event.source, event.target, event.amount, at=event.time)
    start = time.monotonic()
    result = dict(algorithm=algorithm, seed=seed, loss=loss, ack_loss=loss, sleep=sleep,
                  transport=transport, horizon=horizon, arrivals=len(events), parameters=parameters,
                  turn_batch=8 if transport == 'local_turns' else None,
                  arrival_sha256=hashlib.sha256(json.dumps([asdict(e) for e in events], sort_keys=True).encode()).hexdigest(),
                  sleep_sha256=hashlib.sha256(json.dumps(sleeps).encode()).hexdigest(),
                  no_clearing_final_debt_scaled=sum(net_graph(events).values()))

    def pending():
        gates = getattr(sim, 'turn_endpoints', {})
        return dict(time=sim.time, pending_envelopes=len(sim.pending),
                    pending_reservations=sim.pending_reservations,
                    pending_transfers=sum(map(len, sim.transfer_queues.values())),
                    queued_turn_payloads=sum(len(g.outbox) for g in gates.values()),
                    pending_turn_grants=sum(g.pending_grant is not None for g in gates.values()),
                    posted_transfers=len(sim.transfer_records),
                    debt_scaled=sum(sim.graph_snapshot().values()), metrics=dict(sim.metrics))
    try:
        sim.run(horizon, max_events=event_budget)
        result['at_horizon'] = pending()
        sim.drain(max_events=event_budget)
        result['audit'] = audit(sim, events, horizon)
        result['complete'] = True
    except (RuntimeError, AssertionError) as error:
        result['complete'] = False
        result['error'] = f'{type(error).__name__}: {error}'
    result['after_drain'] = pending()
    result['elapsed_seconds'] = time.monotonic()-start
    return result


def paired_summary(rows):
    pairs = {}
    for row in rows:
        key = tuple(row[k] for k in ('kind', 'nodes', 'algorithm', 'seed', 'loss', 'sleep', 'horizon'))
        pairs.setdefault(key, {})[row['transport']] = row
    summary = dict(pairs=0, lower_final_debt=0, equal_final_debt=0, higher_final_debt=0,
                   lower_debt_area=0, equal_debt_area=0, higher_debt_area=0,
                   concurrent_wire_attempts=0, local_turn_wire_attempts=0,
                   concurrent_final_debt=0, local_turn_final_debt=0,
                   concurrent_debt_area=0, local_turn_debt_area=0)
    for pair in pairs.values():
        if set(pair) != {'concurrent', 'local_turns'} or not all(r['complete'] for r in pair.values()):
            continue
        base, turns = pair['concurrent'], pair['local_turns']
        assert base['arrival_sha256'] == turns['arrival_sha256']
        assert base['sleep_sha256'] == turns['sleep_sha256']
        summary['pairs'] += 1
        for label, field in [('final_debt', 'final_debt_scaled'), ('debt_area', 'debt_amount_ticks_to_horizon')]:
            a, b = base['audit'][field], turns['audit'][field]
            summary[('lower_' if b < a else 'higher_' if b > a else 'equal_') + label] += 1
            summary['concurrent_' + label] += a
            summary['local_turn_' + label] += b
        for name, row in [('concurrent', base), ('local_turn', turns)]:
            metrics = row['after_drain']['metrics']
            summary[name + '_wire_attempts'] += metrics.get('data_attempts', 0) + metrics.get('ack_attempts', 0)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=['smoke', 'synthetic', 'sarafu'], default='smoke')
    parser.add_argument('--csv')
    parser.add_argument('--limit', type=int, default=1000)
    parser.add_argument('--arrival-ticks', type=int, default=500)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    source = hashes()
    report = dict(suite=args.suite, source_sha256=source, complete=False, rows=[],
                  transport_note='local_turns is endpoint-local request/grant/epoch protocol over concurrent reliable transport; controls count',
                  fault_note='Shared seeded arrivals and sleeps, equal loss probabilities; actual draws depend on protocol activity',
                  audit_note='Debt area measures posted debt, so inspect deferred-transfer backlog too; post-drain endpoint times may differ')
    cases = []
    if args.suite in ('smoke', 'synthetic'):
        for nodes in ([12] if args.suite == 'smoke' else [12, 24]):
            for kind in (['sparse'] if args.suite == 'smoke' else ['sparse', 'community', 'bursts']):
                for seed in ([0] if args.suite == 'smoke' else [0, 1]):
                    events = synthetic(kind, nodes, seed)
                    for loss in ([.3] if args.suite == 'smoke' else [0, .1, .3]):
                        for sleep in [False, True]:
                            for algorithm in ['numbat', 'random', 'largest']:
                                for transport in ['concurrent', 'local_turns']:
                                    cases.append((dict(kind=kind, nodes=nodes), events,
                                                  dict(algorithm=algorithm, seed=seed, loss=loss, sleep=sleep,
                                                       transport=transport, horizon=800)))
    else:
        if not args.csv or args.limit <= 0 or args.arrival_ticks <= 0:
            parser.error('sarafu requires --csv and positive --limit/--arrival-ticks')
        fixture = load_sarafu(args.csv, tick_microseconds=1)
        selected = fixture.events[:args.limit]
        scale = max(1, (selected[-1].time + args.arrival_ticks - 1)//args.arrival_ticks)
        events = tuple(Transfer(e.time//scale, e.source, e.target, e.amount, e.row_number) for e in selected)
        report['fixture_metadata'] = fixture.metadata
        report['selection'] = dict(first_standard_transfers=len(events), tick_microseconds=scale,
                                   original_elapsed_microseconds=selected[-1].time,
                                   compressed_last_tick=events[-1].time,
                                   note='Actual timestamp gaps uniformly compressed; no real-time throughput claim')
        for seed in [0, 1]:
            for loss, sleep in [(0, False), (.1, True), (.3, True)]:
                for algorithm in ['numbat', 'random', 'largest']:
                    for transport in ['concurrent', 'local_turns']:
                        cases.append((dict(kind='sarafu-prefix', nodes=len({p for e in events for p in (e.source, e.target)})), events,
                                      dict(algorithm=algorithm, seed=seed, loss=loss, sleep=sleep,
                                           transport=transport, horizon=args.arrival_ticks+300)))
    report['planned_cases'] = len(cases)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)

    def checkpoint():
        report['paired_summary'] = paired_summary(report['rows'])
        temp = path.with_suffix(path.suffix+'.tmp')
        temp.write_text(json.dumps(report, indent=2)+'\n')
        temp.replace(path)
    checkpoint()
    for label, events, kwargs in cases:
        if hashes() != source:
            report['interrupted_reason'] = 'Source changed; affected batch not complete'
            checkpoint()
            raise RuntimeError(report['interrupted_reason'])
        result = run_case(events, **kwargs)
        result.update(label)
        report['rows'].append(result)
        checkpoint()
        print(f"{len(report['rows'])}/{len(cases)} {label['kind']} {kwargs['algorithm']} {kwargs['transport']} complete={result['complete']}", flush=True)
    report['complete'] = hashes() == source and all(r['complete'] for r in report['rows'])
    checkpoint()


if __name__ == '__main__':
    main()
