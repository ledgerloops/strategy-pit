# Timestamped Sarafu arrival fixture

`temporal_sarafu.py` loads the **public 50k-line prefix**, not the full Sarafu
history, from [Jerboa's pinned fixture](https://github.com/ledgerloops/jerboa/blob/69c7b2cb3cf6946742e676b4c50ff17bebfec059/__tests__/fixtures/sarafu-50k.csv).
It contains 49,999 data rows, including **30,726 STANDARD transfers**, involving
7,154 peers. Their timestamps span **26 January–14 April 2020**, about 79 days.
Disbursements, reclamations, and agent withdrawals are excluded, matching the
historical comparator's selection. This treats payments as hypothetical debt
arrivals; it does not reconstruct actual Sarafu wallet balances or credit limits.

Amounts use exact integer milliunits: every selected amount is representable
without rounding. The historical converter assigns peer numbers while reading
all rows, including its header; this loader preserves that numbering for exact
comparison. It sorts by actual timestamp, breaking ties by original CSV row.
The public prefix is already chronological. Source timestamps contain no timezone;
only elapsed differences are used, without inventing a timezone.

One default simulation tick is one elapsed second, measured from the first
STANDARD transfer. Subsecond timestamps are floored to ticks while retaining
original chronological order. `tick_microseconds=1` preserves full timestamp
precision; larger ticks intentionally compress arrival spacing relative to message
delays and must be included in benchmark reports. No idle period is removed or
replaced by an artificial uniform arrival schedule.

A transfer adds debt from its source to its target, netting any opposite debt.
This matches the historical Jerboa benchmark convention. A nonzero bilateral
balance permits neighbour communication; a zero balance closes that channel, and
a later transfer can reopen it. Reversal can change the debtor. Handling pending
protocol messages and reservations when a channel closes is the simulator's
responsibility, not the fixture loader's. Under the user's strict zero-close rule,
restoration across a fully cleared link requires a separately stated exception
if a headroom protocol needs that channel.

Without any loop clearing, replay produces exactly the historical 13,831-edge
graph, with total debt **7,434,585.295 Sarafu units**. Gross selected transfers total
11,647,216.905; the difference is bilateral netting, not loop clearing. Benchmark
reports should distinguish these quantities. The offline `net_graph` reference
and metadata generation may see all arrivals; node-local protocols must only
receive events as their simulation time arrives.

Reproduce metadata and optionally validate against the historical debt export:

```sh
python experiments/temporal_sarafu.py /path/to/jerboa/__tests__/fixtures/sarafu-50k.csv \
  --compare-debt /tmp/animal-50k-debt.csv \
  --metadata-out experiments/results/temporal-sarafu-fixture.json
python -m unittest discover -s experiments -p 'test_temporal_sarafu.py'
```

The comparison export is optional; remove `--compare-debt` when it is unavailable.
[Checked metadata](results/temporal-sarafu-fixture.json) pins source SHA-256,
repository commit, units, clock, type counts, and the exact comparison result.
The source CSV is not copied into this repository.
