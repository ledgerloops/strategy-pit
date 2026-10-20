"""Independent evidence-tamper and partial-application regression checks."""
import copy
import hashlib
from pathlib import Path
import secrets
import sys
import unittest
from private_stream_audit import compact, endpoint_metrics, check_wire, verify_local_receipt, match_fulfilled_operations, audit_run


def receipt(node, prev, following):
    value = dict(id='01'*32, amount=1, protocol='private-hashlock-v2',
                 hashlock_scheme='sha256-context-v2', created_at=1,
                 changes=[dict(peer=prev, before=1, after=0), dict(peer=following, before=-1, after=0)])
    context = dict(id=value['id'], amount=1, protocol=value['protocol'], unit='TEST', preimage='02'*32)
    value['condition'] = hashlib.sha256(compact(context)).hexdigest()
    value['digest'] = hashlib.sha256(compact(value)).hexdigest()
    value.update(node=node, status='committed', local_fulfilled=True, mode='testnet', unit='TEST', decided_at=2, preimage='02'*32)
    return value


def research_receipt(incoming=1, outgoing=-1):
    value = dict(id='01'*32, amount=1, protocol='private-hashlock-v2', created_at=1,
                 clearing_mode='comfort', policy='private-local-nonexpansion-v1', direction=1,
                 hashlock_scheme='sha256-private-local-nonexpansion-v1')
    pref = dict(revision=1, credit_limit=10, comfort_min=-10, comfort_max=10, auto_adjust=True)
    changes = []
    for peer, before, after in [('c', incoming, incoming-1), ('b', outgoing, outgoing+1)]:
        changes.append(dict(peer=peer, before=before, after=after, own_revision=1, peer_revision=1,
                            own_preferences=dict(pref), peer_preferences=dict(pref),
                            shared_comfort=dict(hard_min=-10, hard_max=10, min=-10, max=10, empty=False),
                            discomfort_before=0, discomfort_after=0))
    value.update(changes=changes, incoming_quote=changes[0], outgoing_quote=changes[1])
    context = {key: value[key] for key in ('id', 'amount', 'protocol', 'clearing_mode', 'policy', 'direction')}
    context.update(unit='TEST', preimage='02'*32)
    value['condition'] = hashlib.sha256(compact(context)).hexdigest()
    value['digest'] = hashlib.sha256(compact(value)).hexdigest()
    value.update(node='a', status='committed', local_fulfilled=True, mode='testnet', unit='TEST', decided_at=2, preimage='02'*32)
    return value


class PrivateStreamAuditTests(unittest.TestCase):
    def integration_result(self, **options):
        from private_stream import PrivateStream
        pref = dict(credit_limit=100, comfort_min=-100, comfort_max=100, auto_adjust=True)
        edges = [('a', 'b', -2, pref, pref), ('b', 'c', -2, pref, pref), ('c', 'a', 0, pref, pref)]
        with PrivateStream(edges, seed=7, method='private_nonexpansion', discovery_until=3, **options) as stream:
            stream.offer(.2, 'a', 'b', -1, 'one-offer')
            return stream.run(8)

    def test_full_adapter_replay_and_exact_ack_emission_accounting(self):
        result = self.integration_result()
        audit = audit_run(result)
        self.assertTrue(audit['independent_audit_passed'], audit['failures'])
        self.assertGreater(audit['completed_hashlock_cycles'], 0)
        self.assertEqual(audit['fully_applied_obligations'], 1)
        self.assertEqual(audit['local_obligation_applications'], 2)
        self.assertEqual(audit['acknowledgements'], sum(e['kind'] == 'ack_request' for e in result['events']))

    def test_full_audit_rejects_trace_bytes_or_unexplained_local_application(self):
        result = self.integration_result()
        for tamper in ('trace', 'bytes', 'receipt'):
            with self.subTest(tamper=tamper):
                bad = copy.deepcopy(result)
                if tamper == 'trace':
                    bad['trace'][0]['debt'] += 1
                elif tamper == 'bytes':
                    next(e for e in bad['events'] if e['kind'] == 'request')['bytes'] += 1
                else:
                    next(e for e in bad['events'] if e.get('local_receipts'))['local_receipts'] = []
                self.assertFalse(audit_run(bad)['independent_audit_passed'])

    def test_full_audit_preserves_loss_retries_and_cap_pending_work(self):
        for options in ({'drop_request_ids': (1,)}, {'drop_ack_ids': (1,)}, {'message_cap': 15}):
            with self.subTest(options=options):
                result = self.integration_result(**options)
                audit = audit_run(result)
                self.assertTrue(audit['independent_audit_passed'], audit['failures'])
                if 'message_cap' in options:
                    self.assertTrue(result['censored'])
                    self.assertGreater(result['final']['pending_messages'], 0)
                else:
                    self.assertGreater(result['retried_requests'], 0)

    def test_debtor_side_metric_preserves_temporary_mirror_disagreement(self):
        ledger = {'a': {'b': 1}, 'b': {'a': -1}}
        self.assertEqual(endpoint_metrics(ledger)['debt'], 1)
        ledger['a']['b'] = -1  # One local side applied a sign-crossing comfort move.
        metrics = endpoint_metrics(ledger)
        self.assertEqual(metrics['debt'], 2)
        self.assertEqual(metrics['mirror_mismatches'], 1)
        ledger['b']['a'] = 1
        self.assertEqual(endpoint_metrics(ledger)['debt'], 1)
        self.assertEqual(endpoint_metrics(ledger)['mirror_mismatches'], 0)

    def test_hash_context_and_local_digest_are_both_required(self):
        value = receipt('a', 'c', 'b')
        verify_local_receipt(value)
        for field, changed in [('preimage', '03'*32), ('created_at', 9), ('amount', 2)]:
            bad = copy.deepcopy(value); bad[field] = changed
            with self.assertRaises(AssertionError):
                verify_local_receipt(bad)

    def test_partial_local_fulfill_is_not_whole_loop_completion(self):
        values = [receipt('a', 'c', 'b'), receipt('b', 'a', 'c'), receipt('c', 'b', 'a')]
        self.assertEqual(len(match_fulfilled_operations(values[:2])['partial_operations']), 1)
        self.assertEqual(len(match_fulfilled_operations(values)['completed_operations']), 1)
        bad = copy.deepcopy(values); bad[1]['changes'][0]['before'] = 2
        with self.assertRaises(AssertionError):
            match_fulfilled_operations(bad)

    def test_route_and_count_fields_fail_wire_allowlist(self):
        value = receipt('a', 'c', 'b')
        payload = {key: value[key] for key in ('id', 'condition', 'amount', 'protocol')}
        payload.update(kind='probe', message_id='opaque')
        peers = {'a': {'b'}, 'b': {'a'}}
        check_wire('a', 'b', payload, peers)
        for key, value in [('path', ['a', 'b']), ('n', 3), ('hop_count', 3), ('origin', 'a')]:
            with self.assertRaises(AssertionError):
                check_wire('a', 'b', dict(payload, **{key: value}), peers)

    def test_research_policy_context_and_local_nonexpansion(self):
        verify_local_receipt(research_receipt())
        verify_local_receipt(research_receipt(incoming=0, outgoing=-1))  # One local helper is neutral overall.
        with self.assertRaises(AssertionError):
            verify_local_receipt(research_receipt(incoming=0, outgoing=0))
        bad = research_receipt(); bad['policy'] = 'bilateral-comfort-v1'
        with self.assertRaises(AssertionError):
            verify_local_receipt(bad)

    def test_local_nonexpansion_is_sufficient_but_not_complete(self):
        # Each vertex sees the cost of its two incident edges, never a global sum.
        costs = [-1, -1, -1, 1, 1]
        self.assertLess(sum(costs), 0)
        local = [costs[i-1]+costs[i] for i in range(len(costs))]
        self.assertGreater(max(local), 0)  # Profitable loop rejected between adjacent helpers.
        self.assertEqual(sum(local), 2*sum(costs))

    def fixture(self, debts):
        """Actual app actors in isolated in-memory databases; no runtime data."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'app'))
        from private_node import Node
        balances = {}
        for debtor, creditor in debts:
            balances.setdefault(debtor, {})[creditor] = -1
            balances.setdefault(creditor, {})[debtor] = 1
        nodes = {}
        for name, links in balances.items():
            config = dict(node=name, mode='testnet', token=secrets.token_hex(32), peers={
                peer: dict(balance=balance, key=secrets.token_hex(32), url='http://127.0.0.1:1')
                for peer, balance in links.items()})
            nodes[name] = Node(config, ':memory:')
            self.addCleanup(nodes[name].db.close)
        return nodes

    def drain(self, nodes):
        for _ in range(200):
            pending = [(name, dict(row)) for name, node in nodes.items()
                       for row in node.db.execute('SELECT * FROM outbox')]
            if not pending:
                return
            source, row = pending[0]
            import json
            nodes[row['peer']].receive(source, json.loads(row['data']))
            with nodes[source].db:
                nodes[source].db.execute('DELETE FROM outbox WHERE id=?', (row['id'],))
        self.fail('Tiny honest fixture did not drain')

    def test_actual_app_broad_comfort_is_not_gross_debt_complete(self):
        import json
        nodes = self.fixture([('a', 'b'), ('b', 'c'), ('c', 'a')])
        self.drain(nodes)
        pref = dict(revision=2, credit_limit=10, comfort_min=-10, comfort_max=10, auto_adjust=True)
        for node in nodes.values():
            with node.db:
                node.db.execute('UPDATE contacts SET own=?,peer_preferences=?', (json.dumps(pref), json.dumps(pref)))
            with self.assertRaises(ValueError):
                node.discover(1, 'comfort')
        # Cancellation of all three debts is feasible, yet broad comfort gives no strict trigger.
        self.assertEqual(sum(max(-node.balance(peer), 0) for node in nodes.values() for peer in node.peers), 3)

    def test_actual_app_lexical_sink_starves_a_cancellable_cycle(self):
        nodes = self.fixture([('b', 'c'), ('c', 'd'), ('d', 'b'), ('b', 'a'), ('c', 'a'), ('d', 'a')])
        self.drain(nodes)
        for _ in range(3):
            for name in ('b', 'c', 'd'):
                self.assertEqual(nodes[name].candidate(1), 'a')
                nodes[name].discover(1, 'cancellation')
                self.drain(nodes)
        for debtor, creditor in [('b', 'c'), ('c', 'd'), ('d', 'b')]:
            self.assertEqual(nodes[debtor].balance(creditor), -1)
        self.assertTrue(all(not node.db.execute('SELECT 1 FROM reservations').fetchone() for node in nodes.values()))

    def test_actual_comfort_loop_can_increase_gross_debt(self):
        import json
        nodes = self.fixture([('a', 'b'), ('b', 'c'), ('c', 'a')])
        self.drain(nodes)
        for name, node in nodes.items():
            with node.db:
                for peer in node.peers:
                    balance = -1 if (name, peer) == ('a', 'b') else 1 if (name, peer) == ('b', 'a') else 0
                    width = 0 if {name, peer} == {'a', 'b'} else 10
                    pref = dict(revision=2, credit_limit=10, comfort_min=-width, comfort_max=width, auto_adjust=True)
                    node.db.execute('UPDATE balances SET balance=? WHERE peer=?', (balance, peer))
                    node.db.execute('UPDATE contacts SET own=?,peer_preferences=? WHERE peer=?', (json.dumps(pref), json.dumps(pref), peer))
        ident = nodes['a'].discover(1, 'comfort')['id']
        self.drain(nodes)
        for node in nodes.values():
            node.approve(ident, json.loads(node.proposal(ident)['data'])['digest'])
        self.drain(nodes)
        debt = sum(max(-node.balance(peer), 0) for node in nodes.values() for peer in node.peers)
        self.assertEqual(debt, 2)  # Origin discomfort fell; gross increased from1 to2.
        for node in nodes.values():
            verify_local_receipt(node.receipts()[0])


if __name__ == '__main__':
    unittest.main()
