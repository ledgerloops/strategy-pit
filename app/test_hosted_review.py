"""Independent hosted automation permission regressions using real local nodes."""
from contextlib import contextmanager
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

from hosted_runtime import HostedRuntime
import test_headroom_settlement as settlement_fixture


class HostedAutomationReviewTests(unittest.TestCase):
    def pending_cancellation(self, *, tight_comfort=False, disjoint_comfort=False, assistance=True):
        fixture = settlement_fixture.HeadroomSettlementTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.start([('A', 'B', -1), ('B', 'C', -1), ('C', 'A', -1)])
        if tight_comfort or disjoint_comfort or not assistance:
            for node in fixture.nodes.values():
                for peer in node.peers:
                    balance = node.balance(peer)
                    node.set_preferences(peer, dict(expected_revision=2, credit_limit=20,
                        comfort_min=1 if disjoint_comfort else balance if tight_comfort else -20,
                        comfort_max=2 if disjoint_comfort else balance if tight_comfort else 20,
                        auto_adjust=assistance))
            fixture.drain()
        ident = fixture.nodes['A'].discover(1, mode='cancellation')['id']
        fixture.drain()
        target = fixture.nodes['A']
        self.assertEqual(target.proposal(ident)['status'], 'pending')
        with target.db:
            target.db.execute("INSERT INTO meta VALUES('hosted_automation','true')")
            target.db.execute("INSERT INTO meta VALUES('hosted_next_search','9999999999')")

        @contextmanager
        def own_node(node_id):
            self.assertEqual(node_id, 'A')
            with target.db:
                yield target

        runtime = HostedRuntime(None, 'https://app.ledgerloops.com')
        with patch.object(runtime, 'node', own_node), patch('hosted_runtime.urlopen',
                side_effect=URLError('Delivery deliberately unavailable in permission test')):
            runtime.tick('A')
        return target.proposal(ident), json.loads(target.proposal(ident)['data'])

    def test_automatic_cancellation_requires_result_inside_comfort_zone(self):
        row, data = self.pending_cancellation(tight_comfort=True)
        self.assertTrue(all(change['after'] == 0 for change in data['changes']))
        self.assertFalse(row['approved'], 'Automatic clearing must not leave agreed comfort zones')

    def test_automatic_cancellation_within_comfort_zone_is_allowed(self):
        row, _ = self.pending_cancellation()
        self.assertTrue(row['approved'])

    def test_automatic_cancellation_preserves_assistance_opt_out(self):
        row, _ = self.pending_cancellation(assistance=False)
        self.assertFalse(row['approved'])

    def test_disjoint_comfort_does_not_break_worker_wakeup(self):
        row, _ = self.pending_cancellation(disjoint_comfort=True)
        self.assertFalse(row['approved'])


if __name__ == '__main__':
    unittest.main()
