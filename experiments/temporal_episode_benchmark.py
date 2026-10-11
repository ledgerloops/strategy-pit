"""Matched strict-channel-episode experiments; scoring is external to actors."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
from temporal_benchmark import audit, synthetic, sleeps_for
from temporal_sarafu import load_sarafu, Transfer, net_graph
from temporal_episodes import EpisodeTemporalProtocol
from temporal_metrics import temporal_exposure

ROOT = Path(__file__).parent
SOURCES = ('distributed.py', 'numbat.py', 'temporal_protocol.py', 'temporal_episodes.py',
           'temporal_benchmark.py', 'temporal_sarafu.py', 'temporal_metrics.py', 'temporal_episode_benchmark.py')


def hashes():
    return {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCES}


def run_case(events, *, algorithm, seed, loss, sleep, horizon, event_budget):
    sim = EpisodeTemporalProtocol(algorithm=algorithm, seed=seed, loss=loss,
        transport='concurrent', retransmit=20, max_delay=5, retry_interval=50,
        max_hops=32, search_budget=96)
    for node, start, duration in sleeps_for(events, seed, sleep, horizon):
        sim.add_sleep(node, start, duration)
    for event in events:
        if event.amount and event.source != event.target:
            sim.add_transfer(event.source, event.target, event.amount, at=event.time)
    result = dict(algorithm=algorithm, seed=seed, loss=loss, ack_loss=loss,
        sleep=sleep, horizon=horizon, event_budget_per_phase=event_budget,
        transport='concurrent', arrivals=len(events),
        arrival_sha256=hashlib.sha256(json.dumps([asdict(e) for e in events], sort_keys=True).encode()).hexdigest(),
        no_clearing_final_debt_scaled=sum(net_graph(events).values()),
        parameters=dict(retransmit=20,max_delay=5,retry_interval=50,max_hops=32,search_budget=96))
    start=time.monotonic()
    try:
        sim.run(horizon, max_events=event_budget)
        result['at_horizon']=dict(time=sim.time, pending_envelopes=len(sim.pending),
            pending_reservations=sim.pending_reservations,
            pending_transfers=sum(map(len,sim.transfer_queues.values())),
            posted_transfers=len(sim.transfer_records), debt_scaled=sum(sim.graph_snapshot().values()),
            metrics=dict(sim.metrics))
        sim.drain(max_events=event_budget)
        result['audit']=audit(sim,events,horizon)
        result['complete']=True
    except (RuntimeError,AssertionError) as error:
        result.update(complete=False,error=f'{type(error).__name__}: {error}')
    result['exposure']=temporal_exposure(sim,events,horizon,allow_incomplete=not result['complete'])
    result.update(final_time=sim.time, metrics=dict(sim.metrics),
        pending_envelopes=len(sim.pending), pending_reservations=sim.pending_reservations,
        pending_transfers=sum(map(len,sim.transfer_queues.values())), elapsed_seconds=time.monotonic()-start)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=['smoke','synthetic','sarafu'], default='smoke')
    parser.add_argument('--csv')
    parser.add_argument('--limit',type=int,default=5000)
    parser.add_argument('--arrival-ticks',type=int,default=1000)
    parser.add_argument('--event-budget',type=int,default=2_000_000)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if args.limit<0 or args.arrival_ticks<=0 or args.event_budget<=0:
        parser.error('Invalid limit, arrival clock or event budget')
    source=hashes()
    config=vars(args).copy(); config.pop('output')
    report=dict(complete=False,configuration=config,source_sha256=source,rows=[],
        fault_note='Equal loss probabilities and common arrival/sleep schedules; packet random draws differ with algorithm activity.',
        audit_note='Ordered per-edge replay. Posted debt area omits delayed input, so inspect pending input and exposure too.')
    fixtures=[]
    if args.suite=='sarafu':
        if not args.csv:
            parser.error('--csv required')
        fixture=load_sarafu(args.csv,tick_microseconds=1)
        selected=fixture.events[:args.limit] if args.limit else fixture.events
        scale=max(1,(selected[-1].time+args.arrival_ticks-1)//args.arrival_ticks)
        events=tuple(Transfer(e.time//scale,e.source,e.target,e.amount,e.row_number) for e in selected)
        report['fixture_metadata']=fixture.metadata
        report['selection']=dict(first_standard_transfers=len(events),tick_microseconds=scale,
            original_elapsed_microseconds=selected[-1].time,compressed_last_tick=events[-1].time)
        fixtures=[(dict(kind='sarafu-prefix'),events,seed,args.arrival_ticks+300) for seed in [0,1]]
    else:
        for nodes in ([12] if args.suite=='smoke' else [12,24]):
            for kind in (['sparse'] if args.suite=='smoke' else ['sparse','community','bursts']):
                for seed in ([0] if args.suite=='smoke' else [0,1]):
                    fixtures.append((dict(kind=kind,nodes=nodes),synthetic(kind,nodes,seed),seed,800))
    cases=[]
    for label,events,seed,horizon in fixtures:
        for loss in ([0,.3] if args.suite=='smoke' else [0,.1,.3]):
            for sleep in [False,True]:
                for algorithm in ['random','numbat']:
                    cases.append((label,events,dict(seed=seed,horizon=horizon,loss=loss,sleep=sleep,algorithm=algorithm,event_budget=args.event_budget)))
    report['planned_cases']=len(cases)
    output=Path(args.output)
    if output.exists():
        previous=json.loads(output.read_text())
        if previous['configuration']!=config or previous['source_sha256']!=source:
            raise RuntimeError('Refusing to mix source/configurations; use a new output')
        report=previous
    def checkpoint():
        output.parent.mkdir(parents=True,exist_ok=True)
        tmp=output.with_suffix(output.suffix+'.tmp')
        tmp.write_text(json.dumps(report,indent=2)+'\n'); tmp.replace(output)
    checkpoint()
    for label,events,kwargs in cases[len(report['rows']):]:
        if hashes()!=source:
            raise RuntimeError('Source changed during benchmark')
        row=run_case(events,**kwargs); row.update(label)
        report['rows'].append(row); checkpoint()
        print(f"{len(report['rows'])}/{len(cases)} {label['kind']} {kwargs} complete={row['complete']}",flush=True)
    report['complete']=len(report['rows'])==len(cases) and all(r['complete'] for r in report['rows'])
    checkpoint()


if __name__=='__main__':
    main()
