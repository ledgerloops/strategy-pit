# Does true local turn waiting improve clearing?

**On the completed small synthetic suite, it usually makes this particular
clearing protocol worse.** This is useful negative evidence: a turn primitive
that repairs probe-ordering races in an earlier design does not automatically
improve Numbat's search and reservation protocol.

Unlike the scheduler's `stop_wait` reference, this comparison uses actual
endpoint-local request/grant messages and epochs, implemented in
[local_turns.py](local_turns.py) and integrated by
[temporal_turns.py](temporal_turns.py). All controls use the same lossy,
acknowledged, retrying transport as application messages. Their costs count.
No shared controller decides turn ownership or searches for loops.

## Completed results

Each pair shares arrivals, sleep intervals, seed, search parameters, and message
loss probabilities. Protocol activity changes random-number consumption, so
actual lost envelopes are not identical across protocols.

| Fixture | Matched pairs | Turns leave less / equal / more final debt | Turns have lower / equal / higher debt area | Wire attempts: concurrent → turns |
|---|---:|---:|---:|---:|
| Synthetic changing graphs | 216 | 40 / 11 / 165 | 8 / 0 / 208 | 703,716 → 813,415 |
| First 1,000 chronological Sarafu transfers | 18 | 0 / 18 / 0 | 1 / 1 / 16 | 679,338 → 1,005,954 |
| First 5,000 chronological Sarafu transfers | 18 | 6 / 0 / 12 | 4 / 0 / 14 | 7,000,486 → 7,624,949 |

Wire attempts include data, turn controls, retries, and ACK attempts. Synthetic
turn gating increased their total by **15.6%**; the small Sarafu prefix increased
it by **48.1%**. Aggregated synthetic residual debt rose from 229,620,000 to
245,453,000 scaled units (**6.9%**). These aggregate ratios weight cases by debt
or traffic volume; they are not per-case mean improvements.

Synthetic results by search policy:

| Policy | Pairs | Turns leave less / equal / more final debt |
|---|---:|---:|
| Numbat | 72 | 17 / 3 / 52 |
| Random DFS | 72 | 14 / 4 / 54 |
| Largest-first DFS | 72 | 9 / 4 / 59 |

The negative result is not confined to clean networks: at 30% data/ACK loss,
turns leave less/equal/more final debt in **5/5/62** of 72 pairs. The corresponding
counts are 21/4/47 at zero loss and 14/2/56 at 10% loss. All three graph families
also have more losses than wins.

All **504 completed runs** passed independent chronological per-edge ledger
replay, cycle reconstruction, capacity checks, external-transfer accounting,
and final net-position conservation. Reliable delivery was drained before final
state comparisons. Gate backlogs and pending grants were also empty. This does
not establish crash recovery or Byzantine safety.

The 1,000-transfer prefix has little discriminatory power for final clearing;
its equal final balances are not evidence of equal search quality on the full
Sarafu graph. The 5,000-transfer prefix is less degenerate, and turn gating still
loses overall: six lower versus twelve higher final-debt outcomes, with **8.9%**
more wire attempts. Numbat alone has four wins and two losses on that prefix;
its aggregate residual debt improves by only **0.0082%**, also at **8.9%** more
wire attempts. This narrow positive result does not reverse the much broader
synthetic regression or justify selecting turn gating as the default.

## Exact workload and interpretation

Synthetic inputs: 12/24 nodes, sparse/community/burst arrivals, two seeds,
96/192 continuing transfers over roughly 500 ticks, losses 0/10/30% for both
payloads and ACKs, sleeps absent/present, all three search policies, and both
transports. Searches stop at tick 800, then existing work drains. There are
432 runs (216 matched pairs).

Sarafu inputs: first 1,000 chronological STANDARD transfers from the pinned
public 50k-row CSV, timestamp gaps uniformly compressed into 500 arrival ticks,
then 300 further search ticks. Two seeds and clean / 10%-loss-with-sleep /
30%-loss-with-sleep conditions, all three policies, and both transports yield
36 runs. The 5,000-transfer prefix uses the same seeds/fault conditions,
1,000 arrival ticks and a 1,300-tick search horizon, adding another 36 runs.
This accelerated replay does not measure real-time throughput.

Shared parameters: retransmit 20 ticks, maximum delivery delay 5, local retry
interval 50, maximum search hops 32, search budget 96. Turn batch size is 8.
The horizon is shared, but post-drain completion times can differ. Results
record both timestamps and backlogs. Debt area measures **posted** obligations:
delayed external posting can reduce that area mechanically, so interpret it
alongside pending transfers and final audited results.

The simulator retains endpoint state through sleep and pair turn epochs through
zero-balance closure and reopening. Historical communication identities remain
available for finishing control traffic. Arbitrary permanent loss, permanent
sleep, state-losing crashes, and strict immediate transport destruction are not
successful cases hidden by the benchmark: budget exhaustion reports incomplete.

## Artifacts and reproduction

- [Synthetic results](results/temporal-turn-synthetic.json)
- [1,000-transfer results](results/temporal-turn-sarafu1000.json)
- [5,000-transfer results](results/temporal-turn-sarafu5000.json)
- [Harness](temporal_turn_benchmark.py)
- [Protocol description and tests](LOCAL-TURNS.md)

Each result includes exact source hashes, arrival and sleep hashes, horizon and
drained metrics, gate backlog, parameters, independent audit outcomes, and a
batch completion marker. The harness checks source hashes during the batch. The 216 synthetic and 18
Sarafu concurrent reruns exactly reproduce the baseline benchmark's independent
audits and every final metric, providing a cross-harness consistency check.

```sh
PYTHONPATH=experiments python experiments/temporal_turn_benchmark.py \
  --suite synthetic --output experiments/results/temporal-turn-synthetic.json
PYTHONPATH=experiments python experiments/temporal_turn_benchmark.py \
  --suite sarafu --csv /path/to/sarafu-50k.csv --limit 1000 \
  --output experiments/results/temporal-turn-sarafu1000.json
```
