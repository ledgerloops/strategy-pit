"""Simulator runtime experiment; exact protocol equality, no algorithm ranking."""
from pathlib import Path
import hashlib,json,statistics,time
from fast_temporal_transport import FastEpisodeTemporalProtocol,FastConcurrentHeadroom
from temporal_episodes import EpisodeTemporalProtocol
from concurrent_headroom import ConcurrentHeadroom
from temporal_benchmark import synthetic,sleeps_for
from test_fast_temporal_transport import fingerprint

ROOT=Path(__file__).resolve().parent
FILES=['fast_temporal_transport.py','temporal_episodes.py','concurrent_headroom.py','temporal_protocol.py','distributed.py','numbat.py','temporal_benchmark.py','temporal_sarafu.py','test_fast_temporal_transport.py','fast_transport_benchmark.py']
def hashes():return {f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in FILES}

def run(cls,algorithm,events,seed,loss,sleep):
    sim=cls(seed=seed,algorithm=algorithm,loss=loss,ack_loss=loss,retry_interval=50,max_hops=32,search_budget=96)
    for node,start,duration in sleeps_for(events,seed,sleep,800):sim.add_sleep(node,start,duration)
    for e in events:sim.add_transfer(e.source,e.target,e.amount,at=e.time)
    start=time.perf_counter();sim.run(800);sim.drain();elapsed=time.perf_counter()-start
    return sim,elapsed

def main():
    source=hashes()
    report=dict(complete=False,source_sha256=source,rows=[],note='Sequential alternating runtime samples on shared worker; wall-clock speed only, no protocol or message reduction. Timings exclude setup and equality assertions.')
    output=ROOT/'results/fast-transport-runtime.json'
    def save():
        tmp=output.with_suffix('.tmp');tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(output)
    for nodes in (24,72):
        for loss,sleep,seed in ((0.,False,31),(.3,True,32)):
            events=synthetic('bursts',nodes,seed)
            for method,base,fast in [('random',EpisodeTemporalProtocol,FastEpisodeTemporalProtocol),('numbat',EpisodeTemporalProtocol,FastEpisodeTemporalProtocol),('headroom',ConcurrentHeadroom,FastConcurrentHeadroom)]:
                times={'original':[],'fast':[]};reference=None
                for repetition in range(3):
                    variants=[('original',base),('fast',fast)]
                    if repetition%2:variants.reverse()
                    for name,cls in variants:
                        assert hashes()==source
                        sim,elapsed=run(cls,'numbat' if method=='headroom' else method,events,seed,loss,sleep)
                        result=fingerprint(sim)
                        if reference is None:reference=result
                        assert result==reference,(nodes,loss,method,repetition,name)
                        times[name].append(elapsed)
                row=dict(nodes=nodes,loss=loss,sleep=sleep,seed=seed,method=method,equal=True,samples_seconds=times,
                    median_seconds={k:statistics.median(v) for k,v in times.items()},metrics=reference['metrics'])
                row['speedup']=row['median_seconds']['original']/row['median_seconds']['fast']
                report['rows'].append(row);save()
    report['complete']=True;save()
    print(json.dumps(dict(rows=len(report['rows']),complete=True)))

if __name__=='__main__':main()
