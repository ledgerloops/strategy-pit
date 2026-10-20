#!/usr/bin/env python3
"""Pinned Random DFS/Numbat static protocol benchmark with actual JSON transport.

Actor decisions and search/settlement code are unchanged. A single-process event
scheduler delivers compact JSON bytes, with reliable exactly-once delivery and
seeded bounded delay. This measures logical protocol communication and simulator
runtime, not a distributed deployment, private app protocol or Internet latency.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import heapq
import json
from pathlib import Path
import platform
import sys
import time

EXPERIMENTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXPERIMENTS))
from distributed import Token, Transaction
from dfs_benchmark import describe, positions, replay
from numbat_benchmark import CappedDFS, CappedNumbat

PARAMETERS = dict(max_delay=5, retry_interval=50, max_hops=100,
                  search_budget=256, message_cutoff=250_000)
HORIZON = 500
WIRE_SCHEMA = 'ledgerloops-static-benchmark-json-v1'
SOURCE_FILES = ('distributed.py', 'numbat.py', 'numbat_benchmark.py', 'dfs_benchmark.py')


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes():
    return {**{name: fingerprint(EXPERIMENTS / name) for name in SOURCE_FILES},
            'mdg2/ledgerloops_benchmark.py': fingerprint(Path(__file__))}


def encode_payload(payload):
    token = payload.token if isinstance(payload, Transaction) else payload
    encoded = dict(ident=list(token.ident), path=list(token.path), visited=sorted(token.visited), hops=token.hops)
    if hasattr(token, 'capacities'):
        encoded['capacities'] = list(token.capacities)
    if isinstance(payload, Transaction):
        return dict(type='transaction', token=encoded, nodes=list(payload.nodes), amount=payload.amount,
                    prepared=list(payload.prepared), proposed_at=payload.proposed_at)
    return dict(type='token', token=encoded)


def decode_payload(encoded):
    data = encoded['token']
    token = Token(tuple(data['ident']), list(data['path']), set(data['visited']), data['hops'])
    if 'capacities' in data:
        token.capacities = list(data['capacities'])
    if encoded['type'] == 'transaction':
        return Transaction(token, list(encoded['nodes']), encoded['amount'],
                           list(encoded['prepared']), encoded['proposed_at'])
    if encoded['type'] != 'token':
        raise ValueError('Unknown serialized logical payload type')
    return token


@dataclass(frozen=True)
class WireMessage:
    data: bytes


class JsonTransport:
    """Transport-only adapter; no routing choices or access to remote balances."""
    def __init__(self, *args, **kwargs):
        self.communication = Counter()
        self.bytes_by_kind = Counter()
        self.deliveries_by_kind = Counter()
        self._sending_wire = None
        super().__init__(*args, **kwargs)

    def send(self, source, dest, kind, payload):
        # These exact bytes are placed into the queue and decoded at delivery.
        raw = json.dumps(dict(schema=WIRE_SCHEMA, source=source, dest=dest, kind=kind,
                              payload=encode_payload(payload)), sort_keys=True,
                         ensure_ascii=True, separators=(',', ':')).encode('ascii')
        self.communication['logical_messages_created'] += 1
        self.communication['data_attempts'] += 1
        self.communication['serialized_json_bytes'] += len(raw)
        self.communication['max_serialized_message_bytes'] = max(
            self.communication['max_serialized_message_bytes'], len(raw))
        self.bytes_by_kind[kind] += len(raw)
        previous = self._sending_wire
        self._sending_wire = (dest, kind, WireMessage(raw))
        try:
            return super().send(source, dest, kind, payload)
        finally:
            self._sending_wire = previous

    def schedule(self, at, dest, kind, payload):
        if self._sending_wire is not None:
            expected_dest, expected_kind, wire = self._sending_wire
            if dest != expected_dest or kind != expected_kind:
                raise AssertionError('Unexpected scheduling from logical send')
            payload = wire
        return super().schedule(at, dest, kind, payload)

    def run(self, until, max_events=1_000_000):
        # Same event scheduler as DistributedDFS.run, with wire delivery decoding.
        if until < self.time:
            raise ValueError('Cannot run backwards')
        processed = 0
        while self.events and self.events[0][0] <= until:
            if processed >= max_events:
                raise RuntimeError('Event budget exhausted; simulation not complete')
            self.time, _, dest, kind, payload = heapq.heappop(self.events)
            if isinstance(payload, WireMessage):
                wire = json.loads(payload.data)
                if wire['dest'] != dest or wire['kind'] != kind or wire['schema'] != WIRE_SCHEMA:
                    raise AssertionError('Wire envelope does not match queued delivery')
                payload = decode_payload(wire['payload'])
                self.communication['application_deliveries'] += 1
                self.deliveries_by_kind[kind] += 1
            if kind == 'add':
                self.add_edge(*payload)
            else:
                self.nodes[dest].receive(kind, payload)
            processed += 1
            self.metrics['events'] += 1
        self.time = until
        return dict(self.metrics)


class JsonDFS(JsonTransport, CappedDFS):
    pass


class JsonNumbat(JsonTransport, CappedNumbat):
    pass


def graph_from_case(case):
    nodes = case['nodes']
    if len(set(nodes)) != len(nodes) or any(not isinstance(n, str) for n in nodes):
        raise ValueError('Unique string node IDs required')
    graph = {}
    for edge in case['edges']:
        source, target, amount = edge['source'], edge['target'], edge['amount']
        if source not in nodes or target not in nodes or source == target or type(amount) is not int or amount <= 0:
            raise ValueError('Invalid obligation')
        if (source, target) in graph or (target, source) in graph:
            raise ValueError('Duplicate or antiparallel obligations forbidden')
        graph[source, target] = amount
    if {node for edge in graph for node in edge} != set(nodes):
        raise ValueError('Every benchmark node must have an obligation channel')
    return graph


def run_case(case, method, repeat=0, *, serialize=True):
    graph = graph_from_case(case)
    if method not in ('random', 'numbat'):
        raise ValueError('Unknown fixed algorithm')
    cls = ({'random': JsonDFS, 'numbat': JsonNumbat} if serialize else
           {'random': CappedDFS, 'numbat': CappedNumbat})[method]
    started = time.perf_counter()
    simulation = cls(graph, seed=case['seed'], **PARAMETERS)
    setup_done = time.perf_counter()
    simulation.run(HORIZON, max_events=5_000_000)
    simulation.drain(max_events=5_000_000)
    algorithm_done = time.perf_counter()
    # Auditing is deliberately outside the protocol timing and actor decisions.
    expected = replay(graph, simulation.cycles)
    if expected != simulation.graph_snapshot() or positions(expected) != positions(graph):
        raise AssertionError('Independent ledger or net-position audit failed')
    if simulation.events or simulation.pending_reservations or any(n.active for n in simulation.nodes.values()):
        raise AssertionError('Protocol failed to drain')
    measured = describe(graph, simulation.cycles)
    result = dict(case=case['name'], seed=case['seed'], repeat=repeat, method=method,
        complete=True, nodes=len(case['nodes']), input_edges=len(graph),
        initial_debt=sum(graph.values()), remaining_debt=sum(expected.values()),
        amount_cleared=measured['cleared_scaled'], cleared_percent=measured['cleared_percent'],
        cycles_count=len(simulation.cycles), cycle_hops=measured['cycle_hops'],
        residual_is_acyclic=measured['residual_is_acyclic'],
        source_sha256=source_hashes(), parameters=dict(PARAMETERS, horizon=HORIZON),
        runtime_seconds=algorithm_done-started, setup_seconds=setup_done-started,
        protocol_seconds=algorithm_done-setup_done, protocol_metrics=dict(simulation.metrics),
        cutoff_tick=simulation.cutoff_tick, drain_tick=simulation.time,
        message_overshoot=max(0, simulation.metrics['messages']-PARAMETERS['message_cutoff']),
        independent_replay_ok=True, conservation_ok=True, pending_reservations=0, pending_events=0,
        remaining_edges=[dict(source=a, target=b, amount=value) for (a,b),value in sorted(expected.items())],
        cycles=[dict(nodes=nodes, amount=amount) for nodes,amount in simulation.cycles])
    if serialize:
        if not (simulation.metrics['messages'] == simulation.communication['data_attempts'] ==
                simulation.communication['application_deliveries']):
            raise AssertionError('Created, encoded or delivered logical messages disagree')
        result['communication'] = dict(simulation.communication,
            logical_messages_by_kind={key.removeprefix('messages_'): value for key,value in simulation.metrics.items()
                                      if key.startswith('messages_')},
            serialized_json_bytes_by_kind=dict(simulation.bytes_by_kind),
            application_deliveries_by_kind=dict(simulation.deliveries_by_kind),
            ack_attempts=0, retransmissions=0,
            accounting='Exact compact JSON bytes actually encoded, queued and decoded by this simulator; '
                       'includes logical source/destination/kind/schema envelope and all token/transaction fields. '
                       'Excludes TCP/IP/TLS/HTTP headers and external distribution or replication of input. '
                       'Reliable exactly-once transport has no ACK messages or retransmission implementation.')
    deterministic = {key: result[key] for key in ('amount_cleared', 'remaining_edges', 'cycles',
        'protocol_metrics', 'cutoff_tick', 'drain_tick')}
    if serialize:
        deterministic['communication'] = result['communication']
    result['determinism_sha256'] = hashlib.sha256(json.dumps(deterministic, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()
    result['audit_seconds'] = time.perf_counter()-algorithm_done
    return result


def check_adapter():
    """Serialization must preserve the unchanged actors' exact seeded behavior."""
    import random
    cases = []
    for seed in range(3):
        rng = random.Random(seed)
        edges = {(str(i), str((i+1)%12)): rng.randint(1,100) for i in range(12)}
        for a in range(12):
            for b in range(a+1,12):
                if rng.random()<.25 and (str(a),str(b)) not in edges and (str(b),str(a)) not in edges:
                    source,target = (str(a),str(b)) if rng.random()<.5 else (str(b),str(a))
                    edges[source,target] = rng.randint(1,100)
        cases.append(dict(name='adapter-check', seed=seed, nodes=[str(n) for n in range(12)],
                          edges=[dict(source=a,target=b,amount=v) for (a,b),v in edges.items()]))
    for case in cases:
        for method in ('random','numbat'):
            plain = run_case(case, method, serialize=False)
            encoded = run_case(case, method)
            for key in ('cycles','remaining_edges','protocol_metrics','cutoff_tick','drain_tick'):
                if plain[key] != encoded[key]:
                    raise AssertionError(f'Serialization changed {method} seed{case["seed"]} {key}')
    print('Adapter equivalence: six cases match exact cycle sequence, remaining ledger and protocol metrics.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--methods', nargs='+', choices=['random','numbat'], default=['random','numbat'])
    parser.add_argument('--case', nargs='+', help='Only named cases (all matching seeds).')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        check_adapter()
        if args.input is None:
            return
    if args.input is None or args.output is None or args.repeats < 1:
        parser.error('--input, --output and positive --repeats required')
    if args.output.exists():
        parser.error('Output exists; choose a new result path')
    payload = json.loads(args.input.read_text())
    cases = [case for case in payload['cases'] if not args.case or case['name'] in args.case]
    if not cases:
        parser.error('No matching workload cases')
    report = dict(schema_version=1, complete=False, methods=args.methods,
        input_sha256=fingerprint(args.input), input_metadata=payload.get('metadata', {}),
        source_sha256=source_hashes(), python=platform.python_version(), platform=platform.platform(),
        parameters=dict(PARAMETERS,horizon=HORIZON), repeats=args.repeats,
        expected_runs=len(cases)*len(args.methods)*args.repeats,
        model='Static cancellation-only; concurrent local-state actors in a serialized event simulator. '
              'Paths/visited identities disclosed; debtor-owned balances, no bilateral replication. '
              'Reliable exactly-once delivery, no crashes; settlement conservation audited after drain. '
              'Finite message admission cutoff and finite search horizon do not promise maximality. '
              'Simulation runtime includes protocol serialization/scheduler, not Internet latency or current app UI.',
        runs=[])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        temporary=args.output.with_suffix(args.output.suffix+'.tmp')
        temporary.write_text(json.dumps(report, indent=2)+'\n')
        temporary.replace(args.output)
    save()
    # Repeat-major ordering makes each seed/method appear once per timing block.
    for repeat in range(args.repeats):
        for case in cases:
            for method in args.methods:
                if source_hashes() != report['source_sha256'] or fingerprint(args.input) != report['input_sha256']:
                    raise RuntimeError('Source or workload changed during benchmark')
                result = run_case(case,method,repeat)
                earlier = next((run for run in report['runs'] if run['case'] == result['case']
                                and run['seed'] == result['seed'] and run['method'] == method), None)
                if earlier and earlier['determinism_sha256'] != result['determinism_sha256']:
                    raise AssertionError('Timing repeat changed ledger, cycles or communication results')
                report['runs'].append(result)
                save()
                print(f'{case["name"]}/seed{case["seed"]}/{method}/repeat{repeat}: '
                      f'{result["cleared_percent"]:.4f}% {result["runtime_seconds"]:.3f}s '
                      f'{result["communication"]["data_attempts"]} sends '
                      f'{result["communication"]["serialized_json_bytes"]} JSON bytes', flush=True)
    report['complete']=True
    save()


if __name__ == '__main__':
    main()
