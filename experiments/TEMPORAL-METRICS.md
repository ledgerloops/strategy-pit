# Reading temporal clearing results

A changing graph needs separate measures of **final debt reduction**, **gross
cycle clearing**, and **when obligations and settlements are posted**. Gross
clearing divided by a static debt baseline can exceed a static optimum without
beating that optimum on the same problem.

## Exact debt accounting

Start with an empty graph and a fixed set of external transfers. Let:

- `T` be the sum of transferred amounts, counting each transfer once.
- `B0` be debt removed by bilateral netting when no multilateral clearing occurs.
- `D0 = T - B0` be that no-clearing final debt.
- `B` be bilateral netting actually realized with the clearing algorithm running.
- `C` be gross cycle clearing: the sum of amounts removed on every committed leg.
- `D = T - B - C` be final debt after all transfers and settlements drain.

Then the exact identity is:

```text
final debt improvement = D0 - D = C - (B0 - B)
```

`B0 - B` is the offset from displaced bilateral netting. An early clearing can
remove debt that a later opposite transfer would otherwise cancel. Therefore
`C / D0` and `(D0 - D) / D0` answer different questions. Report both explicitly;
do not label the former simply “percentage cleared” in a temporal comparison.
Bilateral netting here counts the reduction in total directed debt, so cancellation
of two opposite amounts `x` contributes `2x` to `B`.

### Full-prefix Numbat example

The completed clean seed-0 Numbat row in
[temporal-sarafu-full-10m.json](results/temporal-sarafu-full-10m.json) processes all
30,726 STANDARD transfers in the public 50k-line fixture. Amounts below are in
Sarafu (the JSON stores thousandths):

| Quantity | Amount |
| --- | ---: |
| External transfers `T` | 11,647,216.905 |
| Baseline bilateral netting `B0` | 4,212,631.610 |
| Baseline final debt `D0` | 7,434,585.295 |
| Actual bilateral netting `B` | 3,827,383.610 |
| Gross cycle clearing `C` | 1,427,025.000 |
| Final debt `D` | 6,392,808.295 |
| Displaced bilateral netting `B0 - B` | 385,248.000 |
| Final improvement `D0 - D` | 1,041,777.000 |

The final improvement is **14.012577%** of baseline debt. Gross cycle clearing is
**19.194413%** of baseline debt, or **12.252069%** of external transfer volume.
These are three distinct metrics.

Historical Jerboa's **15.373238%** fresh result and MCF's approximately **18.92%**
are static cancellation results on the final aggregate graph. They are not a
matched temporal experiment. In particular, Numbat's gross 19.194413% is **not**
evidence of outperforming MCF. An online settlement can also leave a final pair
balance larger than, or reversed relative to, that pair's aggregate no-clearing
balance. Such a result lies outside the static cancellation-only feasible set;
that static MCF optimum is not a general bound on temporal final debt reduction.
Compare algorithms on the same arrivals, clock, deadline, and accounting rules.
A separate [gross-arrival MCF relaxation](TEMPORAL-REFERENCE.md) supplies a valid
optimistic bound for final debt while explicitly ignoring chronology.

## Common deadline and final drain

The full-prefix example has a common search deadline at tick 2,300. At that time
it still has one unposted transfer, 55 reservations, and 9,275 transport envelopes.
Existing work drains to tick 2,673. The final debt above includes those additional
373 ticks, with new searches disabled. It is a final-quality result, not the amount
of completed work by the common deadline.

Posted-debt area integrates the simulator's actual ledger to a common horizon.
Two effects must accompany this number:

1. An external transfer delayed by sleep or reservations does not yet contribute
   to posted debt. A smaller area can therefore reflect delayed posting.
2. A settlement commits one edge at a time. Debt falls before every participant's
   balancing leg has committed. Net positions are preserved after the full cycle,
   but can differ temporarily during its commit traversal.

Pending counts identify unfinished work but do not measure its financial amount
or duration. In the example, 55 reservations need not mean 55 partly committed
settlements; some can still be preparing. Do not infer settlement exposure from
reservation count alone. Report horizon debt and backlog alongside final debt,
drain duration, and the measures below.

## Additional observable measurements

These measurements belong in an independent observer, not in routing decisions.
Existing completed-run ledger records contain the information needed. The separate [observer](temporal_metrics.py) and
[diagnostic wrapper](temporal_metrics_benchmark.py) calculate the core measures
without changing frozen protocol sources or overwriting published runs. Additional
distributions below remain useful extensions.

### Requested but unposted transfers

For transfer `i`, let its requested time be `r_i`, posting time `p_i`, and amount
`a_i`. At horizon `H`, define the outstanding requested amount:

```text
U(H) = sum a_i for transfers with r_i <= H < p_i
```

Its amount-time exposure through the horizon is:

```text
integral U(t) dt = sum a_i * max(0, min(p_i, H) - r_i)
```

For a transfer still unposted at the observation end, use that end in place of
`p_i` and mark the observation censored. Calculate both the common-horizon area
and the full-drain area; report peak amount, horizon amount, maximum posting
delay, and ordinary and amount-weighted mean delay. This exposure measures delayed
external work. It should remain a separate metric: it is not necessarily debt
that would be present if posted immediately, because reciprocal transfers net.

Implementation: match external arrivals to ledger transfer postings in each
unordered pair's FIFO queue. Preserve row identity for equal-valued transfers;
check direction, amount and requested time. Use integer amounts and ordered time
deltas, then cross-check posted count and total transfer amount against the
existing audit. A full-drain amount-weighted delay is the area divided by `T`.

### Partly committed settlements

For transaction `j`, accumulate the absolute amounts removed by its committed
legs. Include this amount in `K(t)` while at least one leg has committed but the
cycle has not yet received its last leg commit. Remove its whole contribution
when the final leg commits. Sum across transactions, keeping transactions separate
so unrelated unsettled legs cannot cancel each other's reported exposure.

Report the area under `K(t)` to the common horizon and through drain, its peak and
horizon amount, first-to-last-leg durations, and transaction counts still partly
committed at the horizon. These figures describe how much already credited debt
reduction is waiting for the remaining balancing legs. They are not a monetary
loss estimate or a proof of atomic settlement. Financial balancing at the last
leg and later application completion/acknowledgement are separate milestones;
report their lag separately if useful.

Implementation: group `commit` ledger records by `txid`; independently verify the
existing simple-cycle/equal-amount invariants, order by `(time, order)`, and derive
the final leg from a completed audited trace. On incomplete observations, do not
invent future completion; retain known exposure to the observation end and mark
it censored. Same-tick commits contribute no artificial elapsed time. Check that
all completed settlements release their exposure and that full-drain `K` is zero.
An optional additional check tracks each node's temporary position difference
from the graph formed by posted external transfers alone. Keep that aggregated
position difference separate because overlapping partial cycles can mask each
other there.

Adding `K` back to posted debt can illustrate delayed credit for unfinished cycles,
but it does **not** reconstruct a valid alternative ledger: a new transfer may
already have posted on an earlier committed edge. Avoid a combined “corrected
score” that hides this distinction.

### Replay checks for the new observer

Use hand-calculated traces with delayed reciprocal transfers; unequal transfer
amounts; multiple identical arrivals on one pair; three-leg commits at distinct
and identical ticks; overlapping partial cycles; and a horizon cutting through a
settlement. Include an external transfer posted between two legs. Verify amounts,
areas, peak values, final zero exposure, and the exact `D0 - D = C - (B0 - B)`
identity. Explicitly distinguish an incomplete observation from a failed audit.

## First exposure diagnostic

[temporal-metrics-diagnostic.json](results/temporal-metrics-diagnostic.json)
contains 40 completed diagnostic runs. This is a small measurement check, not a
new benchmark-wide ranking. The observer uses the last actual leg commit as the
financial completion time; unfinished traces are explicitly censored. Its
[hand-calculated tests](test_temporal_metrics.py) cover amount-weighted delays,
staged commits, and incomplete observations.

One community case (seed 101, clean transport) illustrates why separate measures
matter. These are the exact scaled amounts and amount-ticks stored in the JSON:

| Measure | FIFO turn transport | Priority turn transport |
| --- | ---: | ---: |
| Posted-debt area to horizon | 207,365,000 | 206,586,000 |
| Requested-unposted amount-time to horizon | 390,000 | 508,000 |
| Unposted amount at horizon | 10,000 | 35,000 |
| Partly committed amount-time to horizon | 1,322,000 | 1,299,000 |
| Final debt after drain | 548,000 | 548,000 |
| Data-plus-ACK attempts | 1,376 | 1,436 |

Priority has lower posted-debt area and slightly lower partial-commit exposure,
but more amount-weighted posting delay, a larger horizon backlog, and more wire
attempts; both finish with the same debt. This does not prove that posting delay
caused the debt-area difference. It demonstrates that a lower debt-area score can
coexist with worse delayed-input exposure, which a single combined score would
hide. These runs are distinct from the larger held-out priority matrix below.

## Transport priority results and claim limits

[temporal-priority-training.json](results/temporal-priority-training.json) has
separate training seeds 101/102 and held-out seeds 0/1. Its held-out totals show
priority turn transport versus FIFO turn transport:

- Posted-debt area is **0.9478% lower**.
- Final debt is **0.6800% lower**.
- Data-plus-ACK attempts are **2.5569% higher**.
- Total unweighted posting delay is **1.6877% lower**; no external transfers remain
  unposted at the common horizon, versus one for FIFO.

This supports a modest improvement over FIFO in that small matrix. Priority still
has **4.3315% higher debt area**, **5.6546% higher final debt**, and **17.0220% more
wire attempts** than concurrent transport. It is not a general winner. New
amount-time and partial-settlement measurements can strengthen interpretation;
the existing counters cannot recover those areas retrospectively without traces
or an otherwise identical rerun. Count both data and ACK attempts, including turn
control traffic. Payload `repr` byte counts are an encoding-dependent proxy, not
measured network bandwidth.

The existing audit establishes capacity-valid individual commits, complete
balanced cycles, applied external transfers, and final ledger/position agreement.
It does not by itself prove participant consent, crash recovery, or routing
locality; those require their own protocol checks and assumptions. Preserve this
scope when describing successful audits.
