#!/usr/bin/env python3
"""Launch three zero-balance TEST nodes for proposing and approving obligations."""
import argparse
import json
from pathlib import Path
import signal
import subprocess
import time

from private_node import Node
from run_demo import NODES, create_configs
from run_private_demo import node_command


FIXTURE = 'obligations-triangle-v1'


def initialize(directory, ports):
    directory = Path(directory)
    marker = directory / 'obligations-fixture.json'
    if marker.exists():
        if json.loads(marker.read_text()) != {'fixture': FIXTURE, 'ready': True}:
            raise ValueError('Incomplete fixture setup; use a fresh directory')
        if not all((directory / f'{name}.{suffix}').is_file()
                   for name in NODES for suffix in ('json', 'sqlite')):
            raise ValueError('Missing fixture config or database; restore matching data or use a fresh directory')
        # Refresh transport addresses without touching durable balances or preferences.
        return create_configs(directory, ports)
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('Use a fresh empty directory for this fixture; existing testnets are not overwritten')
    configs = create_configs(directory, ports)
    marker.write_text(json.dumps({'fixture': FIXTURE, 'ready': False}) + '\n')
    for name, config in configs.items():
        for details in config['peers'].values():
            details['balance'] = 0
        (directory / f'{name}.json').write_text(json.dumps(config, indent=2) + '\n')
        node = Node(config, directory / f'{name}.sqlite')
        try:
            for peer in config['peers']:
                node.set_preferences(peer, dict(expected_revision=1, credit_limit=10,
                                               comfort_min=0, comfort_max=0, auto_adjust=False))
        finally:
            node.db.close()
    marker.write_text(json.dumps({'fixture': FIXTURE, 'ready': True}) + '\n')
    return configs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default='/tmp/ledgerloops-obligations-demo')
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
            print(f'{name.title()}: http://127.0.0.1:{ports[name]}/ '
                  f'(token in {Path(args.data_dir) / (name + ".json")})', flush=True)
        print('TEST fixture: all balances start at zero; each neighbour has a 10 TEST grant. '
              'Propose obligations and approve them at the other node. '
              'Balances, preferences and pending reservations survive restart. Ctrl-C stops all nodes.', flush=True)
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
