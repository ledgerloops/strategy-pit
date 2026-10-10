"""Reproducible changing-graph benchmarks with independent per-edge audit.

All graph-wide inspection here is external measurement, never protocol routing.
Run --suite smoke first; synthetic compares shared arrivals and sleep schedules.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
import time
from temporal_protocol import TemporalProtocol
from temporal_sarafu import Transfer, load_sarafu, net_graph

ROOT = Path(__file__).parent


def hashes():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
            for p in ('distributed.py', 'numbat.py', 'temporal_protocol.py',
                      'temporal_sarafu.py', 'temporal_benchmark.py')}


def net_positions(graph):
    values = Counter()
    for (a,b), amount in graph.items():
        values[a] -= amount
        values[b] += amount
    return {a:v for a,v in values.items() if v}


def audit(sim, arrivals, horizon):
    """Replay actual transfers and individual commits, including staged commits.

    Completion-time atomic cycle replay would be incorrect when a new transfer
    posts on an already committed edge before another edge finishes committing.
    """
    graph, commits = {}, defaultdict(list)
    current_debt = area = previous = 0
    transfers, netted, cleared = [], 0, 0
    for expected_order, record in enumerate(sim.ledger_records):
        at, kind = record['time'], record['kind']
        if record['order'] != expected_order or at < previous:
            raise AssertionError('Ledger records not in event order')
        if previous < horizon:
            area += current_debt * (min(at,horizon) - previous)
        previous = at
        a,b,delta = record['source'],record['target'],record['delta']
        if a == b or not isinstance(delta,int):
            raise AssertionError('Invalid ledger entry')
        if kind == 'transfer':
            if delta <= 0:
                raise AssertionError('Invalid transfer')
            old = graph.pop((a,b),0)-graph.pop((b,a),0)
            new = old+delta
            netted += abs(old)+delta-abs(new)
            current_debt += abs(new)-abs(old)
            if new > 0:
                graph[a,b] = new
            elif new < 0:
                graph[b,a] = -new
            transfers.append((at,a,b,delta))
        elif kind == 'commit':
            if delta >= 0 or graph.get((a,b),0) < -delta:
                raise AssertionError('Commit exceeds available debt')
            graph[a,b] += delta
            if not graph[a,b]:
                del graph[a,b]
            current_debt += delta
            cleared -= delta
            commits[tuple(record['txid'])].append((a,b,-delta))
        else:
            raise AssertionError('Unknown ledger event')
    if previous < horizon:
        area += current_debt*(horizon-previous)
    if graph != sim.graph_snapshot():
        raise AssertionError('Independent ledger differs from simulator')
    expected_arrivals = Counter((e.source,e.target,e.amount) for e in arrivals)
    if Counter((a,b,v) for _,a,b,v in transfers) != expected_arrivals:
        raise AssertionError('Dropped or duplicated external transfer')
    # Pair-specific FIFO preserves external arrival order despite posting delays.
    queues = defaultdict(list)
    for e in arrivals:
        queues[frozenset((e.source,e.target))].append(e)
    offsets = Counter()
    for at,a,b,v in transfers:
        pair = frozenset((a,b))
        e = queues[pair][offsets[pair]]
        offsets[pair] += 1
        if (a,b,v) != (e.source,e.target,e.amount) or at < e.time:
            raise AssertionError('Transfer reordered or posted before arrival')
    observed = Counter()
    for edges in commits.values():
        amounts = {v for _,_,v in edges}
        out = {a:b for a,b,_ in edges}
        if len(amounts) != 1 or len(out) != len(edges) or len(edges)<3:
            raise AssertionError('Incomplete or inconsistent settlement')
        start = edges[0][0]
        cursor, visited = start, set()
        while cursor not in visited:
            visited.add(cursor)
            if cursor not in out:
                raise AssertionError('Settlement is not a cycle')
            cursor = out[cursor]
        if cursor != start or len(visited) != len(edges):
            raise AssertionError('Settlement contains disconnected cycles')
        observed[frozenset((a,b) for a,b,_ in edges),next(iter(amounts))] += 1
    declared = Counter()
    for record in sim.cycle_records:
        nodes = record['nodes']
        declared[frozenset(zip(nodes,nodes[1:]+nodes[:1])),record['amount']] += 1
    if observed != declared:
        raise AssertionError('Completion records differ from edge commits')
    if net_positions(graph) != net_positions(net_graph(arrivals)):
        raise AssertionError('Net positions changed')
    if netted != sim.metrics['bilateral_netting'] or cleared != sim.metrics['cleared']:
        raise AssertionError('Reported accounting differs from replay')
    return dict(valid=True, ledger_entries=len(sim.ledger_records), cycles=len(commits),
                debt_amount_ticks_to_horizon=area, final_debt_scaled=current_debt,
                bilateral_netting_scaled=netted, cycle_clearing_scaled=cleared,
                all_transfers_applied=True, net_positions_preserved=True,
                every_commit_capacity_checked=True)


def synthetic(kind, nodes, seed, duration=500):
    rng = random.Random(seed+nodes*1009)
    events=[]
    # Continuing reciprocal transfers permit closure, reversal and reopening.
    for i in range(nodes*8):
        a = rng.randrange(nodes)
        if kind == 'community' and rng.random()<.9:
            group = (a//(nodes//3))*(nodes//3)
            choices = [n for n in range(group,group+nodes//3) if n != a]
            b = rng.choice(choices)
        elif kind == 'sparse':
            b = (a+rng.choice((1,2,nodes-1)))%nodes
        else:
            b = rng.choice([n for n in range(nodes) if n != a])
        at = rng.randrange(duration+1)
        if kind == 'bursts':
            at = (at//100)*100+rng.randrange(8)
        events.append(Transfer(at,a,b,rng.randint(1,30)*1000,i))
    return tuple(sorted(events,key=lambda e:(e.time,e.row_number)))


def sleeps_for(events, seed, enabled, horizon):
    if not enabled:
        return []
    rng=random.Random(seed+77771)
    nodes=sorted({p for e in events for p in (e.source,e.target)})
    result=[]
    for node in nodes:
        if rng.random()<.6:
            for _ in range(2):
                result.append((node,rng.randrange(max(1,horizon-100)),rng.randint(20,100)))
    return result


def run_case(events, *, algorithm, seed, loss, sleep, transport, horizon, event_budget=2_000_000):
    sim=TemporalProtocol(algorithm=algorithm,seed=seed,loss=loss,
                         transport=transport,retransmit=20,max_delay=5,
                         retry_interval=50,max_hops=32,search_budget=96)
    for node,start,duration in sleeps_for(events,seed,sleep,horizon):
        sim.add_sleep(node,start,duration)
    for event in events:
        if event.amount and event.source != event.target:
            sim.add_transfer(event.source,event.target,event.amount,at=event.time)
    start=time.monotonic()
    result=dict(algorithm=algorithm,seed=seed,loss=loss,ack_loss=loss,sleep=sleep,
                transport=transport,horizon=horizon,arrivals=len(events),
                arrival_sha256=hashlib.sha256(json.dumps([asdict(e) for e in events],sort_keys=True).encode()).hexdigest(),
                parameters=dict(retransmit=20,max_delay=5,retry_interval=50,max_hops=32,search_budget=96),
                no_clearing_final_debt_scaled=sum(net_graph(events).values()))
    try:
        sim.run(horizon,max_events=event_budget)
        result['at_horizon']=dict(time=sim.time,pending_envelopes=len(sim.pending),
                                  pending_reservations=sim.pending_reservations,
                                  pending_transfers=sum(map(len,sim.transfer_queues.values())),
                                  posted_transfers=len(sim.transfer_records),
                                  debt_scaled=sum(sim.graph_snapshot().values()),
                                  metrics=dict(sim.metrics))
        sim.drain(max_events=event_budget)
        result['audit']=audit(sim,events,horizon)
        result['complete']=True
    except (RuntimeError,AssertionError) as error:
        result['complete']=False
        result['error']=f'{type(error).__name__}: {error}'
    result.update(final_time=sim.time,metrics=dict(sim.metrics),
                  pending_envelopes=len(sim.pending),pending_reservations=sim.pending_reservations,
                  pending_transfers=sum(map(len,sim.transfer_queues.values())),
                  elapsed_seconds=time.monotonic()-start)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite',choices=['smoke','synthetic','sarafu'],default='smoke')
    parser.add_argument('--csv')
    parser.add_argument('--limit',type=int,default=1000,help='First N chronological STANDARD transfers; 0 means all')
    parser.add_argument('--arrival-ticks',type=int,default=500)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    source_hashes=hashes()
    report=dict(suite=args.suite,source_sha256=source_hashes,complete=False,rows=[],
                transport_note='stop_wait is a shared scheduler reference, not historical turn negotiation',
                fault_note='Same seeded arrival/sleep schedules; data+ACK loss probabilities equal. Random draw streams depend on algorithm activity.',
                audit_note='Independent individual edge replay; debt area uses posted transfers and staged commits, not requested arrivals.')
    cases=[]
    if args.suite in ('smoke','synthetic'):
        nodes_values=[12] if args.suite=='smoke' else [12,24]
        kinds=['sparse'] if args.suite=='smoke' else ['sparse','community','bursts']
        seeds=[0] if args.suite=='smoke' else [0,1]
        for nodes in nodes_values:
            for kind in kinds:
                for seed in seeds:
                    events=synthetic(kind,nodes,seed)
                    for loss in ([0,.3] if args.suite=='smoke' else [0,.1,.3]):
                        for sleep in [False,True]:
                            for transport in ['concurrent','stop_wait']:
                                for algorithm in ['numbat','random','largest']:
                                    cases.append((dict(kind=kind,nodes=nodes),events,dict(algorithm=algorithm,seed=seed,loss=loss,sleep=sleep,transport=transport,horizon=800)))
    else:
        if not args.csv:
            parser.error('--csv required for sarafu')
        if args.arrival_ticks<=0 or args.limit<0:
            parser.error('arrival-ticks must be positive and limit nonnegative')
        precise=load_sarafu(args.csv,tick_microseconds=1)
        selected=precise.events[:args.limit] if args.limit else precise.events
        scale=max(1,(selected[-1].time+args.arrival_ticks-1)//args.arrival_ticks)
        events=tuple(Transfer(e.time//scale,e.source,e.target,e.amount,e.row_number) for e in selected)
        report['fixture_metadata']=precise.metadata
        report['selection']=dict(first_standard_transfers=len(events),tick_microseconds=scale,
                                 original_elapsed_microseconds=selected[-1].time,compressed_last_tick=events[-1].time,
                                 note='Actual timestamp gaps uniformly compressed; this is accelerated replay, not real-time throughput.')
        for seed in [0,1]:
            for loss,sleep in [(0,False),(.1,True),(.3,True)]:
                for algorithm in ['numbat','random','largest']:
                    cases.append((dict(kind='sarafu-prefix',nodes=len({p for e in events for p in (e.source,e.target)})),events,
                                  dict(algorithm=algorithm,seed=seed,loss=loss,sleep=sleep,transport='concurrent',horizon=args.arrival_ticks+300)))
    report['planned_cases']=len(cases)
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    def checkpoint():
        tmp=output.with_suffix(output.suffix+'.tmp')
        tmp.write_text(json.dumps(report,indent=2)+'\n')
        tmp.replace(output)
    checkpoint()
    for label,events,kwargs in cases:
        if hashes()!=source_hashes:
            report['interrupted_reason']='Source changed during benchmark; checkpoint preserved'
            checkpoint()
            raise RuntimeError(report['interrupted_reason'])
        result=run_case(events,**kwargs)
        result.update(label)
        report['rows'].append(result)
        checkpoint()
        print(f"{len(report['rows'])}/{len(cases)} {label['kind']} {kwargs['algorithm']} loss={kwargs['loss']} sleep={kwargs['sleep']} {kwargs['transport']} complete={result['complete']}",flush=True)
    report['complete']=len(report['rows'])==len(cases) and all(r['complete'] for r in report['rows'])
    checkpoint()


if __name__=='__main__':
    main()
