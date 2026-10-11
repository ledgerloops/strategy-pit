"""Single immutable fast-adapter case; separate output and frozen source pins."""
import argparse
import hashlib
import json
from pathlib import Path
import temporal_episode_benchmark as benchmark
from fast_temporal_transport import FastEpisodeTemporalProtocol
from temporal_sarafu import load_sarafu, Transfer

SOURCES=(*benchmark.SOURCES,'concurrent_headroom.py','fast_temporal_transport.py','temporal_episode_fast_case.py')


def hashes():
    root=Path(__file__).parent
    return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in SOURCES}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--csv',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--algorithm',choices=['random','numbat'],required=True)
    p.add_argument('--loss',type=float,required=True)
    p.add_argument('--sleep',action='store_true')
    p.add_argument('--seed',type=int,default=0)
    p.add_argument('--arrival-ticks',type=int,default=2000)
    p.add_argument('--event-budget',type=int,default=10_000_000)
    p.add_argument('--limit',type=int,default=0)
    args=p.parse_args()
    if not 0<=args.loss<=1 or args.arrival_ticks<=0 or args.event_budget<=0 or args.limit<0:
        p.error('Invalid case parameters')
    fixture=load_sarafu(args.csv,tick_microseconds=1)
    selected=fixture.events[:args.limit] if args.limit else fixture.events
    scale=max(1,(selected[-1].time+args.arrival_ticks-1)//args.arrival_ticks)
    events=tuple(Transfer(e.time//scale,e.source,e.target,e.amount,e.row_number) for e in selected)
    config=vars(args).copy();config.pop('output');config.pop('csv')
    frozen=hashes();output=Path(args.output)
    report=dict(complete=False,planned_cases=1,configuration=config,source_sha256=frozen,
        fixture_metadata=fixture.metadata,selection=dict(first_standard_transfers=len(events),tick_microseconds=scale,compressed_last_tick=events[-1].time),
        note='Fast transport adapter; semantic equivalence must be checked separately. Concurrent wall times are not throughput comparisons.',rows=[])
    if output.exists():
        previous=json.loads(output.read_text())
        if (previous['configuration']!=config or previous['source_sha256']!=frozen or
            previous['fixture_metadata']['source_sha256']!=fixture.metadata['source_sha256']):
            raise RuntimeError('Cannot mix source, fixture or configuration')
        if previous['complete']:
            return
        raise RuntimeError('Existing incomplete output; preserve it and choose a new output')
    def save():
        output.parent.mkdir(parents=True,exist_ok=True)
        tmp=output.with_suffix(output.suffix+'.tmp');tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(output)
    save()
    # Process-local injection changes no file or running worker. run_case still
    # uses the exact same observer, audit, event/sleep generator and budgets.
    benchmark.EpisodeTemporalProtocol=FastEpisodeTemporalProtocol
    row=benchmark.run_case(events,algorithm=args.algorithm,seed=args.seed,loss=args.loss,
        sleep=args.sleep,horizon=args.arrival_ticks+300,event_budget=args.event_budget)
    report['rows'].append(row)
    if hashes()!=frozen:
        report['error']='Source changed during run; result not certified'
    else:
        report['complete']=row['complete']
    save()
    print(args.algorithm,args.loss,args.sleep,report['complete'],row['elapsed_seconds'],flush=True)


if __name__=='__main__':
    main()
