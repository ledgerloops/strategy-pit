"""Exact timestamped STANDARD transfers from the public Jerboa Sarafu prefix.

This is fixture preparation, not part of any node's protocol. Peer numbering
matches Jerboa's historical readSarafuCsv (including its header registration).
A transfer adds source -> target debt, netting any opposite balance.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from collections import Counter

PUBLIC_SOURCE_COMMIT = '69c7b2cb3cf6946742e676b4c50ff17bebfec059'
PUBLIC_SOURCE_PATH = '__tests__/fixtures/sarafu-50k.csv'
PUBLIC_SOURCE_SHA256 = '785b8f57d3e7e485a678772727bf593aaa90594c833afb7abc3c4d5fb366eebb'


@dataclass(frozen=True)
class Transfer:
    time: int
    source: int
    target: int
    amount: int
    row_number: int = 0


@dataclass(frozen=True)
class TemporalFixture:
    events: tuple[Transfer, ...]
    metadata: dict


def microseconds(delta):
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def load_sarafu(path, *, tick_microseconds=1_000_000, amount_scale=1000):
    """Return time-sorted events, preserving CSV row order for equal timestamps.

    Tick zero is the first STANDARD timestamp. Timestamps have no timezone in
    the input; only differences are used. Floor division coalesces sub-tick
    arrivals, retaining their true timestamp ordering. No amount is rounded.
    """
    if not isinstance(tick_microseconds, int) or tick_microseconds <= 0:
        raise ValueError('tick_microseconds must be a positive integer')
    if not isinstance(amount_scale, int) or amount_scale <= 0:
        raise ValueError('amount_scale must be a positive integer')
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    peers = {'source': 0, 'target': 1}  # Historical converter processes header.
    records, all_times, types = [], [], Counter()
    with path.open(newline='') as handle:
        reader = csv.DictReader(handle)
        required = {'source', 'target', 'timeset', 'weight', 'transfer_subtype'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('Missing required Sarafu CSV columns')
        for row_number, row in enumerate(reader, 2):
            for column in ('source', 'target'):
                peers.setdefault(row[column], len(peers))
            timestamp = datetime.fromisoformat(row['timeset'])
            all_times.append(timestamp)
            types[row['transfer_subtype']] += 1
            if row['transfer_subtype'] != 'STANDARD':
                continue
            amount = Decimal(row['weight']) * amount_scale
            if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
                raise ValueError(f'Row {row_number}: amount is not exact at scale {amount_scale}')
            records.append((timestamp, row_number, peers[row['source']], peers[row['target']], int(amount)))
    records.sort(key=lambda record: (record[0], record[1]))
    origin = records[0][0] if records else None
    events = tuple(Transfer(microseconds(ts-origin)//tick_microseconds, a, b, amount, row)
                   for ts, row, a, b, amount in records)
    graph = net_graph(events)
    metadata = {
        'source_file': path.name, 'source_sha256': digest,
        'source_repository': 'https://github.com/ledgerloops/jerboa',
        'source_commit': PUBLIC_SOURCE_COMMIT if digest == PUBLIC_SOURCE_SHA256 else None,
        'source_path': PUBLIC_SOURCE_PATH if digest == PUBLIC_SOURCE_SHA256 else None,
        'matches_public_50k_fixture': digest == PUBLIC_SOURCE_SHA256,
        'data_rows': len(all_times), 'rows_by_type': dict(sorted(types.items())),
        'csv_chronological': all(a <= b for a, b in zip(all_times, all_times[1:])),
        'file_start': min(all_times).isoformat() if all_times else None,
        'file_end': max(all_times).isoformat() if all_times else None,
        'first_standard': origin.isoformat() if origin else None,
        'last_standard': records[-1][0].isoformat() if records else None,
        'timezone': 'unspecified in source; relative elapsed time only',
        'tick_microseconds': tick_microseconds, 'time_rounding': 'floor elapsed microseconds',
        'tie_order': 'timestamp then original CSV row number', 'amount_scale': amount_scale,
        'standard_events': len(events), 'final_tick': events[-1].time if events else 0,
        'active_peers': len({p for e in events for p in (e.source, e.target)}),
        'gross_transfer_amount_scaled': sum(e.amount for e in events),
        'final_bilateral_edges': len(graph), 'final_bilateral_debt_scaled': sum(graph.values()),
        'transfer_semantics': 'add source-to-target debt; net opposite bilateral balance',
    }
    return TemporalFixture(events, metadata)


def iter_sarafu(path, **kwargs):
    """Yield chronological transfers; sorting requires reading the source first."""
    yield from load_sarafu(path, **kwargs).events


def net_graph(events):
    """Offline audit reference; zero balances close channels, reversals retain them."""
    balances = {}
    for event in events:
        if event.source == event.target or event.amount == 0:
            continue
        forward, reverse = (event.source, event.target), (event.target, event.source)
        value = balances.pop(forward, 0) - balances.pop(reverse, 0) + event.amount
        if value > 0:
            balances[forward] = value
        elif value < 0:
            balances[reverse] = -value
    return balances


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv')
    parser.add_argument('--tick-microseconds', type=int, default=1_000_000)
    parser.add_argument('--compare-debt', help='Historical whitespace-separated source target amount file')
    parser.add_argument('--metadata-out')
    args = parser.parse_args()
    fixture = load_sarafu(args.csv, tick_microseconds=args.tick_microseconds)
    if args.compare_debt:
        expected = {}
        for line in Path(args.compare_debt).read_text().splitlines():
            a, b, amount = line.split()
            scaled = Decimal(amount) * fixture.metadata['amount_scale']
            if scaled != scaled.to_integral_value():
                raise ValueError('Comparison amount is not exact')
            expected[int(a), int(b)] = int(scaled)
        if net_graph(fixture.events) != expected:
            raise ValueError('Final bilateral graph differs from historical fixture')
        fixture.metadata['historical_debt_graph_exact_match'] = True
        fixture.metadata['historical_debt_graph_sha256'] = hashlib.sha256(Path(args.compare_debt).read_bytes()).hexdigest()
    output = json.dumps(fixture.metadata, indent=2) + '\n'
    if args.metadata_out:
        Path(args.metadata_out).write_text(output)
    print(output, end='')


if __name__ == '__main__':
    main()
