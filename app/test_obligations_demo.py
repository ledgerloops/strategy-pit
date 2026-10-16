"""The obligation demo seeds once and preserves its durable lifecycle on restart."""
import json
from pathlib import Path
import tempfile
import unittest

from private_node import Node
from run_demo import NODES
from run_obligations_demo import FIXTURE, initialize


class ObligationsDemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name) / 'demo'
        self.ports = dict(zip(NODES, (19891, 19892, 19893)))

    def open_nodes(self, configs):
        nodes = {name: Node(config, self.directory / f'{name}.sqlite')
                 for name, config in configs.items()}
        self.addCleanup(lambda: [node.db.close() for node in nodes.values()])
        return nodes

    def drain(self, nodes):
        for _ in range(100):
            pending = [(name, dict(row)) for name, node in nodes.items()
                       for row in node.db.execute('SELECT * FROM outbox')]
            if not pending:
                return
            for name, row in pending:
                nodes[row['peer']].receive(name, json.loads(row['data']))
                with nodes[name].db:
                    nodes[name].db.execute('DELETE FROM outbox WHERE id=?', (row['id'],))
        self.fail('Fixture messages did not drain')

    def test_initial_fixture_is_zero_and_credentials_match(self):
        configs = initialize(self.directory, self.ports)
        nodes = self.open_nodes(configs)
        self.drain(nodes)
        for name, node in nodes.items():
            for contact in node.contacts():
                self.assertEqual(contact['balance'], 0)
                self.assertEqual({key: contact['own'][key] for key in
                                  ('credit_limit', 'comfort_min', 'comfort_max', 'auto_adjust')},
                                 dict(credit_limit=10, comfort_min=0, comfort_max=0, auto_adjust=False))
                self.assertEqual(contact['peer_preferences']['credit_limit'], 10)
                peer = contact['peer']
                self.assertEqual(configs[name]['peers'][peer]['key'], configs[peer]['peers'][name]['key'])
                self.assertNotEqual(configs[name]['token'], configs[name]['peers'][peer]['key'])

    def test_restart_preserves_completed_obligations_preferences_and_pending_locks(self):
        configs = initialize(self.directory, self.ports)
        nodes = self.open_nodes(configs)
        self.drain(nodes)
        nodes['alice'].set_preferences('doris', dict(expected_revision=2, credit_limit=7,
                                                    comfort_min=-2, comfort_max=0, auto_adjust=False))
        self.drain(nodes)
        first = dict(id='a'*64, peer='bob', amount=3, direction='i_owe', description='Demo purchase')
        nodes['alice'].propose_obligation(first)
        self.drain(nodes)
        pending = nodes['bob'].obligations()[0]
        nodes['bob'].approve_obligation(pending['id'], pending['digest'])
        self.drain(nodes)
        nodes['bob'].propose_obligation(dict(id='b'*64, peer='doris', amount=2,
                                              direction='i_owe', description='Awaiting consent'))
        self.drain(nodes)
        before = {name: node.state() for name, node in nodes.items()}
        # Closing before reopening exercises SQLite recovery, rather than a second live connection.
        for node in nodes.values():
            node.db.close()
        moved_ports = {name: port + 10 for name, port in self.ports.items()}
        restarted_configs = initialize(self.directory, moved_ports)
        restarted = self.open_nodes(restarted_configs)
        for name, node in restarted.items():
            self.assertEqual(node.state()['balances'], before[name]['balances'])
            self.assertEqual(node.contacts(), before[name]['contacts'])
            self.assertEqual(node.obligations(), before[name]['obligations'])
            self.assertEqual(restarted_configs[name]['token'], configs[name]['token'])
            for peer in node.peers:
                self.assertEqual(node.peers[peer]['url'], f'http://127.0.0.1:{moved_ports[peer]}')
        self.assertEqual(restarted['alice'].balance('bob'), -3)
        self.assertIsNotNone(next(c for c in restarted['doris'].contacts() if c['peer'] == 'bob')['reserved_by'])

    def test_unrelated_and_incomplete_directories_are_not_overwritten(self):
        self.directory.mkdir()
        sentinel = self.directory / 'unrelated.txt'
        sentinel.write_text('retain me')
        with self.assertRaisesRegex(ValueError, 'fresh empty directory'):
            initialize(self.directory, self.ports)
        self.assertEqual(sentinel.read_text(), 'retain me')
        sentinel.unlink()
        marker = self.directory / 'obligations-fixture.json'
        marker.write_text(json.dumps(dict(fixture=FIXTURE, ready=False)))
        with self.assertRaisesRegex(ValueError, 'Incomplete fixture'):
            initialize(self.directory, self.ports)

    def test_restart_refuses_missing_database_or_config(self):
        initialize(self.directory, self.ports)
        database = self.directory / 'bob.sqlite'
        saved = database.read_bytes()
        database.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing fixture'):
            initialize(self.directory, self.ports)
        self.assertFalse(database.exists())
        database.write_bytes(saved)
        (self.directory / 'bob.json').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing fixture'):
            initialize(self.directory, self.ports)


if __name__ == '__main__':
    unittest.main()
