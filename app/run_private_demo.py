#!/usr/bin/env python3
"""Launch the private hashlock-v2 three-node TEST network on loopback."""
from __future__ import annotations
import argparse
from pathlib import Path
import signal
import subprocess
import sys
import time
from run_demo import NODES, create_configs


def node_command(directory, node, port):
    return [sys.executable, str(Path(__file__).with_name('private_node.py')),
            '--config', str(Path(directory) / f'{node}.json'),
            '--db', str(Path(directory) / f'{node}.sqlite'), '--host', '127.0.0.1',
            '--port', str(port)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default='/tmp/ledgerloops-private-demo')
    parser.add_argument('--base-port', type=int, default=8861)
    args = parser.parse_args()
    ports = {node: args.base_port + i for i, node in enumerate(NODES)}
    create_configs(args.data_dir, ports)
    children = []
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        for node in NODES:
            children.append(subprocess.Popen(node_command(args.data_dir, node, ports[node])))
            print(f'{node.title()}: http://127.0.0.1:{ports[node]}/  '
                  f'(client token in {Path(args.data_dir) / (node + ".json")})', flush=True)
        print('Private hashlock-v2; TEST units only. Use a fresh directory, never a v1 database.', flush=True)
        while all(p.poll() is None for p in children):
            time.sleep(.5)
        raise RuntimeError('A node exited; stopping the rest of the private network')
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
