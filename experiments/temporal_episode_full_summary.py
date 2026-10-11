"""Join two original clean controls and four validated fast fault cases."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from temporal_episode_gold import verify


def verify_fast_sources(gold, report):
    if report['source_sha256'] != gold['source_sha256']:
        raise ValueError('Fast source pins differ from validated gold adapter/driver')

def main():
    root=Path(__file__).parent
    directory=root/'results'
    original_path=directory/'temporal-episode-full.json'
    cache={}
    def load(path):
        if path not in cache:
            raw=path.read_bytes()
            cache[path]=(json.loads(raw),hashlib.sha256(raw).hexdigest())
        return cache[path]
    original,_=load(original_path)
    gold,_=load(directory/'temporal-episode-fast-gold.json')
    equivalence=verify(original,gold)
    rows=[]
    common_input=None
    for algorithm,loss,sleep in [('random',0,False),('numbat',0,False),
                                 ('random',.1,True),('numbat',.1,True),
                                 ('random',.3,True),('numbat',.3,True)]:
        path=(original_path if not loss else
              directory/f'temporal-episode-fast-{algorithm}-loss{round(loss*100)}.json')
        report,result_digest=load(path)
        if loss:
            verify_fast_sources(gold,report)
        if loss and not report['complete']:
            raise ValueError(f'Incomplete fault result: {path}')
        matches=[r for r in report['rows'] if (r['algorithm'],r['loss'],r['sleep'],r['seed'])==(algorithm,loss,sleep,0)]
        if len(matches)!=1 or not matches[0]['complete']:
            raise ValueError(f'Need one completed intended case: {path}')
        row=deepcopy(matches[0])
        inputs=(report['fixture_metadata']['source_sha256'],report['selection'],row['arrival_sha256'],
                row['horizon'],row['event_budget_per_phase'],row['parameters'])
        if common_input is None:
            common_input=inputs
        elif inputs!=common_input:
            raise ValueError('Cases have different input, horizon or search configuration')
        if any(report['source_sha256'].get(p)!=value for p,value in equivalence['common_source_sha256'].items()):
            raise ValueError('Common frozen protocol source differs')
        row['provenance']=dict(adapter='original' if not loss else 'fast',result_file=path.name,
            result_sha256=result_digest,source_sha256=report['source_sha256'])
        rows.append(row)
    output=dict(complete=True,planned_cases=6,rows=rows,
        fixture_metadata=original['fixture_metadata'],selection=original['selection'],
        fast_clean_equivalence=equivalence,
        summary_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        gold_checker_sha256=hashlib.sha256((root/'temporal_episode_gold.py').read_bytes()).hexdigest(),
        note='Two original clean controls, four fast fault cases. Transport adapters passed exact full clean non-timing row equivalence and smaller trace tests. Distinct source provenance retained. Single seed; no universal winner or concurrent throughput claim.')
    path=directory/'temporal-episode-full-comparison.json'
    tmp=path.with_suffix('.json.tmp');tmp.write_text(json.dumps(output,indent=2)+'\n');tmp.replace(path)
    print('Six completed independently audited cases joined with explicit provenance',flush=True)


if __name__=='__main__':
    main()
