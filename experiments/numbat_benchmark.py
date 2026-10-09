"""Held-out Numbat evaluation against the existing 80-case synthetic matrix.

Default settings were frozen using training seeds101/102. Saved baseline scores
are reused only after input and source hashes match. The message comparison uses
an equal admission cutoff, then drains in-flight work: total messages can exceed
the cutoff and overshoot is reported explicitly, not called a hard budget.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform

from distributed import DistributedDFS
from numbat import Numbat
from simulate import scenario, audit

ROOT = Path(__file__).parent


class MessageCutoff:
    def __init__(self, *args, message_cutoff=None, **kwargs):
        self.message_cutoff = message_cutoff
        self.cutoff_tick = None
        super().__init__(*args, **kwargs)

    def send(self, *args, **kwargs):
        super().send(*args, **kwargs)
        if (self.message_cutoff is not None and self.cutoff_tick is None and
                self.metrics['messages'] >= self.message_cutoff):
            self.cutoff_tick = self.time
            self.stop_searches()


class CappedNumbat(MessageCutoff, Numbat):
    pass


class CappedDFS(MessageCutoff, DistributedDFS):
    pass


def run_case(case, label, cutoff=None):
    additions = scenario(case['scenario'], case['seed'], case['nodes'], 500)
    stream = json.dumps([event.__dict__ for event in additions], sort_keys=True)
    assert hashlib.sha256(stream.encode()).hexdigest() == case['stream_sha256']
    cls = CappedNumbat if label == 'numbat' else CappedDFS
    kwargs = dict(seed=case['seed'], max_delay=case['max_message_delay'],
                  retry_interval=case['retry_interval'], max_hops=case['max_hops'],
                  search_budget=case['search_budget'], message_cutoff=cutoff)
    if label != 'numbat':
        kwargs['policy'] = 'largest' if label == 'distributed_largest_dfs' else 'random'
    simulation = cls(**kwargs)
    for event in additions:
        simulation.add_edge(event.source, event.target, event.amount, at=event.time)
    simulation.run(case['search_horizon'])
    simulation.drain()
    if simulation.time > case['observation_horizon']:
        raise AssertionError('Drain exceeded shared observation horizon')
    measured, expected = audit(additions, simulation.cycle_records, case['observation_horizon'])
    assert expected == simulation.graph_snapshot()
    assert simulation.pending_reservations == 0 and not simulation.events
    measured.update(protocol=dict(simulation.metrics), drain_completed_at=simulation.time,
                    pending_events_after_drain=0, pending_reservations_after_drain=0,
                    message_admission_cutoff=cutoff, cutoff_tick=simulation.cutoff_tick,
                    message_overshoot=max(0, simulation.metrics['messages'] - cutoff) if cutoff else 0)
    return measured


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'results/numbat-heldout.json')
    parser.add_argument('--skip-message-cutoff', action='store_true')
    args = parser.parse_args()
    sources = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
               for name in ('distributed.py', 'simulate.py', 'dfs_benchmark.py', 'numbat.py', 'numbat_benchmark.py')}
    original_cases = []
    baseline_hashes = {}
    for name in ('distributed-synthetic.json', 'distributed-scale.json', 'distributed-scale300.json'):
        path = ROOT / 'results' / name
        content = json.loads(path.read_text())
        assert content['complete']
        for source, fingerprint in content['source_sha256'].items():
            assert fingerprint == sources[source], f'Baseline source changed: {source}'
        baseline_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        original_cases.extend(content['cases'])
    result = dict(schema_version=1, complete=False, expected_cases=len(original_cases),
                  synthetic=True, training_seeds=[101, 102], heldout_seeds=[0, 1, 2],
                  config=dict(capacity_power=4, snapshot_capacity=True, close_first=False),
                  python_version=platform.python_version(), source_sha256=sources,
                  baseline_file_sha256=baseline_hashes,
                  assumptions=['Node decisions see local outgoing balances/reservations and received tokens only.',
                    'Reliable exactly-once neighbor messaging, honest nodes, no crashes.',
                    'In-flight commits are not instantaneously atomic; conservation is checked after drain.',
                    'Shared horizons are identical to saved baselines; final score includes in-flight completion.',
                    'Message-cutoff comparison stops admitting searches at a common count, then drains; overshoot varies.',
                    'message_node_ids is a payload proxy, not bytes; Numbat also reports message_capacity_values.',
                    'Parameters frozen on training seeds101/102 before examining heldout cases.'], cases=[])
    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    save()
    for original in original_cases:
        case = {k: v for k, v in original.items() if k != 'methods'}
        case['methods'] = dict(original['methods'])
        case['methods']['numbat'] = run_case(original, 'numbat')
        if not args.skip_message_cutoff:
            cutoff = min(original['methods'][name]['protocol']['messages']
                         for name in ('distributed_dfs', 'distributed_largest_dfs'))
            case['message_cutoff_methods'] = {name: run_case(original, name, cutoff)
                for name in ('distributed_dfs', 'distributed_largest_dfs', 'numbat')}
        result['cases'].append(case)
        save()
        print(f"{len(result['cases'])}/{len(original_cases)} {case['nodes']} {case['scenario']} "
              f"seed={case['seed']} delay={case['max_message_delay']}: "
              f"{case['methods']['numbat']['cleared_percent']:.3f}%", flush=True)
    result['complete'] = True
    save()


if __name__ == '__main__':
    main()
