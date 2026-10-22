"""Known-loop offline fixtures, not private discovery/settlement evidence."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from comfort_zone_policy import locally_willing, local_exposure_delta


def prefs(**overrides):
    return dict(dict(credit_limit=1, comfort_min=-1, comfort_max=1,
                     auto_adjust=True), **overrides)


def change(peer, before, after, own=None, remote=None):
    return dict(peer=peer, before=before, after=after,
                own_preferences=own or prefs(), peer_preferences=remote or prefs())


def fixture(shortcut=True):
    edges = [('A','B',-1), ('B','C',-1), ('C','D',-1), ('D','A',-1),
             ('C','E',-1), ('E','F',-1), ('F','A',-1)]
    if shortcut:
        edges.append(('C','A',0))
    nodes = {}
    for a,b,balance in edges:
        nodes.setdefault(a, {})[b] = balance
        nodes.setdefault(b, {})[a] = -balance
    return nodes


def gross(nodes):
    return sum(abs(x) for peers in nodes.values() for x in peers.values()) // 2


def apply_fixture_cycle(nodes, path):
    # Test author supplies path. No actor is supplied this graph or a benefit flag.
    quoted = {}
    for i, name in enumerate(path):
        prev, following = path[i-1], path[(i+1) % len(path)]
        quoted[name] = [change(prev, nodes[name][prev], nodes[name][prev]-1),
                        change(following, nodes[name][following], nodes[name][following]+1)]
    assert all(locally_willing(changes) for changes in quoted.values())
    prior_positions = {name: sum(peers.values()) for name, peers in nodes.items()}
    before = gross(nodes)
    for name, changes in quoted.items():
        for c in changes:
            nodes[name][c['peer']] = c['after']
    assert prior_positions == {name: sum(peers.values()) for name, peers in nodes.items()}
    assert all(nodes[peer][name] == -balance for name, peers in nodes.items() for peer, balance in peers.items())
    assert 2*(gross(nodes)-before) == sum(local_exposure_delta(c) for c in quoted.values())
    return quoted


class ComfortZonePolicyTests(unittest.TestCase):
    def test_both_competing_choices_shorten_to_one_hop(self):
        for first, remaining, debt in [('ABCD', 'CEFA', 3), ('ABCEF', 'CDA', 2)]:
            with self.subTest(first=first):
                nodes = fixture()
                apply_fixture_cycle(nodes, first)
                self.assertEqual(gross(nodes), debt)
                quotes = apply_fixture_cycle(nodes, remaining)
                self.assertTrue(all(local_exposure_delta(c) <= 0 for c in quotes.values()))
                self.assertEqual(gross(nodes), 1)
                self.assertEqual(nodes['C']['A'], -1)

    def test_repair_can_increase_helper_exposure_without_history(self):
        nodes = fixture(shortcut=False)
        apply_fixture_cycle(nodes, 'ABCD')
        quotes = apply_fixture_cycle(nodes, 'ADCEF')
        self.assertEqual(local_exposure_delta(quotes['D']), 2)
        self.assertEqual(gross(nodes), 2)

    def test_local_permission_also_allows_unwanted_lengthening(self):
        nodes = fixture()
        apply_fixture_cycle(nodes, 'ABCD')
        apply_fixture_cycle(nodes, 'CEFA')
        self.assertEqual(gross(nodes), 1)
        quotes = apply_fixture_cycle(nodes, 'CAFE')
        self.assertEqual(gross(nodes), 3)
        self.assertGreater(sum(local_exposure_delta(c) for c in quotes.values()), 0)

    def test_current_bilateral_bounds_and_opt_outs(self):
        base = [change('a', 0, 1), change('b', 0, -1)]
        self.assertTrue(locally_willing(base))
        for endpoint in ('own_preferences', 'peer_preferences'):
            for pref in (prefs(credit_limit=0), prefs(auto_adjust=False),
                         prefs(comfort_min=0, comfort_max=0)):
                candidate = deepcopy(base)
                for c in candidate:
                    c[endpoint] = pref
                self.assertFalse(locally_willing(candidate))
        candidate = deepcopy(base)
        candidate[0]['own_preferences'] = prefs(comfort_min=1, comfort_max=1)
        candidate[0]['peer_preferences'] = prefs(comfort_min=1, comfort_max=1)
        self.assertFalse(locally_willing(candidate))  # mirrored zones disjoint

    def test_net_positions_and_distinct_edges_required(self):
        self.assertFalse(locally_willing([change('a', 0, 1), change('b', 0, 1)]))
        self.assertFalse(locally_willing([change('a', 0, 1), change('a', 0, -1)]))
        self.assertFalse(locally_willing([change('a', 0, True), change('b', 0, -1)]))

    def test_sign_crossing_uses_actual_exposure_change(self):
        changes = [change('a', -1, 1), change('b', 1, -1)]
        self.assertTrue(locally_willing(changes))
        self.assertEqual(local_exposure_delta(changes), 0)


if __name__ == '__main__':
    unittest.main()
