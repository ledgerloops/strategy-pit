"""Frozen exploratory matched-control matrix; not held-out model selection."""
from collections import Counter,defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from concurrent_headroom import ConcurrentHeadroom
from temporal_benchmark import synthetic,sleeps_for
from temporal_sarafu import net_graph
from test_concurrent_headroom_audit import audit_signed_ledger

ROOT=Path(__file__).resolve().parent
SOURCES=['concurrent_headroom.py','temporal_episodes.py','temporal_protocol.py','distributed.py','numbat.py','temporal_benchmark.py','temporal_sarafu.py','test_concurrent_headroom_audit.py','concurrent_headroom_benchmark.py']


def hashes():
    return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES}


def observe(records,horizon):
    graph={};debts=0;area=0;previous=0
    txnet=defaultdict(Counter);exposure=0;exposure_area=0;peak=0
    for record in records:
        at=record['time']
        duration=max(0,min(at,horizon)-min(previous,horizon))
        area+=debts*duration;exposure_area+=exposure*duration
        previous=at
        a,b,delta=record['source'],record['target'],record['delta']
        if record['kind']=='transfer':
            old=graph.pop((a,b),0)-graph.pop((b,a),0)
            new=old+delta;debts+=abs(new)-abs(old)
            if new>0:graph[a,b]=new
            elif new<0:graph[b,a]=-new
        else:
            graph[a,b]=graph.get((a,b),0)+delta
            if not graph[a,b]:del graph[a,b]
            debts+=delta
            net=txnet[record['txid']]
            before=sum(abs(v) for v in net.values())//2
            net[a]-=delta;net[b]+=delta
            exposure+=sum(abs(v) for v in net.values())//2-before
            if at<=horizon:peak=max(peak,exposure)
    duration=max(0,horizon-previous)
    area+=debts*duration;exposure_area+=exposure*duration
    return dict(posted_debt_area=area,partial_settlement_exposure_area=exposure_area,
                peak_partial_settlement_exposure=peak,final_partial_settlement_exposure=exposure)


def run_case(events,seed,loss,sleep,restoration):
    horizon=800;budget=2_000_000
    sim=ConcurrentHeadroom(seed=seed,restoration=restoration,loss=loss,ack_loss=loss,
        retry_interval=50,max_delay=5,retransmit=20,max_hops=32,search_budget=96)
    for node,start,duration in sleeps_for(events,seed,sleep,horizon):sim.add_sleep(node,start,duration)
    for e in events:sim.add_transfer(e.source,e.target,e.amount,at=e.time)
    row=dict(seed=seed,loss=loss,sleep=sleep,restoration=restoration,horizon=horizon,event_budget_per_run_and_drain=budget,
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
    return row


def main():
    source=hashes()
    report=dict(complete=False,source_sha256=source,rows=[],
        scope='Exploratory 12-node 3-family seeds0/1 matched restoration control; no held-out claim',
        parameters=dict(retry_interval=50,max_delay=5,retransmit=20,max_hops=32,search_budget=96),
        note='Posted-debt area can benefit from delayed input; compare unposted volume too. Exposure sums per-transaction half-L1 net imbalances; staged cycles are not atomic. Same arrival/sleep seeds; transport RNG draw streams differ by activity.')
    out=ROOT/'results/concurrent-headroom-synthetic.json'
    def save():
        tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(out)
    for kind in ('sparse','community','bursts'):
        for seed in (0,1):
            events=synthetic(kind,12,seed)
            for loss,sleep in ((0.,False),(.3,True)):
                for restoration in (False,True):
                    assert hashes()==source,'source changed during benchmark'
                    row=run_case(events,seed,loss,sleep,restoration)
                    row.update(kind=kind,nodes=12)
                    report['rows'].append(row);save()
    report['complete']=all(r['complete'] for r in report['rows'])
    save()
    print(json.dumps(dict(rows=len(report['rows']),complete=report['complete'])))

if __name__=='__main__':main()
