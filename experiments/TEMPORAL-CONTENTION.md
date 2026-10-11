# Temporal contention: observations and a prospective experiment

## What the existing full-prefix results establish

All rows below replay the same 30,726 timestamped STANDARD transfers. Clocks are
compressed arrival durations; results include draining work after the search
horizon. These are the original temporal channel semantics, before strict episode
admission. They diagnose a possible weakness; they do not establish the behavior
of the stricter protocol.

| Arrival ticks / seed | Method | Proposals | Aborts | Abort fraction | Completed cycles | Logical messages / cycle |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 500 / 0 | Random DFS | 11,356 | 9,572 | 84.29% | 1,784 | 538.1 |
| 500 / 0 | Numbat | 12,215 | 11,063 | 90.57% | 1,152 | 853.4 |
| 2,000 / 0 | Random DFS | 15,945 | 13,819 | 86.67% | 2,126 | 905.2 |
| 2,000 / 0 | Numbat | 15,199 | 13,701 | 90.14% | 1,498 | 1,266.2 |
| 4,000 / 0 | Random DFS | 18,745 | 16,464 | 87.83% | 2,281 | 1,404.4 |
| 4,000 / 0 | Numbat | 19,222 | 17,451 | 90.79% | 1,771 | 1,808.6 |
| 2,000 / 1 | Random DFS | 18,371 | 16,219 | 88.29% | 2,152 | 894.0 |
| 2,000 / 1 | Numbat | 14,900 | 13,375 | 89.77% | 1,525 | 1,240.0 |

Largest-first aborts 94.78–95.72% of proposals in these four configurations.
Random DFS completes more cycles and has the lowest final debt in each paired
configuration. Cycle count alone is not the objective: cycle lengths, amounts,
and subsequent bilateral netting differ. Message counts above are logical sends,
not physical data-plus-ACK attempts.

The existing `aborted` counter increments when a participant has no available
capacity. It does **not** distinguish a reservation conflict from debt that was
already cleared or reversed. Calling all these aborts contention would be wrong.
New episode rejections are another separate reason. Search steps account for
79.86–89.70% of messages for random/Numbat here, so reducing preparation abort
messages alone cannot remove most traffic.

Sources: `results/temporal-sarafu-full-10m.json`,
`results/temporal-sarafu-clock-500.json`,
`results/temporal-sarafu-clock-4000.json`, and
`results/temporal-sarafu-clock-2000-seed1.json`. All twelve completed baseline
rows pass the independent ledger audit. Censored two-million-event rows are
excluded, not treated as completions.

## One proposed local policy: reservation-triggered initiation backoff

This policy changes when an actor starts **its own** search. It never postpones
incoming prepare, abort, finish or commit processing, and never inspects another
actor, global failure count or graph.

Each actor keeps a level initially zero and a local `resume_at` time. When an
otherwise episode-valid incoming prepare fails specifically because the actor's
positive outgoing debt is entirely reserved, increment the level (maximum 3) and
set `resume_at = now + retry_interval * 2**level`. Repeated conflicts can extend
the pause. An actual local commit reduces the level by one. Ordinary periodic
wake events keep their existing schedule and random jitter; during the pause
they simply do not initiate a new search. Level zero imposes no pause. No
additional random draw or parameter fitting is used.

This targets reservation pressure observed directly at an actor. It cannot stop
remote initiators from searching through that actor, so it may be ineffective.
A stale/closed episode, zero outgoing debt, or changed direction must not count
as reservation contention. The receiving actor may also be a poor place to
throttle, and fewer searches can mean less clearing. These are reasons to test,
not reasons to promote the policy.

## Preregistered training gate (before running the policy)

Freeze source hashes after the strict episode API is stable. Compare the policy
against an otherwise identical instrumented baseline, for both random DFS and
Numbat. Use synthetic `sparse`, `community` and `bursts`, 12 and 24 nodes,
seeds **101 and 102**, 500 arrival ticks, search horizon 800, search budget 64,
maximum path 64, retry interval 50, maximum message delay 3 and retransmit 20.
Transport scenarios are clean/no-sleep and independent data/ACK loss 0.1 with
the existing seeded sleep schedule. This is 96 runs including controls. Each
run and its drain have a separate 2,000,000-event bound. Budget exhaustion is
incomplete and fails the promotion gate; do not enlarge budgets after seeing
which method fails.

Record independent accounting, final debt, common-horizon posted-debt area,
unposted transfer exposure, partial-commit exposure, physical attempts,
reservation-specific failures, stale/depleted prepare failures, suppressed wakes,
and all pending work. Zero-state and locality tests must pass first.

For either base method, promote only if every paired run completes and audits,
aggregate final debt is no higher than its baseline, aggregate physical attempts
fall by at least 5%, aggregate unposted amount-time and partial-commit exposure
do not increase, and at most one quarter of individual runs have higher final
debt. Report each method's gate independently and retain failures. Debt area is
secondary because delayed posting can make it look better.

Only a passing method proceeds unchanged to held-out seeds 201/202 and a
5,000-transfer real Sarafu prefix. No held-out results choose parameters. A
failure leads to diagnosis or a newly specified hypothesis, not an unreported
sweep over caps or multipliers.
