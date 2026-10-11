"""Prospective bounded full-prefix fault follow-up; run after prefix validation."""
import argparse
import hashlib
import json
from pathlib import Path
from temporal_episode_benchmark import run_case, hashes as base_hashes
from temporal_sarafu import load_sarafu, Transfer


def hashes():
    return dict(base_hashes(), **{Path(__file__).name:hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--csv',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--arrival-ticks',type=int,default=2000)
    p.add_argument('--event-budget',type=int,default=10_000_000)
    p.add_argument('--seed',type=int,default=0)
    args=p.parse_args()
    if args.arrival_ticks<=0 or args.event_budget<=0:
        p.error('Positive arrival clock/event budget required')
    fixture=load_sarafu(args.csv,tick_microseconds=1)
    scale=max(1,(fixture.events[-1].time+args.arrival_ticks-1)//args.arrival_ticks)
    events=tuple(Transfer(e.time//scale,e.source,e.target,e.amount,e.row_number) for e in fixture.events)
    config=dict(seed=args.seed,event_budget_per_phase=args.event_budget,arrival_ticks=args.arrival_ticks,
                faults=[[0,False],[.1,True],[.3,True]],algorithms=['random','numbat'])
    frozen=hashes()
    report=dict(complete=False,planned_cases=6,configuration=config,source_sha256=frozen,
                fixture_metadata=fixture.metadata,
                selection=dict(first_standard_transfers=len(events),tick_microseconds=scale,
                               compressed_last_tick=events[-1].time),rows=[],
                note='One seed diagnostic, not universal winner evidence. Equal drop probabilities; activity-dependent random packet draws.')
    output=Path(args.output)
    if output.exists():
        previous=json.loads(output.read_text())
        if (previous['configuration']!=config or previous['source_sha256']!=frozen or
                previous['fixture_metadata']['source_sha256']!=fixture.metadata['source_sha256']):
            raise RuntimeError('Cannot mix sources, fixtures or configurations')
        report=previous
    def save():
        output.parent.mkdir(parents=True,exist_ok=True)
        temp=output.with_suffix(output.suffix+'.tmp')
        temp.write_text(json.dumps(report,indent=2)+'\n');temp.replace(output)
    save()
    for loss,sleep in config['faults']:
        for algorithm in config['algorithms']:
            if any(r['loss']==loss and r['algorithm']==algorithm for r in report['rows']):
                continue
            if hashes()!=frozen:
                raise RuntimeError('Source changed; prior checkpoint preserved')
            row=run_case(events,algorithm=algorithm,seed=args.seed,loss=loss,sleep=sleep,
                         horizon=args.arrival_ticks+300,event_budget=args.event_budget)
            if hashes()!=frozen:
                raise RuntimeError('Source changed during run; prior checkpoint preserved')
            report['rows'].append(row);save()
            print(algorithm,loss,row['complete'],row['elapsed_seconds'],flush=True)
    report['complete']=len(report['rows'])==6 and all(r['complete'] for r in report['rows'])
    save()


if __name__=='__main__':
    main()
