"""Small versioned diagnostic matrix; preserves posted-debt metrics beside U/K.

Not a model-selection sweep. No combined score. Inputs and observer source hashes
are pinned; decisions use exactly the existing frozen algorithm implementations.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from temporal_protocol import TemporalProtocol
from temporal_turns import TurnTemporalProtocol
from temporal_priority import PriorityTurnTemporalProtocol
from temporal_benchmark import synthetic,sleeps_for,audit
from temporal_metrics import temporal_exposure

SOURCES=('distributed.py','numbat.py','temporal_protocol.py','local_turns.py',
         'temporal_turns.py','temporal_priority.py','temporal_benchmark.py',
         'temporal_sarafu.py','temporal_metrics.py','temporal_metrics_benchmark.py')


def hashes():
    return {name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in SOURCES}


def case(events,method,seed,loss,sleep):
    algorithm='numbat' if method in ('fifo','priority') else method
    cls=PriorityTurnTemporalProtocol if method=='priority' else TurnTemporalProtocol if method=='fifo' else TemporalProtocol
    sim=cls(algorithm=algorithm,seed=seed,loss=loss,retransmit=20,max_delay=5,
            retry_interval=50,max_hops=32,search_budget=96)
    horizon=500
    for node,start,duration in sleeps_for(events,seed,sleep,horizon):
        sim.add_sleep(node,start,duration)
    for e in events:
        sim.add_transfer(e.source,e.target,e.amount,at=e.time)
    sim.run(horizon,max_events=2_000_000)
    at_horizon=dict(pending_envelopes=len(sim.pending),reservations=sim.pending_reservations,
                    unposted_transfers=len(events)-sim.metrics['transfers'],
                    queued_gate_payloads=sum(len(e.outbox) for e in getattr(sim,'turn_endpoints',{}).values()),
                    pending_grants=sum(e.pending_grant is not None for e in getattr(sim,'turn_endpoints',{}).values()))
    sim.drain(max_events=2_000_000)
    checked=audit(sim,events,horizon)
    exposure=temporal_exposure(sim,events,horizon)
    return dict(method=method,algorithm=algorithm,seed=seed,loss=loss,sleep=sleep,
                at_horizon=at_horizon,audit=checked,exposure=exposure,
                metrics=dict(sim.metrics),drained_at=sim.time)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    output=Path(args.output)
    frozen=hashes()
    report=dict(complete=False,metric_version=1,source_sha256=frozen,rows=[],
                purpose='Diagnostic temporal-exposure comparison; no tuning or combined score.',
                parameters=dict(horizon=500,seeds=[101,102],nodes=12,retry_interval=50,
                                search_budget=96,max_hops=32,retransmit=20,max_delay=5,event_budget=2_000_000))
    def save():
        output.parent.mkdir(parents=True,exist_ok=True)
        tmp=output.with_suffix('.tmp')
        tmp.write_text(json.dumps(report,indent=2)+'\n')
        tmp.replace(output)
    save()
    for seed in (101,102):
        for kind in ('community','bursts'):
            events=synthetic(kind,12,seed)
            for loss,sleep in ((0,False),(.3,True)):
                for method in ('numbat','random','largest','fifo','priority'):
                    if hashes()!=frozen:
                        raise RuntimeError('Source changed; checkpoint preserved')
                    row=case(events,method,seed,loss,sleep)
                    row.update(kind=kind,arrival_sha256=hashlib.sha256(json.dumps([asdict(e) for e in events],sort_keys=True).encode()).hexdigest())
                    report['rows'].append(row)
                    save()
                    print(len(report['rows']),kind,seed,loss,method,flush=True)
    if hashes()!=frozen:
        raise RuntimeError('Source changed during final run; checkpoint preserved')
    report['complete']=True
    save()


if __name__=='__main__':
    main()
