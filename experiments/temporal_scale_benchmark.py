"""Bounded, resumable larger Sarafu timestamp replay; no protocol changes."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from temporal_benchmark import hashes, run_case
from temporal_sarafu import load_sarafu, Transfer


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--csv',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--arrival-ticks',type=int,default=2000)
    p.add_argument('--event-budget',type=int,default=10_000_000)
    p.add_argument('--seed',type=int,default=0)
    p.add_argument('--limit',type=int,default=0)
    args=p.parse_args()
    if args.arrival_ticks<=0 or args.event_budget<=0 or args.limit<0:
        p.error('Invalid nonpositive clock/budget or negative limit')
    fixture=load_sarafu(args.csv,tick_microseconds=1)
    selected=fixture.events[:args.limit] if args.limit else fixture.events
    scale=max(1,(selected[-1].time+args.arrival_ticks-1)//args.arrival_ticks)
    events=tuple(Transfer(e.time//scale,e.source,e.target,e.amount,e.row_number) for e in selected)
    source=hashes()
    source['temporal_scale_benchmark.py']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    config=dict(seed=args.seed,event_budget=args.event_budget,arrival_ticks=args.arrival_ticks,
                limit=args.limit,source_sha256=fixture.metadata['source_sha256'])
    output=Path(args.output)
    report=dict(complete=False,configuration=config,source_sha256=source,
                fixture_metadata=fixture.metadata,
                selection=dict(first_standard_transfers=len(events),tick_microseconds=scale,
                               original_elapsed_microseconds=selected[-1].time,compressed_last_tick=events[-1].time),rows=[])
    if output.exists():
        previous=json.loads(output.read_text())
        if previous['configuration']!=config or previous['source_sha256']!=source:
            raise RuntimeError('Refusing to mix versions/configurations; choose a new output')
        report=previous
    def checkpoint():
        output.parent.mkdir(parents=True,exist_ok=True)
        temporary=output.with_suffix('.tmp')
        temporary.write_text(json.dumps(report,indent=2)+'\n')
        temporary.replace(output)
    checkpoint()
    for algorithm in ['numbat','random','largest']:
        if any(row['algorithm']==algorithm for row in report['rows']):
            continue
        if any(hashes().get(k)!=v for k,v in source.items() if k!='temporal_scale_benchmark.py'):
            raise RuntimeError('Source changed; prior checkpoints preserved')
        result=run_case(events,algorithm=algorithm,seed=args.seed,loss=0,sleep=False,
                        transport='concurrent',horizon=args.arrival_ticks+300,event_budget=args.event_budget)
        report['rows'].append(result)
        checkpoint()
        print(algorithm,'complete',result['complete'],'time',result['final_time'],'events',result['metrics']['events'],flush=True)
    report['complete']=len(report['rows'])==3 and all(row['complete'] for row in report['rows'])
    checkpoint()


if __name__=='__main__':
    main()
