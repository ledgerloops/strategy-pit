# Concurrent temporal Headroom prototype

`concurrent_headroom.py` adds signed residual DFS to the frozen strict episode
transport. Multiple roots search and prepare independently. There is no central
initiator queue or globally serialized settlement. It is a small-fixture research
prototype; no benchmark advantage or production safety is claimed.

A live pair permits reduction of its current debt or restoration up to its
current ceiling. Zero closes the pair and expires all headroom. A residual token
carries a path, local capacity observations and episode/revision quotes. A cycle
requires at least three distinct participants and strictly more reducing than
restoring arcs. Its eventual debt reduction is amount times this difference.

Each participant prepares both incident pairs using only its local episode state.
It fails immediately on any existing local pair lock or stale quote. Successful
preparation locks both incidences exclusively and may lower the proposed amount.
An abort unwinds prepared nodes. No participant waits for another transaction's
lock, so lock waiting cannot form a deadlock. Fairness and starvation freedom are
not established; frequent collisions may hurt throughput.

When all nodes have prepared, an irrevocable commit lap visits every participant.
Only the debtor updates each owned edge, including an incoming residual arc that
restores its outgoing debt. Each individual edge change is recorded immediately.
Pairs may update at different times, and intermediate net exposure can occur.
External postings wait while either endpoint retains a pair reservation. A node
releases its own reservations after its owned changes; any later owner still
holds its own lock, preventing premature external posting on that pair.

Both endpoints' episode state is installed by the inherited atomic bilateral
write adapter. This models pair agreement and immediate pair-state visibility;
it is not an implementation of replicated authenticated ledgers. Reliable retry,
ACK deduplication, state-preserving sleep, unlimited tombstones and lack of crash
recovery are inherited. Searches and prepares require exact live episode and
revision; admitted cancellation/commit traffic has restricted control grace.

`restoration=False` provides a cancellation-only control with the **same**
stronger two-incidence locks and search protocol. Compare against this control to
isolate restoration: earlier random DFS reserves only its outgoing edge and is
not a coordination-matched control.

Own tests force the live Alice mixed cycle, prohibit the zero-Alice reverse arc,
exercise restoration-disabled cancellation and run twelve dynamic transfer
seeds with 30% data/ACK loss and random sleeping nodes. Independent tests replay
ordered ledger deltas, caps, episodes and transaction net positions. Independent tests also cover lock/transfer races, forced prepare/commit loss, reordered delivery and actors denied graph access. The exploratory comparison below measures partial exposure with explicit event budgets. Larger-scale validation, crash recovery and held-out workload comparisons remain future work.

## First exploratory matched comparison

`results/concurrent-headroom-synthetic.json` contains **24 completed, audited
runs**: 12 nodes, sparse/community/bursts families, seeds 0/1, clean delivery or
30% data and ACK loss plus sleep. Each configuration runs restoration disabled
and enabled with the same two-incidence locking protocol. Transfers arrive over
500 ticks; searches stop at tick 800, then outstanding work drains. The finite
budget is two million events for each run and drain phase. Source and arrival
hashes are saved. These are exploratory seeds, not held-out validation.

Restoration wins final debt in **7 of 12 pairs**, but loses in five and is worse
in aggregate:

| Summed metric over twelve runs | Cancellation control | Headroom |
| --- | ---: | ---: |
| Final debt, scaled units | 7,358,000 | 7,427,000 |
| Posted-debt area through tick 800 | 5,245,172,000 | 5,333,425,000 |
| Logical messages | 10,262 | 13,604 |
| Data attempts + ACK attempts | 25,000 | 32,672 |
| Partial-settlement exposure area | 19,590,000 | 19,636,000 |
| Unposted transfer volume at tick 800 | 0 | 0 |
| Mixed cycles | 0 | 99 |
| Restored volume | 0 | 586,000 |

Headroom therefore has **0.94% more final debt**, **1.68% more posted-debt area**
and **30.69% more wire attempts** in this small suite. Actual mixed cycles work,
but this implementation is not an improvement overall and should not replace the
cancellation baseline on this evidence. Strict closure, extra search directions,
lock contention and search ordering can all change subsequent opportunities;
these results do not isolate their causal contributions.

Exposure is the sum across transactions of half the L1 norm of each transaction's
currently posted node net changes. Its area integrates only through tick 800;
all runs return to zero exposure after draining. Counting per transaction avoids
hiding two incomplete transactions behind cancelling net deviations. Posted-debt
area can benefit from delayed external input, so horizon unposted volume is
reported alongside it. Data and ACK loss probabilities and sleep schedules match,
but different message activity consumes different transport random draws.

This signed-settlement exposure definition differs from the committed-edge amount measure used by the cancellation-only temporal observer. Compare its values within this matched experiment; do not compare the two exposure totals as if they were the same quantity.
