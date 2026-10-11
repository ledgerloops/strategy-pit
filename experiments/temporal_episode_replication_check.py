"""Small seed-0 equivalence gate before unchanged-policy seed replication."""
import hashlib
import json
from pathlib import Path
import temporal_episode_benchmark as benchmark
from temporal_benchmark import synthetic
from temporal_episodes import EpisodeTemporalProtocol
from fast_temporal_transport import FastEpisodeTemporalProtocol
from temporal_episode_fast_case import hashes
from temporal_episode_gold import canonical


def main():
    source=hashes()
    for name in ('temporal_episode_replication_check.py','temporal_episode_gold.py'):
        source[name]=hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
    events=synthetic('community',24,0)
    rows=[]
    for algorithm in ('random','numbat'):
        for loss,sleep in ((0,False),(.1,True),(.3,True)):
            kwargs=dict(algorithm=algorithm,seed=0,loss=loss,sleep=sleep,horizon=800,event_budget=100000)
            benchmark.EpisodeTemporalProtocol=EpisodeTemporalProtocol
            original=benchmark.run_case(events,**kwargs)
            benchmark.EpisodeTemporalProtocol=FastEpisodeTemporalProtocol
            fast=benchmark.run_case(events,**kwargs)
            if not original['complete'] or not fast['complete'] or canonical(original)!=canonical(fast):
                raise RuntimeError('Seed-0 equivalence gate failed')
            rows.append(dict(algorithm=algorithm,loss=loss,sleep=sleep,equivalent=True,
                non_timing_row_sha256=hashlib.sha256(json.dumps(canonical(original),sort_keys=True).encode()).hexdigest(),
                cycles=original['audit']['cycles'],arrival_sha256=original['arrival_sha256']))
    report=dict(complete=True,source_sha256=source,rows=rows,
        fixture='24-node community synthetic, seed0, continuous arrivals; no policy retuning')
    path=Path(__file__).parent/'results'/'temporal-episode-replication-gate.json'
    tmp=path.with_suffix('.json.tmp');tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(path)
    print('Six seed0 cases exactly match all non-timing fields',flush=True)


if __name__=='__main__':main()
