"""Preregistered reservation-triggered initiation backoff training; no tuning."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from temporal_backoff import BackoffTemporalProtocol
from temporal_benchmark import synthetic, sleeps_for, audit
from temporal_metrics import temporal_exposure

SOURCES=('distributed.py','numbat.py','temporal_protocol.py','temporal_episodes.py',
         'temporal_backoff.py','temporal_benchmark.py','temporal_sarafu.py',
         'temporal_metrics.py','temporal_backoff_benchmark.py','TEMPORAL-CONTENTION.md')


def hashes():
    return {name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in SOURCES}


def case(events, algorithm, seed, loss, sleep, enabled):
    sim=BackoffTemporalProtocol(algorithm=algorithm,seed=seed,loss=loss,
            backoff_enabled=enabled,retransmit=20,max_delay=3,retry_interval=50,
            max_hops=64,search_budget=64)
    for node,start,duration in sleeps_for(events,seed,sleep,800):
        sim.add_sleep(node,start,duration)
    for e in events:
        sim.add_transfer(e.source,e.target,e.amount,at=e.time)
    result=dict(algorithm=algorithm,seed=seed,loss=loss,sleep=sleep,backoff=enabled,
                arrival_sha256=hashlib.sha256(json.dumps([asdict(e) for e in events],sort_keys=True).encode()).hexdigest())
    try:
        sim.run(800,max_events=2_000_000)
        result['at_horizon']=dict(pending_envelopes=len(sim.pending),
                reservations=sim.pending_reservations,
                unposted_transfers=len(events)-sim.metrics['transfers'])
        sim.drain(max_events=2_000_000)
        result['audit']=audit(sim,events,800)
        result['complete']=True
    except (RuntimeError,AssertionError) as error:
        result.update(complete=False,error=f'{type(error).__name__}: {error}')
    result['exposure']=temporal_exposure(sim,events,800,allow_incomplete=not result['complete'])
    result.update(metrics=dict(sim.metrics),final_time=sim.time,
                  pending_envelopes=len(sim.pending),pending_reservations=sim.pending_reservations,
                  pending_transfers=sum(map(len,sim.transfer_queues.values())))
    return result


def gate(rows,algorithm):
    selected=[row for row in rows if row['algorithm']==algorithm]
    if len(selected)!=48 or not all(row['complete'] for row in selected):
        return dict(passed=False,reason='Incomplete paired matrix')
    group={value:[row for row in selected if row['backoff']==value] for value in (False,True)}
    def totals(enabled):
        rs=group[enabled]
        return dict(final_debt=sum(r['audit']['final_debt_scaled'] for r in rs),
                    wire=sum(r['exposure']['wire_attempts_data_plus_ack'] for r in rs),
                    posting=sum(r['exposure']['external_posting_amount_ticks_through_drain'] for r in rs),
                    staged=sum(r['exposure']['committed_edge_amount_ticks_awaiting_cycle_completion_through_drain'] for r in rs))
    base,new=totals(False),totals(True)
    worse=sum(b['audit']['final_debt_scaled']>a['audit']['final_debt_scaled'] for a,b in zip(group[False],group[True]))
    passed=(new['final_debt']<=base['final_debt'] and new['wire']<=.95*base['wire']
            and new['posting']<=base['posting'] and new['staged']<=base['staged'] and worse<=6)
    return dict(passed=passed,baseline=base,backoff=new,higher_final_debt_pairs=worse,pairs=24)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    output=Path(args.output)
    if output.exists():
        raise RuntimeError('Refusing to overwrite an existing experiment')
    frozen=hashes()
    report=dict(complete=False,source_sha256=frozen,rows=[],
                parameters=dict(horizon=800,arrival_ticks=500,seeds=[101,102],nodes=[12,24],
                event_budget_per_run_and_drain=2_000_000,retransmit=20,max_delay=3,retry_interval=50,max_hops=64,search_budget=64),
                randomness_note='Same arrivals and sleep schedules. Packet loss draws are activity-dependent.')
    def save():
        output.parent.mkdir(parents=True,exist_ok=True)
        tmp=output.with_suffix('.tmp')
        tmp.write_text(json.dumps(report,indent=2)+'\n')
        tmp.replace(output)
    save()
    for nodes in (12,24):
        for kind in ('sparse','community','bursts'):
            for seed in (101,102):
                events=synthetic(kind,nodes,seed)
                for loss,sleep in ((0,False),(.1,True)):
                    for algorithm in ('random','numbat'):
                        for enabled in (False,True):
                            if hashes()!=frozen:
                                raise RuntimeError('Source changed; checkpoint preserved')
                            row=case(events,algorithm,seed,loss,sleep,enabled)
                            row.update(nodes=nodes,kind=kind)
                            report['rows'].append(row)
                            save()
                            print(len(report['rows']),algorithm,enabled,row['complete'],flush=True)
    if hashes()!=frozen:
        raise RuntimeError('Source changed; checkpoint preserved')
    report['complete']=all(row['complete'] for row in report['rows'])
    report['gates']={algorithm:gate(report['rows'],algorithm) for algorithm in ('random','numbat')}
    save()


if __name__=='__main__':
    main()
