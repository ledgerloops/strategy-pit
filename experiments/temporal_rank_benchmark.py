"""Fixed rank-weighted Numbat training and conditional held-out matrix."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from temporal_episodes import EpisodeTemporalProtocol
from temporal_rank import RankTemporalProtocol
from temporal_benchmark import synthetic, sleeps_for, audit
from temporal_metrics import temporal_exposure

SOURCES=('distributed.py','numbat.py','temporal_protocol.py','temporal_episodes.py',
         'temporal_rank.py','temporal_benchmark.py','temporal_sarafu.py',
         'temporal_metrics.py','temporal_rank_benchmark.py','TEMPORAL-RANK-PLAN.md')


def hashes():
    return {name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in SOURCES}

def case(events, method, seed, loss, sleep):
    algorithm='numbat' if method=='rank' else method
    cls=RankTemporalProtocol if method=='rank' else EpisodeTemporalProtocol
    sim=cls(algorithm=algorithm,seed=seed,loss=loss,
            retransmit=20,max_delay=5,retry_interval=50,
            max_hops=32,search_budget=96)
    for node,start,duration in sleeps_for(events,seed,sleep,800):
        sim.add_sleep(node,start,duration)
    for e in events:
        sim.add_transfer(e.source,e.target,e.amount,at=e.time)
    result=dict(algorithm=algorithm,seed=seed,loss=loss,sleep=sleep,method=method,
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

def gate(rows):
    if len(rows)!=72 or not all(row['complete'] for row in rows):
        return dict(passed=False,reason='Incomplete matrix')
    totals={}
    for method in ('random','numbat','rank'):
        rs=[r for r in rows if r['method']==method]
        totals[method]=dict(debt=sum(r['audit']['final_debt_scaled'] for r in rs),
            wire=sum(r['exposure']['wire_attempts_data_plus_ack'] for r in rs),
            unposted_count=sum(r['at_horizon']['unposted_transfers'] for r in rs),
            unposted_amount=sum(r['exposure']['unposted_amount_at_horizon'] for r in rs),
            posting_exposure=sum(r['exposure']['external_posting_amount_ticks_through_drain'] for r in rs),
            staged_exposure=sum(r['exposure']['committed_edge_amount_ticks_awaiting_cycle_completion_through_drain'] for r in rs))
    reference=min(('random','numbat'),key=lambda method:totals[method]['debt'])
    base,new=totals[reference],totals['rank']
    passed=new['debt']<base['debt'] and new['wire']<=1.1*base['wire'] and new['unposted_count']<=base['unposted_count'] and new['unposted_amount']<=base['unposted_amount']
    return dict(passed=passed,reference=reference,totals=totals)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--heldout-after')
    args=parser.parse_args()
    output=Path(args.output)
    if output.exists():raise RuntimeError('Refusing to overwrite existing experiment')
    frozen=hashes()
    seeds=(301,302)
    if args.heldout_after:
        training=json.loads(Path(args.heldout_after).read_text())
        assert training['complete'] and training['gate']['passed'] and training['source_sha256']==frozen
        seeds=(303,304)
    report=dict(complete=False,source_sha256=frozen,rows=[],
        parameters=dict(horizon=800,arrival_ticks=500,seeds=seeds,nodes=[24,72],
            event_budget_per_run_and_drain=2_000_000,retransmit=20,max_delay=5,retry_interval=50,max_hops=32,search_budget=96),
        randomness_note='Same arrivals and sleeps. Packet loss draws depend on activity.')
    def save():
        output.parent.mkdir(parents=True,exist_ok=True)
        tmp=output.with_suffix('.tmp');tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(output)
    save()
    for nodes in (24,72):
        for kind in ('sparse','community','bursts'):
            for seed in seeds:
                events=synthetic(kind,nodes,seed)
                for loss,sleep in ((0,False),(.3,True)):
                    for method in ('random','numbat','rank'):
                        assert hashes()==frozen,'Source changed; checkpoint preserved'
                        row=case(events,method,seed,loss,sleep)
                        row.update(nodes=nodes,kind=kind)
                        report['rows'].append(row);save()
                        print(len(report['rows']),method,row['complete'],flush=True)
    assert hashes()==frozen
    report['complete']=all(row['complete'] for row in report['rows'])
    report['gate']=gate(report['rows'])
    save()

if __name__=='__main__':main()
