from copy import deepcopy
import unittest
from distributed import Token
from temporal_episodes import EpisodeTemporalProtocol
from concurrent_headroom import ConcurrentHeadroom,Search
from fast_temporal_transport import FastEpisodeTemporalProtocol,FastConcurrentHeadroom
from temporal_benchmark import synthetic,sleeps_for


def traced(base):
    class Trace(base):
        def __init__(self,*args,**kwargs):
            self.schedule_trace=[]
            super().__init__(*args,**kwargs)
        def schedule(self,at,dest,kind,payload):
            self.schedule_trace.append((at,dest,kind,repr(payload)))
            super().schedule(at,dest,kind,payload)
    return Trace


def fingerprint(sim):
    return dict(metrics=dict(sim.metrics),ledger=sim.ledger_records,cycles=sim.cycle_records,
        messages=sim.message_log,snapshot=sim.graph_snapshot(),random_state=sim.random.getstate(),
        nodes={name:{k:deepcopy(v) for k,v in vars(node).items() if k!='sim'} for name,node in sim.nodes.items()},
        time=sim.time,serial=sim.serial,seen=sim.seen,pending=sim.pending,events=sim.events)


class FastTests(unittest.TestCase):
    def test_exact_trace_equivalence(self):
        for name,base,fast in [('random',EpisodeTemporalProtocol,FastEpisodeTemporalProtocol),
                               ('numbat',EpisodeTemporalProtocol,FastEpisodeTemporalProtocol),
                               ('headroom',ConcurrentHeadroom,FastConcurrentHeadroom)]:
            for seed in (11,12):
                for transport in ('concurrent','stop_wait'):
                    sims=[]
                    events=synthetic('bursts',12,seed,duration=200)
                    for cls in (base,fast):
                        sim=traced(cls)(seed=seed,algorithm='numbat' if name=='headroom' else name,
                            loss=.3,ack_loss=.4,transport=transport,retry_interval=25,max_hops=16,search_budget=64)
                        for node,start,duration in sleeps_for(events,seed,True,400):sim.add_sleep(node,start,duration)
                        for e in events:sim.add_transfer(e.source,e.target,e.amount,at=e.time)
                        sim.run(400);sim.drain()
                        sims.append(sim)
                    self.assertEqual(sims[0].schedule_trace,sims[1].schedule_trace,(name,seed,transport))
                    self.assertEqual(fingerprint(sims[0]),fingerprint(sims[1]),(name,seed,transport))

    def test_sender_and_receiver_do_not_alias_envelope(self):
        for cls,token_cls,kind in [(FastEpisodeTemporalProtocol,Token,'step'),(FastConcurrentHeadroom,Search,'hstep')]:
            sim=cls(loss=1)
            sim.stop_searches();sim.add_transfer('a','b',5);sim.drain()
            token=token_cls(('a',99),['a','b'],{'a','b'})
            sim.send('a','b',kind,token)
            ident=sim.envelope_sequence
            before=deepcopy(sim.pending[ident].payload)
            token.path.append('sender-mutated');token.visited.add('sender-mutated')
            self.assertEqual(sim.pending[ident].payload,before)
            sim._attempt(ident)
            size=len(repr(before).encode())
            sim.loss=0
            received=[]
            def mutate(kind,payload):
                payload.payload.path.append('receiver-mutated')
                received.append(payload)
            sim.nodes['b'].receive=mutate
            sim._delivery(ident)
            self.assertEqual(sim.pending[ident].payload,before)
            sim._attempt(ident)
            self.assertEqual(sim.metrics['payload_repr_bytes'],2*size)
            self.assertTrue(received)

if __name__=='__main__':unittest.main()
