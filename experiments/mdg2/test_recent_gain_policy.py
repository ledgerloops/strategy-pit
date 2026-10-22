"""Offline consent fixtures, not a private discovery/settlement benchmark."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from recent_gain_policy import RecentGainConsent


def prefs(**changes):
    return dict(dict(credit_limit=10, comfort_min=-10, comfort_max=10,
                     auto_adjust=True), **changes)


def node(balances, preferences=None):
    pref = preferences or prefs()
    return RecentGainConsent({peer: (value, pref, pref) for peer, value in balances.items()})


def fixture(arrows):
    balances = {}
    for a, b in arrows:
        balances.setdefault(a, {})[b] = -1
        balances.setdefault(b, {})[a] = 1
    return {name: node(values) for name, values in balances.items()}


def gross(nodes):
    return sum(abs(edge['balance']) for n in nodes.values() for edge in n.edges.values()) // 2


def apply_known_cycle(nodes, path, ident):
    # The fixture chooses a known loop to test consent, not to simulate discovery.
    changes = {}
    for i, name in enumerate(path):
        prev, following = path[i-1], path[(i+1) % len(path)]
        n = nodes[name]
        changes[name] = {prev: n.edges[prev]['balance']-1,
                         following: n.edges[following]['balance']+1}
    assert all(nodes[name].willing(change) for name, change in changes.items())
    for name, change in changes.items():
        nodes[name].observe_completed(ident, change)


class RecentGainTests(unittest.TestCase):
    def test_competing_loop_repair_from_three_to_two(self):
        nodes = fixture([('A','B'), ('B','C'), ('C','D'), ('D','A'),
                         ('C','E'), ('E','F'), ('F','A')])
        self.assertEqual(gross(nodes), 7)
        apply_known_cycle(nodes, 'ABCD', 'short')
        self.assertEqual(gross(nodes), 3)
        self.assertTrue(all(e['balance'] == 0 for e in nodes['D'].edges.values()))
        apply_known_cycle(nodes, 'ADCEF', 'repair')
        self.assertEqual(gross(nodes), 2)
        self.assertEqual({p: e['balance'] for p, e in nodes['D'].edges.items()}, {'C': 1, 'A': -1})
        self.assertTrue(all(e['balance'] == 0 for name in 'BEF' for e in nodes[name].edges.values()))

    def test_local_willingness_alone_can_increase_global_debt(self):
        nodes = fixture([('A','B'), ('B','C'), ('A','E'), ('E','D'), ('D','C'), ('C','A')])
        apply_known_cycle(nodes, 'AEDC', 'first')
        self.assertEqual(gross(nodes), 2)
        # Every local predicate passes, but aggregate improvement MUST reject this.
        apply_known_cycle(nodes, 'ABCDE', 'inadmissible-global-regression')
        self.assertEqual(gross(nodes), 3)

    def test_no_ratchet_no_opposite_debt_and_idempotent_replay(self):
        n = node({'a': 2, 'b': -2})
        n.observe_completed('clear', {'a': 0, 'b': 0})
        self.assertTrue(n.willing({'a': 2, 'b': -2}))
        self.assertFalse(n.willing({'a': 3, 'b': -3}))
        self.assertFalse(n.willing({'a': -1, 'b': 1}))
        n.observe_completed('restore', {'a': 2, 'b': -2})
        n.observe_completed('clear', {'a': 0, 'b': 0})  # duplicate cannot reset state
        self.assertEqual(n.edges['a']['balance'], 2)
        self.assertFalse(n.willing({'a': 3, 'b': -3}))
        with self.assertRaises(ValueError):
            n.observe_completed('clear', {'a': 1, 'b': -1})

    def test_transactions_and_changed_settings_invalidate_only_affected_edge(self):
        for event in ('transaction', 'settings'):
            n = node({'a': 2, 'b': -2})
            n.observe_completed('clear', {'a': 0, 'b': 0})
            if event == 'transaction':
                n.observe_transaction('a', 1)
                self.assertEqual(n.edges['a']['baseline'], 1)
            else:
                n.update_preferences('a', prefs(credit_limit=9), prefs())
                self.assertEqual(n.edges['a']['baseline'], 0)
            self.assertEqual(n.edges['b']['baseline'], -2)
            self.assertFalse(n.willing({'a': 2, 'b': -2}))

    def test_noop_settings_do_not_expire_history(self):
        n = node({'a': 2, 'b': -2})
        n.observe_completed('clear', {'a': 0, 'b': 0})
        n.update_preferences('a', prefs(), prefs())
        self.assertTrue(n.willing({'a': 2, 'b': -2}))

    def test_current_hard_limits_comfort_and_opt_in_still_apply(self):
        for pref in (prefs(credit_limit=1), prefs(comfort_min=0, comfort_max=0)):
            n = node({'a': 2, 'b': -2}, pref)
            n.observe_completed('clear', {'a': 0, 'b': 0})
            self.assertFalse(n.willing({'a': 2, 'b': -2}))
        n = node({'a': 2, 'b': -2}, prefs(auto_adjust=False))
        self.assertFalse(n.willing({'a': 0, 'b': 0}))


if __name__ == '__main__':
    unittest.main()
