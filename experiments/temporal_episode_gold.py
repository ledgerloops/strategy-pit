"""Verify fast full-case equivalence against an original saved case."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path


REQUIRED_BASE=('distributed.py','numbat.py','temporal_protocol.py','temporal_episodes.py',
               'temporal_benchmark.py','temporal_sarafu.py','temporal_metrics.py',
               'temporal_episode_benchmark.py')

def canonical(row):
    row=deepcopy(row)
    row.pop('elapsed_seconds',None)
    return row


def verify(legacy,fast):
    if not fast.get('complete') or len(fast.get('rows',[]))!=1:
        raise ValueError('Fast reference must contain exactly one completed case')
    candidate=fast['rows'][0]
    key=lambda r:tuple(r[k] for k in ('algorithm','seed','loss','sleep','horizon'))
    references=[r for r in legacy['rows'] if key(r)==key(candidate)]
    if len(references)!=1 or not references[0].get('complete'):
        raise ValueError('Need exactly one completed matching original case')
    if legacy['fixture_metadata']['source_sha256']!=fast['fixture_metadata']['source_sha256']:
        raise ValueError('Fixture hash differs')
    if legacy['selection']!=fast['selection']:
        raise ValueError('Input selection differs')
    if any(p not in report['source_sha256'] for report in (legacy,fast) for p in REQUIRED_BASE):
        raise ValueError('Required base source pin missing')
    common=set(legacy['source_sha256'])&set(fast['source_sha256'])
    if not common or any(legacy['source_sha256'][p]!=fast['source_sha256'][p] for p in common):
        raise ValueError('Common protocol source hash differs')
    left,right=canonical(references[0]),canonical(candidate)
    if left!=right:
        differences=sorted(k for k in left.keys()|right.keys() if left.get(k)!=right.get(k))
        raise ValueError('Non-timing row differs: '+', '.join(differences))
    fingerprint=hashlib.sha256(json.dumps(left,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return dict(complete=True,equivalent=True,algorithm=candidate['algorithm'],seed=candidate['seed'],
        loss=candidate['loss'],sleep=candidate['sleep'],non_timing_row_sha256=fingerprint,
        fixture_sha256=fast['fixture_metadata']['source_sha256'],selection=fast['selection'],
        common_source_sha256={p:legacy['source_sha256'][p] for p in sorted(common)},
        excluded_fields=['elapsed_seconds'],
        limitation='Saved full rows lack complete event traces and RNG states; smaller independent trace/RNG tests provide complementary coverage.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--legacy',required=True);p.add_argument('--fast',required=True);p.add_argument('--output',required=True)
    args=p.parse_args()
    original=json.loads(Path(args.legacy).read_text());fast=json.loads(Path(args.fast).read_text())
    report=verify(original,fast)
    report.update(legacy_file=args.legacy,fast_file=args.fast,
        legacy_source_sha256=original['source_sha256'],fast_source_sha256=fast['source_sha256'],
        checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    temp=output.with_suffix(output.suffix+'.tmp');temp.write_text(json.dumps(report,indent=2)+'\n');temp.replace(output)
    print('Exact non-timing full row equivalence verified',flush=True)


if __name__=='__main__':
    main()
