"""Version-aware infrastructure scheduling; no account or financial fixtures."""
from concurrent.futures import Future
import unittest

from hosted_worker import WakeupSchedule


IDLE = dict(retry_outbox=False, next_search_at=None)


class ControlledExecutor:
    def __init__(self):
        self.calls = []

    def submit(self, tick, node_id):
        future = Future()
        self.calls.append((node_id, future))
        return future


class WorkerWakeupTests(unittest.TestCase):
    def setUp(self):
        self.schedule = WakeupSchedule()
        self.executor = ControlledExecutor()

    def dispatch(self, versions, now):
        self.schedule.dispatch(versions, self.executor, lambda _: None, now=now)

    def complete(self, result=IDLE, now=.5, wall_time=1000):
        self.executor.calls[-1][1].set_result(result)
        self.schedule.collect(now=now, wall_time=wall_time)

    def test_unchanged_idle_nodes_skip_payload_ticks_until_bounded_heartbeat(self):
        self.dispatch({'alice': 7}, 0)
        self.complete()
        for poll in range(1, 121):
            self.dispatch({'alice': 7}, poll*.5)
        self.assertEqual(len(self.executor.calls), 1,
                         '120 lightweight registry polls must not reload an unchanged idle image')
        self.dispatch({'alice': 7}, 60.5)
        self.assertEqual(len(self.executor.calls), 2, 'A bounded heartbeat remains available without writes')

    def test_new_node_and_changed_version_wake_without_waiting_for_idle_heartbeat(self):
        self.dispatch({'alice': 7}, 0)
        self.complete()
        self.dispatch({'alice': 8, 'bob': 0}, 1)
        self.assertEqual([node for node, _ in self.executor.calls], ['alice', 'alice', 'bob'])

    def test_incoming_change_during_tick_is_not_acknowledged_by_its_completion(self):
        self.dispatch({'alice': 7}, 0)
        first = self.executor.calls[0][1]
        self.dispatch({'alice': 8}, .5)
        self.dispatch({'alice': 9}, 1)
        self.assertEqual(len(self.executor.calls), 1, 'An active node must never get concurrent ticks')
        first.set_result(IDLE)
        self.schedule.collect(now=1.5, wall_time=1000)
        self.dispatch({'alice': 9}, 1.5)
        self.assertEqual(len(self.executor.calls), 2,
                         'Completion must retain the dispatch version and preserve an incoming-write wakeup')
        self.assertEqual(self.schedule.pending['alice'][0], 9)

    def test_queued_outbox_retries_fast_even_without_snapshot_version_changes(self):
        self.dispatch({'alice': 7}, 0)
        self.complete(dict(retry_outbox=True, next_search_at=None))
        self.dispatch({'alice': 7}, .75)
        self.assertEqual(len(self.executor.calls), 1)
        self.dispatch({'alice': 7}, 1)
        self.assertEqual(len(self.executor.calls), 2)

    def test_own_search_deadline_wakes_before_heartbeat_and_past_due_does_not_spin(self):
        self.dispatch({'alice': 7}, 0)
        self.complete(dict(retry_outbox=False, next_search_at=1004), wall_time=1000)
        self.dispatch({'alice': 7}, 4)
        self.assertEqual(len(self.executor.calls), 1)
        self.dispatch({'alice': 7}, 4.5)
        self.assertEqual(len(self.executor.calls), 2)
        self.complete(dict(retry_outbox=False, next_search_at=999), now=5, wall_time=1000)
        self.dispatch({'alice': 7}, 5)
        self.assertEqual(len(self.executor.calls), 2, 'A past deadline still waits for the next infrastructure poll')
        self.dispatch({'alice': 7}, 5.5)
        self.assertEqual(len(self.executor.calls), 3)

    def test_failed_tick_does_not_consume_version_and_retries_after_one_second(self):
        self.dispatch({'alice': 7}, 0)
        self.executor.calls[-1][1].set_exception(TimeoutError('isolated worker test'))
        with self.assertLogs(level='ERROR'):
            self.schedule.collect(now=.5, wall_time=1000)
        self.dispatch({'alice': 7}, 1)
        self.assertEqual(len(self.executor.calls), 1)
        self.dispatch({'alice': 7}, 1.5)
        self.assertEqual(len(self.executor.calls), 2)
        self.assertNotIn('alice', self.schedule.seen)
        self.complete(now=2)
        self.dispatch({'alice': 7}, 2.5)
        self.assertEqual(len(self.executor.calls), 2)

    def test_restart_reloads_existing_registry_nodes_without_local_cache(self):
        self.dispatch({'alice': 7}, 0)
        self.complete()
        restarted = WakeupSchedule()
        restarted.dispatch({'alice': 7}, self.executor, lambda _: None, now=1)
        self.assertEqual(len(self.executor.calls), 2)


if __name__ == '__main__':
    unittest.main()
