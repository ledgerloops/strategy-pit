"""One frozen exploration-mixture hypothesis; training gates held-out evaluation.

Promising means aggregate debt area decreases, final debt does not increase,
wire attempts stay <=110% of original Numbat, and cutoff unposted arrivals do
not increase. Uniform random remains a visible control. No parameter search.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from temporal_exploration import ExplorationTemporalProtocol
from temporal_protocol import TemporalProtocol
from temporal_benchmark import synthetic, sleeps_for, audit

ROOT = Path(__file__).parent
SOURCES = ('distributed.py', 'numbat.py', 'temporal_protocol.py', 'temporal_benchmark.py',
           'temporal_sarafu.py', 'temporal_exploration.py', 'temporal_exploration_benchmark.py')


def hashes():
    return {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCES}


def run_case(events, method, seed, loss, sleep):
    cls = ExplorationTemporalProtocol if method == 'mixture' else TemporalProtocol
    sim = cls(algorithm='random' if method == 'random' else 'numbat', seed=seed,
              loss=loss, retransmit=20, max_delay=5, retry_interval=50,
              max_hops=32, search_budget=96)
    for node, at, duration in sleeps_for(events, seed, sleep, 800):
        sim.add_sleep(node, at, duration)
    for event in events:
        sim.add_transfer(event.source, event.target, event.amount, at=event.time)
    sim.run(800, max_events=2_000_000)
    cutoff = dict(requested=len(events), applied=sim.metrics['transfers'],
                  pending_envelopes=len(sim.pending), pending_reservations=sim.pending_reservations,
                  queued_transfer_requests=sum(map(len, sim.transfer_queues.values())))
    sim.drain(max_events=2_000_000)
    return dict(method=method, seed=seed, loss=loss, sleep=sleep, at_cutoff=cutoff,
                metrics=dict(sim.metrics), audit=audit(sim, events, 800), drained_at=sim.time)


def summarize(rows):
    totals = {}
    for method in ('numbat', 'mixture', 'random'):
        group = [row for row in rows if row['method'] == method]
        totals[method] = dict(debt_area=sum(row['audit']['debt_amount_ticks_to_horizon'] for row in group),
                             final_debt=sum(row['audit']['final_debt_scaled'] for row in group),
                             wire_attempts=sum(row['metrics'].get('data_attempts', 0)+row['metrics'].get('ack_attempts', 0) for row in group),
                             unposted=sum(row['at_cutoff']['requested']-row['at_cutoff']['applied'] for row in group),
                             posting_delay=sum(row['metrics'].get('transfer_delay', 0) for row in group))
    variant, base = totals['mixture'], totals['numbat']
    promising = (variant['debt_area'] < base['debt_area']
                 and variant['final_debt'] <= base['final_debt']
                 and variant['wire_attempts'] <= 1.1*base['wire_attempts']
                 and variant['unposted'] <= base['unposted'])
    return dict(totals=totals, promising=promising,
                criterion='Lower debt area, no worse final debt, <=110% wire attempts and no more cutoff unposted inputs than Numbat; frozen before training.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'results/temporal-exploration.json')
    args = parser.parse_args()
    frozen = hashes()
    report = dict(complete=False, source_sha256=frozen, uniform_probability=.5,
                  capacity_power=4, training_seeds=[101, 102], heldout_seeds=[0, 1],
                  parameters=dict(horizon=800, nodes=24, max_hops=32, search_budget=96,
                                  retry_interval=50, max_delay=5, retransmit=20, event_budget=2_000_000),
                  assumptions=['Same horizons, arrivals, sleep intervals and delay/loss distributions.',
                    'Shared PRNG seeds do not imply identical packet loss realization across different traffic.',
                    'Completion includes post-cutoff drain; message attempts and backlog explicitly reported.',
                    'Global graph used only by offline independent auditor, never search selection.',
                    'Existing temporal control-channel grace semantics; not issue003 strict episode admission.'],
                  training=[], heldout=[])

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temp = args.output.with_suffix('.tmp')
        temp.write_text(json.dumps(report, indent=2)+'\n')
        temp.replace(args.output)

    save()
    for phase, seeds in (('training', [101, 102]), ('heldout', [0, 1])):
        if phase == 'heldout' and not report['training_summary']['promising']:
            report['heldout_skipped'] = 'Training did not pass preregistered improvement criterion.'
            break
        for seed in seeds:
            for topology in ('sparse', 'community', 'bursts'):
                events = synthetic(topology, 24, seed)
                for loss, sleep in ((0, False), (.3, True)):
                    for method in ('numbat', 'mixture', 'random'):
                        if hashes() != frozen:
                            raise RuntimeError('Source changed during frozen experiment')
                        row = run_case(events, method, seed, loss, sleep)
                        row.update(topology=topology,
                                   arrival_sha256=hashlib.sha256(json.dumps([asdict(e) for e in events], sort_keys=True).encode()).hexdigest())
                        report[phase].append(row)
                        save()
                        print(phase, topology, seed, loss, method, row['audit']['final_debt_scaled'], flush=True)
        report[phase+'_summary'] = summarize(report[phase])
        save()
    report['complete'] = True
    save()


if __name__ == '__main__':
    main()
