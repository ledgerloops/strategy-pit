#!/usr/bin/env python3
"""Three-node comfort/hashlock fixture: debt can rise while discomfort falls."""
import argparse
import json
from pathlib import Path
import signal
import subprocess
import sys
import time
from run_demo import NODES, create_configs
from run_private_demo import node_command
from private_node import Node


def initialize(directory, ports):
    directory = Path(directory)
    marker = directory / 'comfort-fixture.json'
    if marker.exists():
        if json.loads(marker.read_text()) != {'fixture': 'comfort-triangle-v1', 'ready': True}:
            raise ValueError('Incomplete fixture setup; use a fresh directory')
        if not all((directory / f'{name}.sqlite').exists() for name in NODES):
            raise ValueError('Missing fixture database; restore matching data or use a fresh directory')
        return create_configs(directory, ports)
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('Use a fresh empty directory for this fixture; existing testnets are not overwritten')
    configs = create_configs(directory, ports)
    for name, config in configs.items():
        for peer, details in config['peers'].items():
            details['balance'] = -2 if (name, peer) == ('alice', 'bob') else 2 if (name, peer) == ('bob', 'alice') else 0
        (directory / f'{name}.json').write_text(json.dumps(config, indent=2) + '\n')
    for name, config in configs.items():
        node = Node(config, directory / f'{name}.sqlite')
        try:
            for peer in config['peers']:
                helper = {name, peer} != {'alice', 'bob'}
                node.set_preferences(peer, dict(expected_revision=1, credit_limit=4,
                                               comfort_min=-2 if helper else 0,
                                               comfort_max=2 if helper else 0, auto_adjust=True))
        finally:
            node.db.close()
    marker.write_text(json.dumps({'fixture': 'comfort-triangle-v1', 'ready': True}) + '\n')
    return configs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default='/tmp/ledgerloops-comfort-settlement')
    parser.add_argument('--base-port', type=int, default=8991)
    args = parser.parse_args()
    ports = {name: args.base_port + i for i, name in enumerate(NODES)}
    initialize(args.data_dir, ports)
    children = []
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        for name in NODES:
            children.append(subprocess.Popen(node_command(args.data_dir, name, ports[name])))
            print(f'{name.title()}: http://127.0.0.1:{ports[name]}/ (token in {Path(args.data_dir) / (name + ".json")})', flush=True)
        print('TEST fixture: Alice owes Bob 2. Helper links start at zero. Choose comfort mode, amount 2, then approve at all three nodes. Existing balances and preferences survive restart.', flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(.5)
        raise RuntimeError('A node exited; stopping the test network')
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
