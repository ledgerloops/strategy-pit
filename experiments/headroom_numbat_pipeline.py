"""Node-local Numbat initialization, followed by serialized local Headroom search.

The phase barrier and second phase are globally serialized by the simulator;
this is not a demonstrated concurrent distributed Headroom scheduler.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
from dfs_benchmark import read_graph, replay
from numbat_benchmark import CappedNumbat
from headroom import Headroom
from headroom_benchmark import audit_records, ReductionOnlyNode

ROOT=Path(__file__).parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path)
    p.add_argument('--output',type=Path,default=ROOT/'results/headroom-numbat-pipeline.json')
    p.add_argument('--seeds',type=int,nargs='+',default=[0,1])
    a=p.parse_args();caps=read_graph(a.input.read_text());total=sum(caps.values())
    result=dict(complete=False,expected_runs=len(a.seeds),input_sha256=hashlib.sha256(a.input.read_bytes()).hexdigest(),
      original_debt_scaled=total,scale=1000,seeds=a.seeds,
      numbat_config=dict(capacity_power=4,snapshot_capacity=True,close_first=False,max_delay=5,retry_interval=50,
                         max_hops=100,search_budget=256,message_cutoff=1000000,search_horizon=2000),
      headroom_config=dict(search_budget=64,max_hops=64,rounds=2),
      source_sha256={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in
      ('headroom_numbat_pipeline.py','headroom.py','headroom_benchmark.py','numbat.py','numbat_benchmark.py','distributed.py','dfs_benchmark.py')},runs=[])
    def save():a.output.write_text(json.dumps(result,indent=2)+'\n')
    save()
    for seed in a.seeds:
        started=time.monotonic()
        n=CappedNumbat(caps,seed=seed,max_delay=5,retry_interval=50,max_hops=100,search_budget=256,message_cutoff=1000000)
        n.run(2000,max_events=10000000);n.drain(max_events=10000000)
        initial=replay(caps,n.cycles);assert initial==n.graph_snapshot()
        entry=dict(seed=seed,numbat_cleared_percent=100*(total-sum(initial.values()))/total,numbat_metrics=dict(n.metrics),
                   numbat_replay_ok=True,postpasses={})
        for label in ('headroom','reduction-only-ablation'):
            h=Headroom(caps,initial,seed=seed,search_budget=64,max_hops=64)
            if label=='reduction-only-ablation':
                for node in h.nodes.values():node.__class__=ReductionOnlyNode
            rows=[]
            for r in range(2):
                final=h.run(1);audit=audit_records(caps,initial,h.records,final)
                row=dict(round=r+1,cleared_percent=100*(total-sum(final.values()))/total,
                         headroom_messages=h.metrics['messages'],total_pipeline_messages=n.metrics['messages']+h.metrics['messages'],audit=audit)
                rows.append(row);print(seed,label,r+1,row['cleared_percent'],row['total_pipeline_messages'],flush=True)
            entry['postpasses'][label]=rows
        entry['seconds_with_audits']=time.monotonic()-started;result['runs'].append(entry);save()
    result['complete']=True;save()
if __name__=='__main__':main()
