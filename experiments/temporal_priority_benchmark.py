"""Frozen prospective priority experiment; training seeds precede held-out seeds.

Training is promising only when priority improves aggregate debt area, does not
increase aggregate final debt, and uses <=110% of FIFO wire attempts. Comparison
to concurrent remains visible even if priority improves its FIFO parent.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from temporal_protocol import TemporalProtocol
from temporal_turns import TurnTemporalProtocol
from temporal_priority import PriorityTurnTemporalProtocol
from temporal_benchmark import synthetic, sleeps_for, audit

SOURCES = ('distributed.py','numbat.py','temporal_protocol.py','local_turns.py',
           'temporal_turns.py','temporal_priority.py','temporal_benchmark.py',
           'temporal_sarafu.py','temporal_priority_benchmark.py')


def source_hashes():
    return {p:hashlib.sha256(Path(__file__).with_name(p).read_bytes()).hexdigest() for p in SOURCES}


def run_case(events,method,seed,loss,sleep):
    cls = {'concurrent':TemporalProtocol,'fifo':TurnTemporalProtocol,'priority':PriorityTurnTemporalProtocol}[method]
    sim = cls(algorithm='numbat',seed=seed,loss=loss,retransmit=20,max_delay=5,
              retry_interval=50,max_hops=32,search_budget=96)
    for node,start,duration in sleeps_for(events,seed,sleep,800):
        sim.add_sleep(node,start,duration)
    for e in events:
        sim.add_transfer(e.source,e.target,e.amount,at=e.time)
    sim.run(800,max_events=2_000_000)
    horizon = dict(applied=sim.metrics['transfers'],requested=len(events),
                   pending=len(sim.pending),reservations=sim.pending_reservations)
    sim.drain(max_events=2_000_000)
    checked = audit(sim,events,800)
    return dict(method=method,seed=seed,loss=loss,sleep=sleep,at_horizon=horizon,audit=checked,
                metrics=dict(sim.metrics),drained_at=sim.time,
                priority_pops=sum(getattr(e.outbox,'priority_pops',0)
                                  for e in getattr(sim,'turn_endpoints',{}).values()))


def summary(rows):
    totals = {}
    for method in ('concurrent','fifo','priority'):
        group = [r for r in rows if r['method']==method]
        totals[method] = dict(debt_area=sum(r['audit']['debt_amount_ticks_to_horizon'] for r in group),
                             final_debt=sum(r['audit']['final_debt_scaled'] for r in group),
                             wire_attempts=sum(r['metrics'].get('data_attempts',0)+r['metrics'].get('ack_attempts',0) for r in group),
                             transfer_delay=sum(r['metrics'].get('transfer_delay',0) for r in group),
                             horizon_unposted=sum(r['at_horizon']['requested']-r['at_horizon']['applied'] for r in group))
    p,f=totals['priority'],totals['fifo']
    promising = p['debt_area']<f['debt_area'] and p['final_debt']<=f['final_debt'] and p['wire_attempts']<=1.1*f['wire_attempts']
    return dict(totals=totals,promising=promising,criterion='Debt area strictly lower, final debt no worse, wire attempts <=110% of FIFO; fixed before training. Posted-ledger area excludes unposted transfers; horizon backlog and total posting delay reported separately.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    path=Path(args.output)
    frozen=source_hashes()
    report=dict(complete=False,source_sha256=frozen,priority_burst=4,turn_batch=8,
                parameters=dict(horizon=800,retry_interval=50,max_hops=32,search_budget=96,event_budget=2_000_000),
                training_seeds=[101,102],heldout_seeds=[0,1],training=[],heldout=[])
    def save():
        path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix('.tmp')
        tmp.write_text(json.dumps(report,indent=2)+'\n')
        tmp.replace(path)
    save()
    for phase,seeds in [('training',[101,102]),('heldout',[0,1])]:
        if phase=='heldout' and not report['training_summary']['promising']:
            report['heldout_skipped']='Training did not meet preregistered improvement criterion.'
            break
        for seed in seeds:
            for kind in ('sparse','community','bursts'):
                events=synthetic(kind,24,seed)
                for loss,sleep in ((0,False),(.3,True)):
                    for method in ('concurrent','fifo','priority'):
                        if source_hashes()!=frozen:
                            raise RuntimeError('Source changed; refuse mixed-source results')
                        result=run_case(events,method,seed,loss,sleep)
                        result.update(kind=kind,nodes=24,
                                      arrival_sha256=hashlib.sha256(json.dumps([asdict(e) for e in events],sort_keys=True).encode()).hexdigest())
                        report[phase].append(result)
                        save()
                        print(phase,len(report[phase]),kind,seed,loss,method,flush=True)
        report[phase+'_summary']=summary(report[phase])
        save()
    report['complete']=True
    save()


if __name__=='__main__':
    main()
