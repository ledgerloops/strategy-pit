#!/usr/bin/env python3
"""Launch three isolated LedgerLoops test nodes on loopback; no real balances."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

NODES = ('alice', 'bob', 'doris')
BALANCES = {'alice': {'bob': -7, 'doris': 5},
            'bob': {'alice': 7, 'doris': -3},
            'doris': {'alice': -5, 'bob': 3}}


def create_configs(directory, ports, mode='testnet'):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if set(ports) != set(NODES) or len(set(ports.values())) != len(NODES) or any(
            not isinstance(port, int) or not 1 <= port <= 65535 for port in ports.values()):
        raise ValueError('Three distinct ports in range 1–65535 are required')
    existing = [node for node in NODES if (directory / f'{node}.json').exists()]
    if existing and len(existing) != len(NODES):
        raise ValueError('Incomplete config set; restore matching configs or use a fresh directory')
    if not existing and any((directory / f'{node}.sqlite').exists() for node in NODES):
        raise ValueError('Database exists without its config; restore config or use a fresh directory')
    configs = {}
    keys = {tuple(sorted((a, b))): secrets.token_urlsafe(32)
            for a in NODES for b in NODES if a != b}
    for node in NODES:
        path = directory / f'{node}.json'
        if path.exists():
            config = json.loads(path.read_text())
            if config['mode'] != mode:
                raise ValueError('Existing demo mode differs; use a fresh data directory')
            for peer in config['peers']:
                config['peers'][peer]['url'] = f'http://127.0.0.1:{ports[peer]}'
        else:
            config = {'node': node, 'mode': mode, 'token': secrets.token_urlsafe(32),
                      'peers': {
                          peer: {'url': f'http://127.0.0.1:{ports[peer]}',
                                 'balance': balance, 'key': keys[tuple(sorted((node, peer)))]}
                          for peer, balance in BALANCES[node].items()}}
        configs[node] = config
    for node in NODES:
        for peer in configs[node]['peers']:
            if configs[node]['peers'][peer]['key'] != configs[peer]['peers'][node]['key']:
                raise ValueError('Peer key mismatch; restore a matching set of configs')
    for node, config in configs.items():
        path = directory / f'{node}.json'
        path.touch(mode=0o600, exist_ok=True)
        path.chmod(0o600)
        path.write_text(json.dumps(config, indent=2) + '\n')
    return configs


def node_command(directory, node, port):
    return [sys.executable, str(Path(__file__).with_name('node.py')),
            '--config', str(Path(directory) / f'{node}.json'),
            '--db', str(Path(directory) / f'{node}.sqlite'), '--host', '127.0.0.1',
            '--port', str(port)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default='/tmp/ledgerloops-demo')
    parser.add_argument('--base-port', type=int, default=8761)
    args = parser.parse_args()
    ports = {node: args.base_port + i for i, node in enumerate(NODES)}
    configs = create_configs(args.data_dir, ports)
    children = []
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        for node in NODES:
            children.append(subprocess.Popen(node_command(args.data_dir, node, ports[node])))
            print(f'{node.title()}: http://127.0.0.1:{ports[node]}/  '
                  f'(client token in {Path(args.data_dir) / (node + ".json")})', flush=True)
        print('Test units only. Separate databases and neighbour HTTP messages. Ctrl-C stops all nodes.', flush=True)
        while all(p.poll() is None for p in children):
            time.sleep(.5)
        raise RuntimeError('A demo node exited; stopping the remaining nodes')
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == '__main__':
    main()
