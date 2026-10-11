"""Actual TCP integration tests: three processes, three SQLite databases.

Run: python -m unittest discover -s app -p test_network.py -v
Tests use fabricated TEST units and loopback only, not a deployed community.
"""
from __future__ import annotations
import json
from pathlib import Path
import socket
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import subprocess
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from run_demo import BALANCES, NODES, create_configs, node_command


class Network:
    def __init__(self, mode='testnet'):
        self.tmp = tempfile.TemporaryDirectory(prefix='ledgerloops-network-')
        self.directory = Path(self.tmp.name)
        holders = []
        try:
            for _ in NODES:
                sock = socket.socket()
                sock.bind(('127.0.0.1', 0))
                holders.append(sock)
            self.ports = {node: sock.getsockname()[1] for node, sock in zip(NODES, holders)}
        finally:
            for sock in holders:
                sock.close()
        self.configs = create_configs(self.directory, self.ports, mode)
        self.processes = {}
        self.logs = {}
        try:
            for node in NODES:
                self.start(node)
        except BaseException:
            self.close()
            raise

    def start(self, node):
        self.logs[node] = open(self.directory / f'{node}.log', 'ab')
        self.processes[node] = subprocess.Popen(node_command(self.directory, node, self.ports[node]),
                                               stdout=self.logs[node], stderr=subprocess.STDOUT)
        def ready():
            if self.processes[node].poll() is not None:
                raise AssertionError((self.directory / f'{node}.log').read_text())
            try:
                return self.request(node, '/api/state')[0] == 200
            except (URLError, ConnectionError, TimeoutError):
                return False
        self.wait(ready, f'{node} startup')

    def stop(self, node, crash=False):
        process = self.processes.pop(node)
        if crash:
            process.kill()
        else:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        self.logs.pop(node).close()

    def close(self):
        for node in list(self.processes):
            self.stop(node)
        self.tmp.cleanup()

    @staticmethod
    def wait(predicate, label, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = predicate()
            if result:
                return result
            time.sleep(.05)
        raise AssertionError(f'Timed out waiting for {label}')

    def request(self, node, path, data=None, token=True, headers=None):
        request_headers = {'Content-Type': 'application/json'}
        if token:
            request_headers['Authorization'] = f'Bearer {self.configs[node]["token"]}'
        request_headers.update(headers or {})
        request = Request(f'http://127.0.0.1:{self.ports[node]}{path}',
                          data=None if data is None else json.dumps(data).encode(),
                          headers=request_headers)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def state(self, node):
        status, value = self.request(node, '/api/state')
        assert status == 200, value
        return value

    def balances(self, node):
        return {entry['peer']: entry['balance'] for entry in self.state(node)['balances']}

    def proposal(self, node, ident):
        return next((p for p in self.state(node)['proposals'] if p['id'] == ident), None)

    def prepared_cycle(self):
        ident = self.discover()['id']
        self.wait(lambda: all(self.proposal(node, ident) is not None for node in NODES), 'all proposals prepared')
        return ident

    def approve(self, node, ident):
        return self.request(node, f'/api/proposals/{ident}/approve', {'digest': self.proposal(node, ident)['digest']})

    def completed(self, ident):
        return all(any(r['id'] == ident and r.get('cycle_complete') for r in self.state(node)['receipts']) for node in NODES)

    def discover(self):
        status, value = self.request('alice', '/api/discover', {'amount': 3})
        assert status in (200, 201, 202), value
        return value


class DropCommitAckProxy:
    """Deliver one commit, then close its HTTP connection without the ACK."""
    def __init__(self, target):
        self.target = target
        self.dropped_id = None
        self.deliveries = {}
        proxy = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                message = json.loads(body)
                headers = {key: self.headers[key] for key in ('Content-Type', 'Authorization', 'X-Peer-ID')}
                request = Request(proxy.target + self.path, data=body, headers=headers)
                with urlopen(request, timeout=3) as response:
                    result = response.read()
                    status = response.status
                ident = message.get('message_id', message.get('mid', message.get('id')))
                if message.get('kind') == 'commit':
                    proxy.deliveries[ident] = proxy.deliveries.get(ident, 0) + 1
                    if proxy.dropped_id is None:
                        proxy.dropped_id = ident
                        self.close_connection = True
                        self.connection.shutdown(socket.SHUT_RDWR)
                        self.connection.close()
                        return
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(result)))
                self.end_headers()
                self.wfile.write(result)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class DemoConfigTests(unittest.TestCase):
    def test_generated_pair_keys_are_symmetric_and_private(self):
        with tempfile.TemporaryDirectory() as directory:
            ports = dict(zip(NODES, (8101, 8102, 8103)))
            configs = create_configs(directory, ports)
            self.assertEqual(len({config['token'] for config in configs.values()}), 3)
            for node in NODES:
                self.assertEqual((Path(directory) / f'{node}.json').stat().st_mode & 0o777, 0o600)
                for peer in configs[node]['peers']:
                    self.assertEqual(configs[node]['peers'][peer]['key'], configs[peer]['peers'][node]['key'])
            self.assertEqual(create_configs(directory, ports), configs)

    def test_partial_configs_and_orphaned_database_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            ports = dict(zip(NODES, (8101, 8102, 8103)))
            create_configs(directory, ports)
            (Path(directory) / 'alice.json').unlink()
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                create_configs(directory, ports)
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'alice.sqlite').touch()
            with self.assertRaisesRegex(ValueError, 'Database'):
                create_configs(directory, ports)

    def test_invalid_ports_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for ports in ((8101, 8101, 8103), (0, 8102, 8103), (8101, 8102, 65536)):
                with self.assertRaises(ValueError):
                    create_configs(directory, dict(zip(NODES, ports)))


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.net = Network()
        self.addCleanup(self.net.close)

    def assert_final_balances(self):
        expected = {'alice': {'bob': -4, 'doris': 2},
                    'bob': {'alice': 4, 'doris': 0},
                    'doris': {'alice': -2, 'bob': 0}}
        for node in NODES:
            state = self.net.state(node)
            actual = self.net.balances(node)
            self.assertEqual(actual, expected[node])
            self.assertEqual(sum(actual.values()), sum(BALANCES[node].values()))
            self.assertTrue(all(entry['reserved_by'] is None for entry in state['balances']))
            for peer, balance in actual.items():
                self.assertEqual(balance, -self.net.balances(peer)[node])

    def test_manual_approval_and_durable_replay(self):
        ident = self.net.prepared_cycle()
        for node in NODES:
            self.assertEqual(self.net.balances(node), BALANCES[node])
            self.assertFalse(self.net.proposal(node, ident)['approved'])
        for node in ('alice', 'bob'):
            self.assertEqual(self.net.approve(node, ident)[0], 200)
        time.sleep(.5)
        for node in NODES:
            self.assertEqual(self.net.balances(node), BALANCES[node])
            self.assertEqual(self.net.state(node)['receipts'], [])
        self.assertEqual(self.net.approve('bob', ident)[0], 200)
        self.assertEqual(self.net.approve('doris', ident)[0], 200)
        self.net.wait(lambda: self.net.completed(ident), 'whole cycle confirmation')
        self.assert_final_balances()
        for node in NODES:
            self.net.approve(node, ident)  # May reject a terminal proposal; must never reapply.
            self.net.stop(node, crash=True)
            self.net.start(node)
        self.assert_final_balances()
        for node in NODES:
            receipts = self.net.state(node)['receipts']
            self.assertEqual(len(receipts), 1)
            self.assertEqual(receipts[0]['id'], ident)
            self.assertTrue(receipts[0]['cycle_complete'])

    def test_offline_participant_and_crash_recovery(self):
        ident = self.net.prepared_cycle()
        for node in ('bob', 'doris'):
            self.assertEqual(self.net.approve(node, ident)[0], 200)
        # Let their durable votes reach the origin before disconnecting Doris.
        def votes_arrived():
            with sqlite3.connect(self.net.directory / 'alice.sqlite') as db:
                row = db.execute('SELECT votes FROM proposals WHERE id=?', (ident,)).fetchone()
                return row and set(json.loads(row[0])) == {'bob', 'doris'}
        self.net.wait(votes_arrived, 'durable peer votes at Alice')
        self.net.stop('doris', crash=True)
        self.assertEqual(self.net.approve('alice', ident)[0], 200)
        self.net.wait(lambda: self.net.proposal('bob', ident)['status'] == 'committed', 'Bob local commit')
        for node in ('alice', 'bob'):
            receipt = self.net.state(node)['receipts'][0]
            self.assertFalse(receipt['cycle_complete'])
        self.assertGreater(self.net.state('bob')['outbox_pending'], 0)
        self.net.stop('bob', crash=True)
        self.net.start('bob')
        self.assertEqual(self.net.balances('bob'), {'alice': 4, 'doris': 0})
        self.assertFalse(self.net.state('bob')['receipts'][0]['cycle_complete'])
        self.assertGreater(self.net.state('bob')['outbox_pending'], 0)
        # Pause new work while allowing irrevocable old work to finish.
        self.assertEqual(self.net.request('bob', '/api/pause', {'paused': True})[0], 200)
        self.net.start('doris')
        self.net.wait(lambda: self.net.completed(ident), 'recovery after participant restart')
        self.assert_final_balances()
        self.assertTrue(self.net.state('bob')['paused'])

    def test_delivered_commit_with_dropped_ack_retries_once_logically(self):
        ident = self.net.prepared_cycle()
        proxy = DropCommitAckProxy(f'http://127.0.0.1:{self.net.ports["doris"]}')
        self.addCleanup(proxy.close)
        self.net.stop('bob')
        path = self.net.directory / 'bob.json'
        config = json.loads(path.read_text())
        config['peers']['doris']['url'] = proxy.url
        path.write_text(json.dumps(config))
        self.net.start('bob')
        for node in NODES:
            self.assertEqual(self.net.approve(node, ident)[0], 200)
        self.net.wait(lambda: self.net.completed(ident), 'completion with dropped commit ACK')
        self.net.wait(lambda: proxy.dropped_id and proxy.deliveries[proxy.dropped_id] >= 2,
                      'duplicate network delivery after lost ACK')
        self.assert_final_balances()
        for node in NODES:
            self.assertEqual(len(self.net.state(node)['receipts']), 1)

    def test_prepared_reservations_survive_offline_and_restart(self):
        ident = self.net.prepared_cycle()
        self.assertEqual(self.net.approve('alice', ident)[0], 200)
        self.net.stop('doris', crash=True)
        self.net.stop('alice', crash=True)
        self.net.start('alice')
        state = self.net.state('alice')
        self.assertTrue(self.net.proposal('alice', ident)['approved'])
        self.assertTrue(all(b['reserved_by'] == ident for b in state['balances']))
        self.assertEqual(self.net.balances('alice'), BALANCES['alice'])
        self.assertEqual(state['receipts'], [])
        self.assertEqual(self.net.request('alice', '/api/discover', {'amount': 1})[0], 400)
        self.net.start('doris')
        for node in ('bob', 'doris'):
            self.assertEqual(self.net.approve(node, ident)[0], 200)
        self.net.wait(lambda: self.net.completed(ident), 'prepared reservation restart recovery')
        self.assert_final_balances()

    def test_decline_releases_unapproved_proposal_without_changing_balances(self):
        ident = self.net.prepared_cycle()
        proposal = self.net.proposal('bob', ident)
        status, response = self.net.request('bob', f'/api/proposals/{ident}/decline',
                                            {'digest': proposal['digest']})
        self.assertEqual(status, 200, response)
        self.net.wait(lambda: all(self.net.proposal(node, ident)['status'] == 'aborted' for node in NODES),
                      'decline abort propagated around cycle')
        for node in NODES:
            self.assertEqual(self.net.balances(node), BALANCES[node])
            self.assertTrue(all(b['reserved_by'] is None for b in self.net.state(node)['balances']))
            self.assertEqual(self.net.state(node)['receipts'][0]['status'], 'aborted')
        new_ident = self.net.prepared_cycle()
        self.assertNotEqual(new_ident, ident)

    def test_authentication(self):
        for node in NODES:
            self.assertIn(self.net.request(node, '/api/state', token=False)[0], (401, 403))
            self.assertIn(self.net.request(node, '/api/discover', {'amount': 3}, token=False)[0], (401, 403))
            self.assertIn(self.net.request(node, '/peer/message', {}, token=False)[0], (401, 403))


if __name__ == '__main__':
    unittest.main()
