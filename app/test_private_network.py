"""Private hashlock-v2 HTTP rings: real isolated processes, local-view audits."""
from __future__ import annotations
import json
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from run_private_demo import node_command
from test_network import Network


class CaptureProxy:
    """Harness-only transport observation and one-shot lost-ACK injection."""
    def __init__(self, target):
        self.target = target
        self.messages = []
        self.drop_kind = None
        self.block_kind = None
        self.dropped_id = None
        proxy = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                message = json.loads(body)
                proxy.messages.append(dict(sender=self.headers.get('X-Peer-ID'), body=message))
                if message.get('kind') == proxy.block_kind:
                    self.close_connection = True
                    return
                headers = {key: self.headers[key] for key in ('Content-Type', 'Authorization', 'X-Peer-ID')}
                request = Request(proxy.target + self.path, data=body, headers=headers)
                try:
                    with urlopen(request, timeout=3) as response:
                        result, status = response.read(), response.status
                except HTTPError as error:
                    result, status = error.read(), error.code
                except OSError:
                    self.close_connection = True
                    return
                if message.get('kind') == proxy.drop_kind and proxy.dropped_id is None and status == 200:
                    proxy.dropped_id = message['message_id']
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


class PrivateNetwork(Network):
    def __init__(self, size=3, graph=None):
        self.tmp = tempfile.TemporaryDirectory(prefix='ledgerloops-private-')
        self.directory = Path(self.tmp.name)
        self.nodes = tuple(f'participant_{i:03d}' for i in range(size))
        holders = []
        try:
            for node in self.nodes:
                sock = socket.socket(); sock.bind(('127.0.0.1', 0)); holders.append(sock)
            self.ports = {node: sock.getsockname()[1] for node, sock in zip(self.nodes, holders)}
        finally:
            for sock in holders:
                sock.close()
        self.proxies = {node: CaptureProxy(f'http://127.0.0.1:{self.ports[node]}') for node in self.nodes}
        self.processes, self.logs, self.configs, self.initial = {}, {}, {}, {}
        amounts = [7, 3, 5] if size == 3 else [7] * size
        keys = {frozenset((a, b)): secrets.token_urlsafe(32)
                for a in self.nodes for b in self.nodes if a != b}
        for i, node in enumerate(self.nodes):
            previous, following = self.nodes[i - 1], self.nodes[(i + 1) % size]
            balances = dict(graph[node]) if graph is not None else {previous: amounts[i - 1], following: -amounts[i]}
            self.initial[node] = dict(balances)
            peers = {peer: dict(url=self.proxies[peer].url, balance=balance,
                                key=keys[frozenset((node, peer))]) for peer, balance in balances.items()}
            # Dormant and creditor-side extra neighbours must not join this outgoing search.
            # Their configured endpoint is offline, so accidental routing blocks the test.
            for leaf, balance in ((f'leaf_zero_{i:03d}', 0), (f'leaf_credit_{i:03d}', 2)):
                peers[leaf] = dict(url='http://127.0.0.1:1', balance=balance, key=secrets.token_urlsafe(32))
                self.initial[node][leaf] = balance
            config = dict(node=node, mode='testnet', token=secrets.token_urlsafe(32), peers=peers)
            self.configs[node] = config
            (self.directory / f'{node}.json').write_text(json.dumps(config))
        try:
            for node in self.nodes:
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
            except OSError:
                return False
        self.wait(ready, f'{node} startup')

    def close(self):
        for node in list(self.processes):
            self.stop(node)
        for proxy in self.proxies.values():
            proxy.close()
        self.tmp.cleanup()

    def discover(self):
        status, value = self.request(self.nodes[0], '/api/discover', {'amount': 3})
        assert status == 200, value
        return value

    def prepared_cycle(self):
        ident = self.discover()['id']
        self.wait(lambda: all(self.proposal(node, ident) is not None for node in self.nodes), 'all local proposals')
        return ident

    def completed(self, ident):
        return all(any(r['id'] == ident and r['status'] == 'committed' for r in self.state(node)['receipts'])
                   for node in self.nodes)

    def approve_all(self, ident):
        for node in self.nodes:
            status, data = self.approve(node, ident)
            assert status == 200, data

    def audit_local_views(self):
        for node in self.nodes:
            permitted = {node, *self.configs[node]['peers']}
            all_identities = set(self.nodes) | {peer for config in self.configs.values() for peer in config['peers']}
            forbidden = all_identities - permitted
            with sqlite3.connect(self.directory / f'{node}.sqlite') as db:
                dump = '\n'.join(db.iterdump())
            api = json.dumps(self.state(node), sort_keys=True)
            inbound = json.dumps(self.proxies[node].messages, sort_keys=True)
            outgoing = json.dumps([m for proxy in self.proxies.values() for m in proxy.messages
                                   if m['sender'] == node], sort_keys=True)
            for other in forbidden:
                assert other not in dump, (node, 'database', other)
                assert other not in api, (node, 'API', other)
                assert other not in inbound, (node, 'incoming', other)
                assert other not in outgoing, (node, 'outgoing', other)
            for message in self.proxies[node].messages:
                assert not ({'path', 'route', 'participants', 'length', 'hop_count'} & set(message['body'])), message

    def assert_final(self, test):
        for i, node in enumerate(self.nodes):
            actual = self.balances(node)
            expected = dict(self.initial[node])
            expected[self.nodes[i - 1]] -= 3
            expected[self.nodes[(i + 1) % len(self.nodes)]] += 3
            test.assertEqual(actual, expected)
            test.assertEqual(sum(actual.values()), sum(self.initial[node].values()))
            for peer in self.nodes:
                if peer in actual:
                    test.assertEqual(actual[peer], -self.balances(peer)[node])
            test.assertEqual(len(self.state(node)['receipts']), 1)
        self.audit_local_views()


class PrivateNetworkTests(unittest.TestCase):
    def make_network(self, size=3):
        net = PrivateNetwork(size)
        self.addCleanup(net.close)
        return net

    def test_three_four_seven_node_rings_manual_consent_and_local_views(self):
        for size in (3, 4, 7):
            with self.subTest(size=size):
                net = PrivateNetwork(size)
                try:
                    ident = net.prepared_cycle()
                    net.audit_local_views()
                    for node in net.nodes[:-1]:
                        self.assertEqual(net.approve(node, ident)[0], 200)
                    time.sleep(.5)
                    for node in net.nodes:
                        self.assertEqual(net.balances(node), net.initial[node])
                    self.assertEqual(net.approve(net.nodes[-1], ident)[0], 200)
                    net.wait(lambda: net.completed(ident), f'{size}-node fulfillment')
                    net.assert_final(self)
                finally:
                    net.close()

    def test_lost_fulfillment_ack_replayed_without_double_apply(self):
        net = self.make_network()
        ident = net.prepared_cycle()
        proxy = net.proxies[net.nodes[1]]
        proxy.drop_kind = 'fulfill'
        net.approve_all(ident)
        net.wait(lambda: net.completed(ident), 'fulfillment')
        net.wait(lambda: proxy.dropped_id and sum(m['body']['message_id'] == proxy.dropped_id
                 for m in proxy.messages) >= 2, 'duplicate fulfill after dropped ACK')
        net.assert_final(self)

    def test_prepared_restart_keeps_reservation_and_approval(self):
        net = self.make_network()
        ident = net.prepared_cycle()
        origin = net.nodes[0]
        self.assertEqual(net.approve(origin, ident)[0], 200)
        net.stop(origin, crash=True)
        net.start(origin)
        self.assertTrue(net.proposal(origin, ident)['approved'])
        self.assertTrue(any(b['reserved_by'] == ident for b in net.state(origin)['balances']))
        self.assertEqual(net.balances(origin), net.initial[origin])
        net.approve_all(ident)
        net.wait(lambda: net.completed(ident), 'prepared restart recovery')
        net.assert_final(self)

    def test_missing_wrong_preimage_rejected_without_economic_change(self):
        net = self.make_network()
        ident = net.prepared_cycle()
        receiver, sender = net.nodes[1], net.nodes[0]
        before = net.state(receiver)
        for preimage in (None, '00' * 32):
            message = dict(kind='fulfill', id=ident, condition=net.proposal(receiver, ident)['condition'], amount=3,
                           protocol='private-hashlock-v2', message_id=secrets.token_hex(16))
            if preimage is not None:
                message['preimage'] = preimage
            status, response = net.request(receiver, '/peer/message', message, token=False,
                headers={'Authorization': 'Bearer ' + net.configs[receiver]['peers'][sender]['key'],
                         'X-Peer-ID': sender})
            self.assertEqual(status, 400, response)
            after = net.state(receiver)
            for key in ('balances', 'proposals', 'receipts'):
                self.assertEqual(after[key], before[key])
        net.approve_all(ident)
        net.wait(lambda: net.completed(ident), 'normal fulfillment after rejected preimages')
        net.assert_final(self)

    def test_release_crash_offline_peer_and_restart(self):
        net = self.make_network()
        ident = net.prepared_cycle()
        for proxy in net.proxies.values():
            proxy.block_kind = 'fulfill'
        net.approve_all(ident)
        origin = net.nodes[0]
        net.wait(lambda: net.proposal(origin, ident)['status'] == 'committed', 'durable origin release')
        def held_target():
            return next((node for node, proxy in net.proxies.items()
                         if any(m['body']['kind'] == 'fulfill' for m in proxy.messages)), None)
        target = net.wait(held_target, 'undelivered fulfillment at transport barrier')
        self.assertNotEqual(target, origin)
        net.stop(target, crash=True)
        net.stop(origin, crash=True)
        net.start(origin)
        self.assertEqual(net.proposal(origin, ident)['status'], 'committed')
        self.assertGreater(net.state(origin)['outbox_pending'], 0)
        self.assertEqual(net.request(origin, '/api/pause', {'paused': True})[0], 200)
        for proxy in net.proxies.values():
            proxy.block_kind = None
        net.start(target)
        net.wait(lambda: net.completed(ident), 'irrevocable fulfillment after origin and peer restart')
        net.assert_final(self)
        self.assertTrue(net.state(origin)['paused'])

    def test_repeated_nonorigin_visit_rejects_and_drains(self):
        names = tuple(f'participant_{i:03d}' for i in range(4))
        origin, a, b, c = names
        graph = {origin: {a: -3}, a: {origin: 3, b: -3, c: 3},
                 b: {a: 3, c: -3}, c: {b: 3, a: -3}}
        net = PrivateNetwork(4, graph=graph)
        self.addCleanup(net.close)
        ident = net.discover()['id']
        net.wait(lambda: any(s['id'] == ident and s['status'] == 'no_cycle_on_path'
                            for s in net.state(origin)['searches']), 'repeated-visit rejection at origin')
        net.wait(lambda: all(net.state(n)['outbox_pending'] == 0 for n in net.nodes), 'rejection outboxes drained')
        for node in net.nodes:
            self.assertEqual(net.balances(node), net.initial[node])
            self.assertTrue(all(b['reserved_by'] is None for b in net.state(node)['balances']))
            self.assertTrue(all(r['status'] == 'aborted' for r in net.state(node)['receipts']))
        net.audit_local_views()

    def test_decline_preserves_balances(self):
        net = self.make_network()
        ident = net.prepared_cycle()
        node = net.nodes[1]
        status, response = net.request(node, f'/api/proposals/{ident}/decline',
                                       {'digest': net.proposal(node, ident)['digest']})
        self.assertEqual(status, 200, response)
        net.wait(lambda: all(net.proposal(n, ident)['status'] == 'aborted' for n in net.nodes), 'decline propagation')
        for node in net.nodes:
            self.assertEqual(net.balances(node), net.initial[node])
            self.assertTrue(all(b['reserved_by'] is None for b in net.state(node)['balances']))
        net.audit_local_views()


if __name__ == '__main__':
    unittest.main()
