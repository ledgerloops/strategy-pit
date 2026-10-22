"""Disposable real HTTP/PostgreSQL hosted browser fixture; never a deployment.

Requires LEDGERLOOPS_TEST_POSTGRES_DSN pointing to a local TEST PostgreSQL server.
Uses a fresh random namespace and removes only its own snapshots on shutdown.
Workers deliver genuine HTTP neighbour envelopes; no protocol functions are
mocked and no graph-aware settlement helper is used.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
import secrets
import signal
import socket
import threading

from werkzeug.serving import make_server
from psycopg.conninfo import conninfo_to_dict
from hosted_server import create_app
from hosted_storage import PgStoreFactory, TABLE


class ScopedStores:
    def __init__(self, factory, prefix):
        self.factory, self.prefix = factory, prefix

    def create(self, key):
        return self.factory.create(self.prefix+key)

    def connection(self, key):
        return self.factory.connection(self.prefix+key)

    def list_nodes(self):
        return [key[len(self.prefix):] for key in self.factory.list_nodes() if key.startswith(self.prefix)]


def main():
    dsn = os.environ.get('LEDGERLOOPS_TEST_POSTGRES_DSN')
    if not dsn:
        raise SystemExit('Set LEDGERLOOPS_TEST_POSTGRES_DSN to a disposable local TEST database')
    config = conninfo_to_dict(dsn)
    if config.get('host') not in ('localhost', '127.0.0.1', '::1') or config.get('hostaddr', '127.0.0.1') not in ('127.0.0.1', '::1'):
        raise SystemExit('Browser fixture requires an explicit loopback PostgreSQL host')
    # Only loopback communication in this browser fixture bypasses HTTP proxies.
    os.environ['no_proxy'] = os.environ.get('no_proxy', '')+',localhost,127.0.0.1'
    factory = PgStoreFactory(dsn, max_connections=8)
    factory.initialize()
    prefix = 'browser-test-'+secrets.token_hex(16)+':'
    stores = ScopedStores(factory, prefix)
    stopped = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stopped.set())
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    origin = f'http://localhost:{port}'
    app = create_app(stores=stores, origin=origin, development=True)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    server = make_server('127.0.0.1', port, app, threaded=True)
    runtime = app.extensions['hosted_runtime']
    web = threading.Thread(target=server.serve_forever, daemon=True)
    web.start()

    def schedule():
        pending = {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            while not stopped.wait(.1):
                for node_id, future in list(pending.items()):
                    if future.done():
                        if future.exception():
                            print(json.dumps({'worker_error': type(future.exception()).__name__}), flush=True)
                        del pending[node_id]
                for node_id in runtime.scheduled_nodes():
                    if node_id not in pending:
                        pending[node_id] = pool.submit(runtime.tick, node_id)

    worker = threading.Thread(target=schedule, daemon=True)
    worker.start()
    print(json.dumps({'origin': origin, 'fixture': 'real-http-postgresql'}), flush=True)
    try:
        stopped.wait()
    finally:
        stopped.set()
        worker.join(timeout=15)
        server.shutdown()
        web.join(timeout=5)
        app.extensions['hosted_auth'].db.close()
        with factory._pool.connection() as connection:
            connection.execute(f'DELETE FROM {TABLE} WHERE node_id LIKE %s', (prefix+'%',))
        factory.close()


if __name__ == '__main__':
    main()
