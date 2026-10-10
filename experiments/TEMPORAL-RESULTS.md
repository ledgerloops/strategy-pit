# Changing graphs, dropped messages, and sleeping nodes

These experiments compare Numbat, randomized local DFS, and largest-first local
DFS on the same timed arrivals. They test cancellation-only clearing, **not
headroom restoration**. Search decisions use node-local state and neighbour
messages. The event scheduler and independent auditor see the whole run solely
for delivery and measurement.

## Completed synthetic matrix

[temporal-synthetic.json](results/temporal-synthetic.json) contains **432 completed,
independently audited runs**: sparse, community, and burst streams; 12 or 24 nodes;
two seeds; 0%, 10%, or 30% data **and ACK** loss; no sleep or two randomly placed
20–100 tick sleep periods for about 60% of nodes; three search algorithms; two
transport modes. Every stream has 8 transfers per node and includes reciprocal
transfers, new neighbours, balance reversals, and possible channel reopening.
Arrivals span about 500 ticks; searches stop at tick 800, then existing work drains.

For the ordinary concurrent transport, aggregate results over the same 72 cases
per algorithm are:

| Algorithm | Posted debt area (million units × ticks; lower is better) | Final debt after drain (units; lower is better) | Logical messages | Data attempts |
| --- | ---: | ---: | ---: | ---: |
| Numbat | 52.104 | 75,460 | 92,216 | 127,871 |
| Random local DFS | 52.940 | 76,734 | 93,678 | 130,187 |
| Largest-first local DFS | 52.955 | 77,426 | 92,670 | 128,315 |

Numbat's aggregate posted debt area is **1.58% lower than random DFS**, and its
final debt is **1.66% lower**. Numbat wins debt area in 29/72 cases, random in 18,
and largest-first in 25. This supports Numbat on this particular small synthetic
matrix, not a universal winner. Increasing loss degrades all three: retries preserve
settlement correctness, but consume the finite search window.

The `stop_wait` transport is a **central scheduler's half-duplex pair queue**,
not the old animal protocol's node-negotiated turn-taking. It reduces logical
traffic but is generally slower to clear. Aggregate posted debt areas are 56.840,
56.509, and 57.842 million units × ticks for Numbat, random, and largest-first;
random leads that metric. These results must not be labelled a test of the actual
historical turn-waiting algorithm. A separate local-turn experiment can reuse the
same fixtures and audit.

## Sarafu timestamp replay

[temporal-sarafu.json](results/temporal-sarafu.json) contains **18 completed runs**
of the first 1,000 chronological STANDARD transfers from the public 50k-line
fixture, preserving the actual relative timestamp gaps. This is roughly four
days compressed into 500 ticks: **one tick = 694,095,258 microseconds**. Two seeds
and clean / 10%-loss-plus-sleep / 30%-loss-plus-sleep conditions use concurrent
transport and all three algorithms.

That small prefix gives effectively no algorithm separation: all three have the
same final debt after drain. It is a transport/replay smoke test, not evidence
that Numbat beats the historical Jerboa/Jaribu clearing benchmarks. Larger prefix
experiments are separately named so their selection, clock and status cannot be
confused with this completed result.

[temporal-sarafu-5000.json](results/temporal-sarafu-5000.json) extends this to the
first **5,000 STANDARD transfers**, about 19 days compressed into 500 ticks
(one tick = 3,300,842,176 microseconds). All 18 runs complete and pass the audit.
Over six matched conditions per algorithm, Numbat has aggregate final debt
6,959,637 units, random 6,960,037, and largest-first 6,960,515. Numbat's aggregate
posted debt area is only **0.13% below random**. These small differences do not
justify a broad superiority claim; largest-first slightly beats Numbat in the
clean seed-0 case. All transfers are posted by the shared horizon, but final
draining takes as many as 1,669 additional ticks.

The first full-prefix attempt,
[temporal-sarafu-full.json](results/temporal-sarafu-full.json), exhausted its
2-million-event budget on all four recorded cases before completing the common
horizon. It is explicitly censored; its partial figures are not a ranking.
`temporal_scale_benchmark.py` provides a resumable follow-up with 10 million
events per phase, three clean seed-0 algorithms and all 30,726 STANDARD transfers
compressed into 2,000 ticks. Its output records completion per algorithm; consult
that status before interpreting any score.

## What the audit proves and what the metrics mean

The independent auditor replays **each actual edge commit**, not just complete
cycles. Commits happen in stages, and a later incoming transfer can legitimately
post to an already committed edge before the rest of its cycle finishes. The
audit verifies each committed amount against the balance then available, verifies
all legs form one simple cycle with an equal amount, matches declared cycle
completions, checks every external transfer arrived no earlier than requested and
in bilateral FIFO order, and compares the final graph and every node's net
position. All completed runs drain envelopes, reservations, and transfer queues.

Debt area integrates actual posted bilateral debt to the **common tick-800
horizon**, including individual commit times. Sleeping endpoints or reservations
can delay external posting. Consequently, a lower posted-debt area alone can
reward delayed transfers; it must be read with transfer delay and pending counts.
Concurrent runs have no unposted transfers at the horizon. Mean posting delays
are 6.17, 6.65, and 5.74 ticks for Numbat, random, and largest-first. The stop-wait
matrix has respectively 25, 5, and 3 total transfers still queued at the horizon;
all are subsequently posted during drain. Final debt is measured after drain,
which can extend beyond the common search deadline, and therefore is not a
fixed-time throughput score.

Data attempts include retransmissions; logical messages do not. ACK attempts and
losses are separately reported in each row. Sleep preserves node state; this
models temporary unavailability, not crashes or malicious behaviour. Zero economic
balance closes the link for new forward searches, while historical pair identity
provides an explicitly modelled control-message grace period to complete in-flight
work. This is not an implementation of immediate physical disconnection at zero.

Every file records algorithm-source SHA-256 values, input hashes, parameters,
completion status and pending work. A source change stops the runner instead of
silently mixing versions. The same inputs and sleep schedules are reused across
algorithms; message randomness is reproducible but activity-dependent, so the exact
lost-message pattern differs as the algorithms send different messages. Two seeds
are an exploratory comparison, not a statistical confidence interval.

## Reproduction

```sh
python experiments/temporal_benchmark.py --suite smoke \
  --output experiments/results/temporal-smoke.json
python experiments/temporal_benchmark.py --suite synthetic \
  --output experiments/results/temporal-synthetic.json
python experiments/temporal_benchmark.py --suite sarafu \
  --csv /path/to/jerboa/__tests__/fixtures/sarafu-50k.csv \
  --limit 1000 --arrival-ticks 500 \
  --output experiments/results/temporal-sarafu.json
python -m unittest discover -s experiments -p 'test_temporal*.py'
```

`--limit 0` selects all STANDARD transfers in this public prefix, not the complete
Sarafu dataset. Each run has an explicit event budget; exhaustion is saved as
`complete: false`, never counted as a completed clearing score. Output checkpoints
are replaced atomically after every case so interrupted campaigns retain completed
work.
