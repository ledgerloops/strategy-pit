import random
import unittest

from local_turns import LocalTurn, TurnMessage


class Pair:
    def __init__(self, batch=2):
        self.wire = []
        self.delivered = [[], []]
        self.ends = [LocalTurn(i, 1-i,
                              lambda msg, i=i: self.wire.append((1-i, msg)),
                              self.delivered[i].append, max_batch=batch)
                     for i in range(2)]

    def deliver(self, index=0, duplicate=False):
        dest, msg = self.wire.pop(index)
        self.ends[dest].receive(msg)
        if duplicate:
            self.ends[dest].receive(msg)
        assert sum(end.owns_turn for end in self.ends) <= 1
        return msg

    def drain(self, seed=0):
        rng = random.Random(seed)
        for _ in range(10000):
            if not self.wire:
                for end in self.ends:
                    end.pump()
            if not self.wire:
                return
            self.deliver(rng.randrange(len(self.wire)), duplicate=True)
        raise AssertionError('did not quiesce')


class LocalTurnTests(unittest.TestCase):
    def test_grant_waits_for_reordered_payload_barrier(self):
        pair = Pair()
        pair.ends[0].enqueue('first')
        pair.ends[1].enqueue('second')
        pair.deliver(1)  # request delivered before first payload
        pair.deliver(1, duplicate=True)  # grant arrives before first payload
        self.assertFalse(pair.ends[1].owns_turn)
        self.assertEqual(pair.delivered, [[], []])
        pair.deliver(0, duplicate=True)
        self.assertTrue(pair.ends[1].owns_turn)
        pair.drain()
        self.assertEqual(pair.delivered, [['second'], ['first']])

    def test_both_queues_make_progress_under_reordering_and_duplicates(self):
        for seed in range(30):
            pair = Pair(batch=3)
            # Queue while endpoints are asleep; wake with simultaneous demand.
            for i in range(2):
                pair.ends[i].outbox.extend((i, j) for j in range(30))
            pair.ends[0].pump()
            pair.ends[1].pump()
            pair.drain(seed)
            for receiver in range(2):
                self.assertEqual(pair.delivered[receiver], [(1-receiver, j) for j in range(30)])
            self.assertFalse(any(end.outbox for end in pair.ends))

    def test_sleep_or_dropped_grant_does_not_create_a_second_owner(self):
        pair = Pair()
        pair.ends[1].enqueue('queued')
        pair.deliver()  # owner receives request, relinquishes
        retry = pair.wire.pop()  # first grant transmission dropped
        for _ in range(100):
            for end in pair.ends:
                end.pump()
        self.assertEqual(pair.delivered, [[], []])
        self.assertFalse(any(end.owns_turn for end in pair.ends))
        pair.wire.append(retry)  # reliable adapter retry after peer wakes
        pair.drain()
        self.assertEqual(pair.delivered[0], ['queued'])

    def test_stale_requests_and_grants_do_not_resurrect_turns(self):
        pair = Pair()
        for n in range(12):
            pair.ends[n % 2].enqueue(n)
            pair.drain(n)
        before = [end.epoch for end in pair.ends]
        pair.ends[0].receive(TurnMessage('request', 1))
        pair.ends[1].receive(TurnMessage('grant', 1, 0))
        self.assertEqual([end.epoch for end in pair.ends], before)
        self.assertEqual(sum(end.owns_turn for end in pair.ends), 1)
        self.assertTrue(all(len(end.received) <= 1 for end in pair.ends))
        pair.ends[1].receive(TurnMessage('data', 0, 0, 'old duplicate'))
        self.assertNotIn('old duplicate', pair.delivered[1])

    def test_invalid_owner_cannot_send_data(self):
        pair = Pair()
        with self.assertRaises(ValueError):
            pair.ends[0].receive(TurnMessage('data', 0, 0, 'invalid'))


if __name__ == '__main__':
    unittest.main()
