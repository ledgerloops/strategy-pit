import unittest
from temporal_priority import PriorityOutbox, PriorityTurnTemporalProtocol
from temporal_benchmark import audit, synthetic, sleeps_for


class PriorityTests(unittest.TestCase):
    def test_priority_and_bounded_exploration_wait(self):
        queue = PriorityOutbox(2)
        queue.append(('step',1))
        queue.append(('step',2))
        for i in range(5):
            queue.append(('commit',i))
        self.assertEqual([queue.popleft()[0] for _ in range(7)],
                         ['commit','commit','step','commit','commit','step','commit'])

    def test_loss_sleep_safe(self):
        for seed in (11,12,13):
            events = synthetic('bursts',12,seed)
            sim = PriorityTurnTemporalProtocol(seed=seed,loss=.3,ack_loss=.5,max_hops=32,search_budget=96)
            for node,start,duration in sleeps_for(events,seed,True,800):
                sim.add_sleep(node,start,duration)
            for e in events:
                sim.add_transfer(e.source,e.target,e.amount,at=e.time)
            sim.run(800)
            sim.drain()
            self.assertTrue(audit(sim,events,800)['valid'])
            self.assertEqual(sim.metrics['application_messages'],sim.metrics['application_deliveries'])
            self.assertGreater(sim.metrics['duplicates_suppressed'],0)


if __name__=='__main__':
    unittest.main()
