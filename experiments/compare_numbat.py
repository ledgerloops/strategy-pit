"""Fixed Numbat on an explicitly supplied static debt graph; no parameter tuning.

Message checkpoints count completed cycles only. In-flight work is drained before
ledger/conservation validation; checkpoints are not snapshots of atomic balances.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time
from dfs_benchmark import read_graph, replay, describe, clear_dfs, mcf_reference
from numbat_benchmark import CappedNumbat

class ObservedNumbat(CappedNumbat):
    def __init__(self,*args,**kwargs):
        self.checkpoints=[]
        super().__init__(*args,**kwargs)
    def send(self,*args,**kwargs):
        super().send(*args,**kwargs)
        if self.metrics['messages'] in (100000,250000,500000,1000000,2000000):
            self.checkpoints.append(dict(messages=self.metrics['messages'],tick=self.time,
                completed_cleared_scaled=self.metrics['cleared'],completed_cycles=self.metrics['cycles']))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('debt',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seeds',type=int,nargs='+',default=[0,1,2]);p.add_argument('--cutoff',type=int,default=1000000)
    p.add_argument('--horizon',type=int,default=2000);a=p.parse_args()
    graph=read_graph(a.debt.read_text());root=Path(__file__).parent
    config=dict(max_delay=5,retry_interval=50,max_hops=100,search_budget=256,message_cutoff=a.cutoff)
    out=dict(complete=False,input_sha256=hashlib.sha256(a.debt.read_bytes()).hexdigest(),
             input_edges=len(graph),input_nodes=len({n for edge in graph for n in edge}),
             input_total_scaled=sum(graph.values()),scale=1000,python_version=platform.python_version(),
             numbat_config=dict(capacity_power=4,snapshot_capacity=True,close_first=False),
             scheduler_config=config,search_horizon=a.horizon,seeds=a.seeds,
             source_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
                ('compare_numbat.py','numbat.py','distributed.py','numbat_benchmark.py','dfs_benchmark.py')},
             references={},runs=[])
    def save():
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n')
    save()
    for label,cycles in [('dfs',clear_dfs(graph)),('largest_dfs',clear_dfs(graph,policy='largest')),('mcf',mcf_reference(graph))]:
        out['references'][label]=describe(graph,cycles)
    save()
    for seed in a.seeds:
        start=time.monotonic();s=ObservedNumbat(graph,seed=seed,**config)
        s.run(a.horizon,max_events=10000000);s.drain(max_events=10000000)
        expected=replay(graph,s.cycles);assert expected==s.graph_snapshot()
        r=describe(graph,s.cycles);r.update(seed=seed,protocol=dict(s.metrics),checkpoints=s.checkpoints,
             drain_tick=s.time,cutoff_tick=s.cutoff_tick,elapsed_seconds=time.monotonic()-start,
             replay_ok=True,pending_events=len(s.events),pending_reservations=s.pending_reservations)
        out['runs'].append(r);save();print(seed,r['cleared_percent'],s.metrics['messages'],flush=True)
    out['complete']=True;save()
if __name__=='__main__':main()
