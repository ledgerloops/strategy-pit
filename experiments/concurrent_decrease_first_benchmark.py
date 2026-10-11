"""Preregistered concurrent decrease-first training and conditional held-out run."""
from collections import Counter,defaultdict
from dataclasses import asdict
import argparse
import hashlib
import json
from pathlib import Path
from concurrent_headroom import ConcurrentHeadroom
from concurrent_decrease_first import DecreaseFirstHeadroom
from concurrent_headroom_benchmark import observe
from temporal_benchmark import synthetic,sleeps_for
from temporal_sarafu import net_graph
from test_concurrent_headroom_audit import audit_signed_ledger

SOURCES=['concurrent_headroom.py','concurrent_decrease_first.py','temporal_episodes.py',
 'temporal_protocol.py','distributed.py','numbat.py','temporal_benchmark.py',
 'temporal_sarafu.py','test_concurrent_headroom_audit.py','concurrent_headroom_benchmark.py',
 'concurrent_decrease_first_benchmark.py','CONCURRENT-DECREASE-FIRST-PLAN.md']

def hashes():
    return {p:hashlib.sha256(Path(__file__).with_name(p).read_bytes()).hexdigest() for p in SOURCES}

def run_case(events,seed,loss,sleep,method):
    restoration=method!='disabled'
    cls=DecreaseFirstHeadroom if method=='decrease_first' else ConcurrentHeadroom
    horizon=800;budget=2_000_000
    sim=cls(seed=seed,restoration=restoration,loss=loss,ack_loss=loss,
        retry_interval=50,max_delay=5,retransmit=20,max_hops=32,search_budget=96)
    for node,start,duration in sleeps_for(events,seed,sleep,horizon):sim.add_sleep(node,start,duration)
    for e in events:sim.add_transfer(e.source,e.target,e.amount,at=e.time)
    row=dict(method=method,seed=seed,loss=loss,sleep=sleep,restoration=restoration,horizon=horizon,event_budget_per_run_and_drain=budget,
        arrival_sha256=hashlib.sha256(json.dumps([asdict(e) for e in events],sort_keys=True).encode()).hexdigest(),
        no_clearing_final_debt=sum(net_graph(events).values()),complete=False)
    try:
        sim.run(horizon,max_events=budget)
        posted=sum(v for _,_,_,v in sim.transfer_records)
        row['at_horizon']=dict(debt=sum(sim.graph_snapshot().values()),posted_transfers=len(sim.transfer_records),
            pending_transfer_count=sum(map(len,sim.transfer_queues.values())),unposted_transfer_volume=sum(e.amount for e in events)-posted,
            reservations=sim.pending_reservations,pending_envelopes=len(sim.pending))
        sim.drain(max_events=budget)
        row['audit']=audit_signed_ledger(sim)
        assert Counter((e.source,e.target,e.amount) for e in events)==Counter((a,b,v) for _,a,b,v in sim.transfer_records)
        row['complete']=True
    except (AssertionError,RuntimeError) as error:
        row['error']=f'{type(error).__name__}: {error}'
    row.update(final_debt=sum(sim.graph_snapshot().values()),final_time=sim.time,metrics=dict(sim.metrics),observation=observe(sim.ledger_records,horizon))
    requests=defaultdict(list)
    for e in events: requests[frozenset((e.source,e.target))].append(e)
    offsets=Counter()
    posting_area=0
    for at,a,b,amount in sim.transfer_records:
        pair=frozenset((a,b))
        e=requests[pair][offsets[pair]]
        offsets[pair]+=1
        assert (a,b,amount)==(e.source,e.target,e.amount)
        posting_area+=amount*(at-e.time)
    row['posting_amount_ticks_through_trace']=posting_area
    row['pending_transfers_at_end']=sum(map(len,sim.transfer_queues.values()))
    row['pending_envelopes_at_end']=len(sim.pending)
    row['pending_reservations_at_end']=sim.pending_reservations
    return row

def gate(rows):
    if len(rows)!=36 or not all(r['complete'] for r in rows):
        return dict(passed=False,reason='Incomplete matrix')
    totals={}
    for method in ('disabled','original','decrease_first'):
        rs=[r for r in rows if r['method']==method]
        totals[method]=dict(debt=sum(r['final_debt'] for r in rs),
            wire=sum(r['metrics'].get('data_attempts',0)+r['metrics'].get('ack_attempts',0) for r in rs),
            unposted_count=sum(r['at_horizon']['pending_transfer_count'] for r in rs),
            unposted_amount=sum(r['at_horizon']['unposted_transfer_volume'] for r in rs),
            posting_exposure=sum(r['posting_amount_ticks_through_trace'] for r in rs),
            staged_exposure=sum(r['observation']['partial_settlement_exposure_area'] for r in rs))
    base,new=totals['disabled'],totals['decrease_first']
    passed=new['debt']<=base['debt'] and new['wire']<=1.1*base['wire'] and new['unposted_count']<=base['unposted_count'] and new['unposted_amount']<=base['unposted_amount']
    return dict(passed=passed,totals=totals)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True)
    p.add_argument('--heldout-after')
    args=p.parse_args()
    output=Path(args.output)
    if output.exists():raise RuntimeError('Choose fresh output path')
    source=hashes()
    seeds=(201,202)
    if args.heldout_after:
        training=json.loads(Path(args.heldout_after).read_text())
        assert training['complete'] and training['gate']['passed'] and training['source_sha256']==source
        seeds=(203,204)
    report=dict(complete=False,source_sha256=source,seeds=seeds,rows=[],
                parameters=dict(retry_interval=50,max_delay=5,retransmit=20,max_hops=32,search_budget=96,horizon=800,event_budget_per_run_and_drain=2_000_000))
    def save():
        output.parent.mkdir(parents=True,exist_ok=True)
        tmp=output.with_suffix('.tmp');tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(output)
    save()
    for kind in ('sparse','community','bursts'):
        for seed in seeds:
            events=synthetic(kind,12,seed)
            for loss,sleep in ((0.,False),(.3,True)):
                for method in ('disabled','original','decrease_first'):
                    assert hashes()==source,'Source changed; checkpoint preserved'
                    row=run_case(events,seed,loss,sleep,method)
                    row.update(kind=kind,nodes=12)
                    report['rows'].append(row);save()
                    print(len(report['rows']),method,row['complete'],flush=True)
    assert hashes()==source
    report['complete']=all(r['complete'] for r in report['rows'])
    report['gate']=gate(report['rows'])
    save()

if __name__=='__main__':main()
