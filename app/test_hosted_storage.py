"""Real PostgreSQL durability tests; set LEDGERLOOPS_TEST_POSTGRES_DSN.

Creates randomly named node records in the test database, removing only those
records afterward. Never point this at a production database. The tests exercise
separate OS processes, rollback, restart, and process death while holding a row.
"""
import multiprocessing
import json
import os
import queue
import signal
import sqlite3
import time
import tempfile
import unittest
import uuid
from unittest.mock import patch

from hosted_storage import PgStoreFactory, TABLE


def increment_process(dsn, key, count, errors):
    factory = PgStoreFactory(dsn)
    db = factory.connection(key)
    try:
        for _ in range(count):
            with db:
                previous = db.execute('SELECT n FROM counter').fetchone()[0]
                time.sleep(.002)
                db.execute('UPDATE counter SET n=?', (previous+1,))
    except Exception as error:
        errors.put(type(error).__name__ + ': ' + str(error))
    finally:
        db.close()
        factory.close()


def uncommitted_process(dsn, key, ready):
    factory = PgStoreFactory(dsn)
    db = factory.connection(key)
    with db:
        db.execute('UPDATE counter SET n=999')
        db.execute("INSERT INTO outbox VALUES('uncommitted')")
        ready.set()
        time.sleep(60)  # Parent kills this test process after observing readiness.


@unittest.skipUnless(os.environ.get('LEDGERLOOPS_TEST_POSTGRES_DSN'),
                     'Set LEDGERLOOPS_TEST_POSTGRES_DSN for real PostgreSQL tests')
class PostgresSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ['LEDGERLOOPS_TEST_POSTGRES_DSN']
        self.factory = PgStoreFactory(self.dsn)
        self.factory.initialize()
        self.keys = []
        self.connections = []

    def tearDown(self):
        for connection in self.connections:
            connection.close()
        # Infrastructure-only cleanup, not an actor capability.
        with self.factory._pool.connection() as connection:
            connection.execute(f'DELETE FROM {TABLE} WHERE node_id = ANY(%s)', (self.keys,))
        self.factory.close()

    def node(self):
        key = 'storage-test-' + uuid.uuid4().hex
        self.keys.append(key)
        self.factory.create(key)
        db = self.factory.connection(key)
        self.connections.append(db)
        db.executescript('CREATE TABLE counter(n INTEGER NOT NULL); INSERT INTO counter VALUES(0); '
                         'CREATE TABLE outbox(id TEXT PRIMARY KEY);')
        return key, db

    def test_sqlite_compatibility_and_restart(self):
        key, db = self.node()
        db.row_factory = sqlite3.Row
        with db:
            db.execute('UPDATE counter SET n=?', (17,))
            db.execute('INSERT OR IGNORE INTO outbox VALUES(?)', ('a',))
            db.execute('INSERT OR IGNORE INTO outbox VALUES(?)', ('a',))
        self.assertEqual(dict(db.execute('SELECT n AS count FROM counter').fetchone()), {'count': 17})
        self.assertEqual(db.execute('SELECT id FROM outbox ORDER BY rowid DESC').fetchall()[0][0], 'a')
        self.factory.create(key)  # Repeated provisioning cannot reset an existing ledger.
        second_factory = PgStoreFactory(self.dsn)
        restarted = second_factory.connection(key)
        try:
            self.assertEqual(restarted.execute('SELECT n FROM counter').fetchone()[0], 17)
            self.assertEqual(restarted.execute('SELECT id FROM outbox').fetchall(), [('a',)])
        finally:
            restarted.close()
            second_factory.close()

    def test_ledger_and_outbox_rollback_together(self):
        _, db = self.node()
        with self.assertRaisesRegex(ValueError, 'abort fixture'):
            with db:
                db.execute('UPDATE counter SET n=42')
                db.execute("INSERT INTO outbox VALUES('pending')")
                raise ValueError('abort fixture')
        self.assertEqual(db.execute('SELECT n FROM counter').fetchone()[0], 0)
        self.assertEqual(db.execute('SELECT count(*) FROM outbox').fetchone()[0], 0)
        with db:
            db.execute('UPDATE counter SET n=42')
            db.execute("INSERT INTO outbox VALUES('pending')")
        self.assertEqual(db.execute('SELECT n FROM counter').fetchone()[0], 42)
        self.assertEqual(db.execute('SELECT count(*) FROM outbox').fetchone()[0], 1)

    def test_nested_failure_cannot_be_swallowed_into_partial_commit(self):
        _, db = self.node()
        with self.assertRaisesRegex(sqlite3.OperationalError, 'rolled back'):
            with db:
                db.execute('UPDATE counter SET n=5')
                try:
                    with db:
                        db.execute("INSERT INTO outbox VALUES('partial')")
                        raise ValueError('nested')
                except ValueError:
                    pass
        self.assertEqual(db.execute('SELECT n FROM counter').fetchone()[0], 0)
        self.assertEqual(db.execute('SELECT count(*) FROM outbox').fetchone()[0], 0)

    def test_actor_sql_cannot_read_another_node_or_attach_a_database(self):
        _, left = self.node()
        _, right = self.node()
        right.execute('UPDATE counter SET n=8')
        self.assertEqual(left.execute('SELECT n FROM counter').fetchone()[0], 0)
        with self.assertRaises(sqlite3.OperationalError):
            left.execute(f'SELECT * FROM {TABLE}')
        with self.assertRaises(sqlite3.DatabaseError):
            left.execute("ATTACH DATABASE ':memory:' AS other_node")
        self.assertEqual(right.execute('SELECT n FROM counter').fetchone()[0], 8)

    def test_independent_node_transactions_can_overlap(self):
        _, left = self.node()
        _, right = self.node()
        # Different keys lock different rows. This would deadlock with a global lock.
        with left:
            left.execute('UPDATE counter SET n=1')
            with right:
                right.execute('UPDATE counter SET n=2')
        self.assertEqual(left.execute('SELECT n FROM counter').fetchone()[0], 1)
        self.assertEqual(right.execute('SELECT n FROM counter').fetchone()[0], 2)

    def test_separate_processes_have_no_lost_updates(self):
        key, db = self.node()
        context = multiprocessing.get_context('spawn')
        errors = context.Queue()
        processes = [context.Process(target=increment_process, args=(self.dsn, key, 12, errors))
                     for _ in range(3)]
        try:
            for process in processes:
                process.start()
            for process in processes:
                process.join(20)
                self.assertFalse(process.is_alive(), 'Worker did not make progress')
                self.assertEqual(process.exitcode, 0)
            failures = []
            while True:
                try:
                    failures.append(errors.get_nowait())
                except queue.Empty:
                    break
            self.assertEqual(failures, [])
            self.assertEqual(db.execute('SELECT n FROM counter').fetchone()[0], 36)
        finally:
            for process in processes:
                if process.is_alive():
                    process.kill()
                    process.join()

    def test_process_death_before_commit_keeps_previous_ledger(self):
        key, db = self.node()
        context = multiprocessing.get_context('spawn')
        ready = context.Event()
        process = context.Process(target=uncommitted_process, args=(self.dsn, key, ready))
        process.start()
        try:
            self.assertTrue(ready.wait(15), 'Child failed to acquire its node transaction')
            process.kill()
            process.join(10)
            self.assertEqual(process.exitcode, -signal.SIGKILL)
            self.assertEqual(db.execute('SELECT n FROM counter').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM outbox').fetchone()[0], 0)
        finally:
            if process.is_alive():
                process.kill()
                process.join()

    def test_unprovisioned_key_fails_closed(self):
        connection = self.factory.connection('missing-' + uuid.uuid4().hex)
        try:
            with self.assertRaisesRegex(ValueError, 'not been provisioned'):
                connection.execute('SELECT 1')
        finally:
            connection.close()

    def test_real_private_nodes_restart_and_fulfill_from_postgres(self):
        from private_node import Node
        from run_demo import create_configs
        from verify_private_receipt import verify
        with tempfile.TemporaryDirectory() as directory:
            configs = create_configs(directory, {'alice': 19001, 'bob': 19002, 'doris': 19003})
        keys = {name: 'storage-test-' + uuid.uuid4().hex for name in configs}
        for key in keys.values():
            self.keys.append(key)
            self.factory.create(key)

        def open_nodes():
            result = {}
            for name, config in configs.items():
                db = self.factory.connection(keys[name])
                db.row_factory = sqlite3.Row
                self.connections.append(db)
                with db:
                    result[name] = Node(config, ':memory:', connection=db)
            return result

        nodes = open_nodes()

        def drain():
            for _ in range(100):
                entries = [(name, dict(row)) for name, node in nodes.items()
                           for row in node.db.execute('SELECT * FROM outbox')]
                if not entries:
                    return
                sender, row = entries[-1]
                payload = json.loads(row['data'])
                nodes[row['peer']].receive(sender, payload)
                nodes[row['peer']].receive(sender, payload)  # Real replay handling.
                with nodes[sender].db:
                    nodes[sender].db.execute('DELETE FROM outbox WHERE id=?', (row['id'],))
            self.fail('Private protocol did not drain')

        drain()
        ident = nodes['alice'].discover(3)['id']
        drain()
        alice = nodes['alice']
        alice.approve(ident, json.loads(alice.proposal(ident)['data'])['digest'])
        # Drop all in-memory actors after one approval; retain only PostgreSQL.
        for node in nodes.values():
            node.db.close()
        nodes = open_nodes()
        for name in ('bob', 'doris'):
            node = nodes[name]
            node.approve(ident, json.loads(node.proposal(ident)['data'])['digest'])
        drain()
        for node in nodes.values():
            self.assertEqual(node.proposal(ident)['status'], 'committed')
            self.assertTrue(verify(node.receipts()[0])['valid'])
            self.assertEqual(node.db.execute('SELECT count(*) FROM reservations').fetchone()[0], 0)
        self.assertEqual(nodes['alice'].balance('bob'), -4)
        self.assertEqual(nodes['bob'].balance('doris'), 0)
        self.assertEqual(nodes['doris'].balance('alice'), -2)

    def test_hosted_invitation_recovers_between_endpoint_transactions(self):
        from hosted_runtime import HostedRuntime
        runtime = HostedRuntime(self.factory, 'https://example.test')
        issuer, joiner = 'n_'+uuid.uuid4().hex, 'n_'+uuid.uuid4().hex
        for ident in (issuer, joiner):
            self.keys.append(runtime.key(ident))
            runtime.provision(dict(node_id=ident, name='Storage test account'))
        invitation = runtime.invite(issuer, max_trust=22)['invite_token']
        connect_local = runtime._connect_local

        def fail_second_endpoint(node_id, peer, key, max_trust=10):
            if node_id == issuer:
                raise RuntimeError('Simulated crash between endpoints')
            connect_local(node_id, peer, key, max_trust)

        with patch.object(runtime, '_connect_local', side_effect=fail_second_endpoint):
            with self.assertRaisesRegex(RuntimeError, 'between endpoints'):
                runtime.accept_invite(joiner, invitation, max_trust=9)
        with runtime.node(joiner) as node:
            retained_key = node.peers[issuer]['key']
        self.assertEqual(len(runtime.state(issuer)['contacts']), 0)
        # A new runtime knows nothing of prior memory; same invitation repairs only
        # missing enrollment. No cross-node transaction or key rotation is used.
        restarted = HostedRuntime(self.factory, 'https://example.test')
        restarted.accept_invite(joiner, invitation, max_trust=99)
        for ident, other in ((issuer, joiner), (joiner, issuer)):
            restarted.provision(dict(node_id=ident, name='Storage test account'))
            with restarted.node(ident) as node:
                self.assertEqual(node.peers[other]['key'], retained_key)
                self.assertEqual(node.balance(other), 0)
                own = json.loads(node.db.execute('SELECT own FROM contacts WHERE peer=?', (other,)).fetchone()[0])
                self.assertEqual(own['credit_limit'], 22 if ident == issuer else 9)
                self.assertEqual(own['comfort_max'], 11 if ident == issuer else 4)


if __name__ == '__main__':
    unittest.main()
