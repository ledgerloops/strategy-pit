"""Causal evidence tests; these are deterministic fixtures, not performance runs."""
import copy
import hashlib
import unittest

from private_stream_audit import compact
from private_stream_observer import Observer


def cycle(ident, before=2, amount=1, nodes=('a', 'b', 'c')):
    receipts = []
    for index, node in enumerate(nodes):
        value = dict(id=f'{ident:064x}', amount=amount, protocol='private-hashlock-v2',
                     hashlock_scheme='sha256-context-v2', created_at=1,
                     changes=[dict(peer=nodes[index-1], before=before, after=before-amount),
                              dict(peer=nodes[(index+1) % len(nodes)], before=-before, after=amount-before)])
        context = dict(id=value['id'], amount=amount, protocol=value['protocol'], unit='TEST', preimage='02'*32)
        value['condition'] = hashlib.sha256(compact(context)).hexdigest()
        value['digest'] = hashlib.sha256(compact(value)).hexdigest()
        value.update(node=node, status='committed', local_fulfilled=True, mode='testnet',
                     unit='TEST', decided_at=2, preimage='02'*32)
        receipts.append(value)
    return receipts


def payment(ident, a='a', b='b', before=-2, delta=1):
    base = dict(id=ident, amount=abs(delta), description='fixture', digest='03'*32,
                applied_at=3, status='committed', unit='TEST')
    first = dict(base, peer=b, before=before, after=before+delta, origin=True,
                 direction='peer_owes' if delta > 0 else 'i_owe')
    second = dict(base, peer=a, before=-before, after=-before-delta, origin=False,
                  direction='i_owe' if delta > 0 else 'peer_owes')
    return [(a, first), (b, second)]


def research_cycle(ident, before=2, amount=1):
    values = cycle(ident, before=before, amount=amount)
    prefs = dict(revision=1, credit_limit=10, comfort_min=-10, comfort_max=10, auto_adjust=True)
    zone = dict(hard_min=-10, hard_max=10, min=-10, max=10, empty=False)
    added = {'digest', 'status', 'node', 'mode', 'unit', 'local_fulfilled', 'decided_at', 'preimage'}
    for value in values:
        value.update(clearing_mode='comfort', policy='private-local-nonexpansion-v1',
                     direction=1, hashlock_scheme='sha256-private-local-nonexpansion-v1')
        for change in value['changes']:
            change.update(own_preferences=copy.deepcopy(prefs), peer_preferences=copy.deepcopy(prefs),
                          own_revision=1, peer_revision=1, shared_comfort=zone,
                          discomfort_before=0, discomfort_after=0)
        value['incoming_quote'], value['outgoing_quote'] = copy.deepcopy(value['changes'])
        context = {key: value[key] for key in ('id', 'amount', 'protocol', 'unit', 'preimage',
                                              'clearing_mode', 'policy', 'direction')}
        value['condition'] = hashlib.sha256(compact(context)).hexdigest()
        value['digest'] = hashlib.sha256(compact({k: v for k, v in value.items() if k not in added})).hexdigest()
    return values


class ObserverTests(unittest.TestCase):
    def observer(self, before=2):
        return Observer([('a', 'b', -before), ('b', 'c', -before), ('c', 'a', -before)])

    def feed(self, observer, receipts, count=1):
        for receipt in receipts:
            observer.observe_receipt(receipt['node'], receipt, time=count, message_count=count)
        return observer.trace[-1]

    def test_partial_and_duplicates_cannot_count_whole_cycle(self):
        observer = self.observer()
        values = cycle(1)
        self.feed(observer, values[:2])
        self.feed(observer, values[:1])
        self.assertEqual(observer.trace[-1]['causal_fully_applied_gross'], 6)
        self.assertEqual(observer.trace[-1]['pending']['clearing'], 1)
        final = self.feed(observer, values[2:])
        self.assertEqual(final['causal_fully_applied_gross'], 3)
        self.assertEqual(final['same_posted_no_clearing_gross'], 6)
        self.assertEqual(final['incorporated']['clearing'], 1)
        self.feed(observer, values)
        self.assertEqual(len(observer.application_order), 1)

    def test_later_complete_cycle_waits_for_earlier_partial_cycle(self):
        observer = self.observer()
        first, second = cycle(1, before=2), cycle(2, before=1)
        self.feed(observer, first[:1], 1)
        row = self.feed(observer, second, 2)
        self.assertEqual(row['fully_observed_dependency_blocked'], 1)
        self.assertEqual(row['causal_fully_applied_gross'], 6)
        row = self.feed(observer, first[1:], 3)
        self.assertEqual(row['causal_fully_applied_gross'], 0)
        self.assertEqual([entry['id'] for entry in observer.application_order], [first[0]['id'], second[0]['id']])
        self.assertEqual([entry['message_count'] for entry in observer.application_order], [3, 3])

    def test_completed_quotes_without_predecessor_remain_pending_at_result(self):
        observer = self.observer()
        self.feed(observer, cycle(2, before=1))
        result = observer.result()
        self.assertEqual(result['final']['causal_fully_applied_gross'], 6)
        self.assertEqual(len(result['dependency_blocked']), 1)
        self.assertEqual(result['final']['pending']['clearing'], 1)

    def test_research_policy_requires_strict_whole_operation_reduction(self):
        observer = self.observer()
        self.feed(observer, research_cycle(1))
        self.assertEqual(observer.trace[-1]['cumulative_clearing_gross_reduction'], 3)
        observer = self.observer(before=1)
        # Each participant is locally nonexpanding, but there is no strict
        # origin improvement: sign-crossing all three edges leaves gross flat.
        with self.assertRaises(ValueError):
            self.feed(observer, research_cycle(2, before=1, amount=2))

    def test_external_bilateral_netting_steps_down_and_sign_crossing_steps_up(self):
        observer = self.observer()
        first = payment('p1', before=-2, delta=2)
        observer.observe_obligation(*first[0], time=1, message_count=1)
        self.assertEqual(observer.trace[-1]['same_posted_no_clearing_gross'], 6)
        row = observer.observe_obligation(*first[1], time=2, message_count=2)
        self.assertEqual((row['causal_fully_applied_gross'], row['same_posted_no_clearing_gross']), (4, 4))
        for node, view in payment('p2', before=0, delta=3):
            row = observer.observe_obligation(node, view, time=3, message_count=3)
        self.assertEqual((row['causal_fully_applied_gross'], row['same_posted_no_clearing_gross']), (7, 7))

    def test_reference_replays_same_posted_delta_after_clearing(self):
        observer = self.observer()
        self.feed(observer, cycle(1))
        for node, view in payment('p1', before=-1, delta=2):
            row = observer.observe_obligation(node, view, time=2, message_count=2)
        self.assertEqual(row['causal_fully_applied_gross'], 3)
        self.assertEqual(row['same_posted_no_clearing_gross'], 4)
        self.assertEqual(row['gross_saving'], 1)

    def test_negative_snapshot_saving_is_retained_not_reported_as_cumulative_clearing(self):
        observer = self.observer()
        self.feed(observer, cycle(1))
        for index, (a, b) in enumerate([('a', 'b'), ('b', 'c'), ('c', 'a')]):
            for node, view in payment(f'p{index}', a=a, b=b, before=-1, delta=3):
                row = observer.observe_obligation(node, view, time=2, message_count=2)
        self.assertEqual(row['causal_fully_applied_gross'], 6)
        self.assertEqual(row['same_posted_no_clearing_gross'], 3)
        self.assertEqual(row['gross_saving'], -3)
        self.assertEqual(row['cumulative_clearing_gross_reduction'], 3)

    def test_unapplied_and_lost_ack_keep_economics_distinct_from_protocol(self):
        observer = self.observer()
        views = payment('p1')
        proposed = dict(views[0][1], applied_at=None, status='proposed')
        observer.observe_obligation('a', proposed)
        self.assertEqual(observer.trace[-1]['incorporated']['obligation'], 0)
        committing = dict(views[0][1], status='committing')
        observer.observe_obligation('a', committing)
        observer.observe_obligation(*views[1])
        self.assertEqual(observer.trace[-1]['incorporated']['obligation'], 1)
        observer.observe_obligation(*views[0])  # ACK status update, no second payment.
        self.assertEqual(observer.trace[-1]['incorporated']['obligation'], 1)

    def test_external_op_also_waits_for_overlapping_cycle_predecessor(self):
        observer = self.observer()
        for node, view in payment('p1', before=-1, delta=2):
            observer.observe_obligation(node, view)
        self.assertEqual(observer.trace[-1]['fully_observed_dependency_blocked'], 1)
        self.feed(observer, cycle(1))
        self.assertEqual(observer.application_order[-1]['kind'], 'obligation')
        self.assertEqual(observer.trace[-1]['fully_observed_dependency_blocked'], 0)

    def test_conflicting_duplicate_and_mirrors_fail_closed(self):
        observer = self.observer()
        values = cycle(1)
        observer.observe_receipt('a', values[0])
        bad = copy.deepcopy(values[0]); bad['decided_at'] = 99
        with self.assertRaises(ValueError):
            observer.observe_receipt('a', bad)
        observer = self.observer()
        first, second = payment('p1')
        observer.observe_obligation(*first)
        second[1]['before'] -= 1; second[1]['after'] -= 1
        with self.assertRaises(ValueError):
            observer.observe_obligation(*second)

    def test_context_mismatch_and_disconnected_same_id_rejected(self):
        observer = self.observer()
        values = cycle(1)
        values[2] = cycle(1, amount=2)[2]
        with self.assertRaises(ValueError):
            self.feed(observer, values)
        observer = Observer([('a', 'b', -2), ('b', 'c', -2), ('c', 'a', -2),
                             ('d', 'e', -2), ('e', 'f', -2), ('f', 'd', -2)])
        # First closed component is valid alone, so adding a second component
        # under the same opaque id must fail rather than silently count it.
        self.feed(observer, cycle(1))
        with self.assertRaises(ValueError):
            self.feed(observer, cycle(1, nodes=('d', 'e', 'f')))

    def test_unknown_edges_and_backwards_observation_clocks_rejected(self):
        observer = self.observer()
        with self.assertRaises(ValueError):
            for node, value in payment('p1', a='a', b='d'):
                observer.observe_obligation(node, value)
        observer.snapshot()
        observer.observe_event(dict(time=3), message_count=5)
        with self.assertRaises(ValueError):
            observer.observe_event(dict(time=2), message_count=5)
        with self.assertRaises(ValueError):
            observer.observe_event(dict(time=3), message_count=4)


if __name__ == '__main__':
    unittest.main()
