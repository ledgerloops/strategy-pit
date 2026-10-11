"""Summarize every declared seed-replication case with immutable provenance."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from temporal_episode_gold import verify


def certified_result(report,row,job_state,child,ident,result_path,result_digest,manifest_path,manifest_digest):
    record=child.get('jobs',{}).get(ident,{})
    worker=(job_state.get('status')=='completed' and child.get('status')=='completed' and
            record.get('status')=='completed' and
            record.get('output_sha256',{}).get(str(result_path.resolve()))==result_digest and
            record.get('source_input_sha256',{}).get(str(manifest_path.resolve()))==manifest_digest)
    drained=(row.get('pending_envelopes')==0 and row.get('pending_reservations')==0 and
             row.get('pending_transfers')==0 and not row.get('exposure',{}).get('censored',True))
    return bool(worker and report.get('complete') and row.get('complete') and
                row.get('audit',{}).get('valid') and drained)


def main():
    root=Path(__file__).parent;directory=root/'results'
    snapshots={}
    def load(path):
        if path not in snapshots:
            raw=path.read_bytes();snapshots[path]=(json.loads(raw),hashlib.sha256(raw).hexdigest())
        return snapshots[path]
    gold,_=load(directory/'temporal-episode-fast-gold.json')
    original,_=load(directory/'temporal-episode-full.json')
    certificate=verify(original,gold)
    manifest,manifest_digest=load(root/'research_campaign_episode_replication.json')
    state,state_digest=load(directory/'research-campaign-episode-replication-state.json')
    canonical_manifest=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
    if state['manifest_sha256']!=canonical_manifest:
        raise ValueError('Coordinator state belongs to a different manifest')
    cases=[];rows=[]
    for seed in (1,2):
        for condition,loss,sleep in [('clean',0,False),('loss10',.1,True),('loss30',.3,True)]:
            for algorithm in ('random','numbat'):
                ident=f'seed{seed}-{algorithm}-{condition}'
                path=directory/f'temporal-episode-replication-{ident}.json'
                case=dict(id=ident,seed=seed,algorithm=algorithm,loss=loss,sleep=sleep,complete=False,
                          coordinator_job=state['jobs'].get(ident,{}))
                cases.append(case)
                if not path.exists():
                    case['reason']='No result artifact';continue
                report,digest=load(path)
                case.update(result_file=path.name,result_sha256=digest)
                if report['source_sha256']!=gold['source_sha256']:
                    raise ValueError('Replication source differs from validated fast adapter/driver')
                if (report['fixture_metadata']['source_sha256']!=certificate['fixture_sha256'] or
                        report['selection']!=certificate['selection']):
                    raise ValueError('Replication fixture/selection differs')
                if len(report['rows'])!=1:
                    case['reason']='No completed row checkpoint';continue
                row=deepcopy(report['rows'][0])
                if (row['algorithm'],row['seed'],row['loss'],row['sleep'])!=(algorithm,seed,loss,sleep):
                    raise ValueError('Wrong case in declared artifact')
                reference=gold['rows'][0]
                for key in ('horizon','event_budget_per_phase','arrival_sha256','parameters','transport'):
                    if row[key]!=reference[key]:raise ValueError('Changed fixed benchmark parameter: '+key)
                row['provenance']=dict(result_file=path.name,result_sha256=digest,source_sha256=report['source_sha256'])
                rows.append(row)
                job_state=case['coordinator_job']
                child={}
                if job_state.get('status')=='completed' and job_state.get('state'):
                    child,child_digest=load(Path(job_state['state']))
                    case['child_state_sha256']=child_digest
                case['complete']=certified_result(report,row,job_state,child,ident,path,digest,
                    root/'research_campaign_episode_replication.json',manifest_digest)
                row['provenance']['certified_complete']=case['complete']
                if not case['complete']:
                    case['reason']=row.get('error',report.get('error',
                        'Worker certification pending/failed or audit/drain incomplete'))
    if {j['id'] for j in manifest['jobs']}!={c['id'] for c in cases}:
        raise ValueError('Declared campaign cases differ from intended replication')
    pairs=[]
    certified={(c['seed'],c['loss'],c['sleep'],c['algorithm']) for c in cases if c['complete']}
    by_key={(r['seed'],r['loss'],r['sleep'],r['algorithm']):r for r in rows
            if (r['seed'],r['loss'],r['sleep'],r['algorithm']) in certified}
    for seed in (1,2):
        for loss,sleep in ((0,False),(.1,True),(.3,True)):
            if not all((seed,loss,sleep,a) in by_key for a in ('random','numbat')):continue
            a,b=(by_key[seed,loss,sleep,name] for name in ('random','numbat'))
            pair=dict(seed=seed,loss=loss,sleep=sleep,
                random_final_improvement_percent=100*(1-a['audit']['final_debt_scaled']/a['no_clearing_final_debt_scaled']),
                numbat_final_improvement_percent=100*(1-b['audit']['final_debt_scaled']/b['no_clearing_final_debt_scaled']),
                final_debt_winner='random' if a['audit']['final_debt_scaled']<b['audit']['final_debt_scaled'] else
                                  'numbat' if b['audit']['final_debt_scaled']<a['audit']['final_debt_scaled'] else 'tie')
            pairs.append(pair)
    report=dict(complete=state['complete'] and all(c['complete'] for c in cases),planned_cases=12,cases=cases,rows=rows,pairs=pairs,
        coordinator_status=state['status'],coordinator_state_sha256=state_digest,manifest_sha256=manifest_digest,
        gate=certificate,summary_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        checker_source_sha256=hashlib.sha256((root/'temporal_episode_gold.py').read_bytes()).hexdigest(),
        note='Fixed seed1/2 robustness replication; unchanged policies, same real fixture. Incomplete cases retained; no universal ranking.')
    path=directory/'temporal-episode-replication-summary.json';tmp=path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(path)
    print('Complete:',report['complete'],'cases:',sum(c['complete'] for c in cases),'/12',flush=True)


if __name__=='__main__':main()
