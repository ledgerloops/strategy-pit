# Temporal Headroom: first serial experiment

This is a small **serialized, reliable-message prototype**, not the concurrent temporal transport benchmark. Each accepted transfer and each search/settlement finishes before the next starts. Node routing and acceptance use the existing neighbour-message Headroom search; the scheduler provides global serialization. It does not model loss, sleep, delayed posting, stale packets, crash recovery, or settlement races. No concurrent-protocol performance claim follows.

Implementation: [temporal_headroom.py](temporal_headroom.py). Specification: [issue 003](../docs/issues/003-temporal-headroom-semantics.md). Results: [temporal-headroom.json](results/temporal-headroom.json).

## What works

Live pair episodes carry balance `x`, ceiling `B`, generation and revision. Accepted external transfers preserve existing headroom (`B += d`) while the direction stays live. A zero balance discards the ceiling. Reversal closes the old episode and starts a fresh ceiling equal to the opposite debt. A genuinely new transfer can reopen the pair with a new generation; it cannot revive old permission.

The original Alice example is rejected after Alice–Charlie reaches zero: total debt stays 10. Starting Alice–Charlie at six instead leaves one live unit and permits restoration by three; total debt falls from 11 to eight. The seven focused tests cover those cases, cap shifts, zero/reversal/reopening, cancellation-only and cap-reset controls, and a node transport facade that rejects global graph access.

An independent replay reconstructs all posted transfers and completed cycle actions, checking caps, balances, signed net positions, episode generations and revisions. This checks drained serialized execution. Generations are bookkeeping in this first adapter; stale packets and duplicate commits are **not supported or tested**, and their rejection is not a claimed property.

## Bounded exploratory comparison

Four seeds, fixed before running: 101–104. Each input has 16 peers and 240 integer transfers (amounts 1–20), one arrival per tick. Every transfer is followed by exactly one search from its sender, using budget 64 and maximum path length 16. All three treatments share the same input, scheduling rule, seeds and search settings. Search candidates use the inherited local capacity preference. This is exploratory synthetic evidence, not held-out validation or a Sarafu comparison.

| Seed | Cancellation final debt | Headroom final debt | Cap-reset final debt |
| --- | ---: | ---: | ---: |
| 101 | 717 | 729 | 738 |
| 102 | 777 | 685 | 690 |
| 103 | 734 | 629 | 656 |
| 104 | 608 | 541 | 561 |

Headroom improves final debt in three of four seeds and regresses on seed 101. Across these four runs, final debt totals 2,584 versus cancellation's 2,836 (8.9% lower); debt area totals 425,401 versus 437,964 (2.9% lower). These are aggregate sums of this declared sample, not universal expectations. All 12 runs pass independent replay. The cap-reset sensitivity treatment discards headroom after each external transfer; it finishes slightly worse than canonical Headroom in every seed here.

Headroom uses 25,887 search/prepare/commit messages versus cancellation's 32,054 (19.2% fewer). External pair posting is a simulator operation; its negotiation traffic is not modeled or counted. These counts are **not** comparable to the temporal loss/ACK benchmark's physical wire attempts. One search may finish earlier by finding a mixed cycle, so identical search counts do not imply equal message budgets.

Debt area sums the posted ledger after each tick's instantaneous drained work. All 240 transfers post immediately; there are no pending transfers or unfinished settlements at observation points. Completed-cycle reduction, external bilateral netting, restored volume, mixed cycles, closures and reopenings are separate counters in the JSON. Different clearing paths can change later bilateral netting, so cycle reduction alone is not the final-debt ranking.

## Reproduce and next boundary

```sh
python3 -m unittest discover -s experiments -p test_temporal_headroom.py -v
python3 experiments/temporal_headroom.py --output experiments/results/temporal-headroom.json
```

The result pins implementation/dependency hashes and each generated input hash. Integrating these cap transitions into the episode-aware temporal message protocol still requires bilateral agreement, stale-quote checks at preparation, pair reservations and recovery, and explicit loss/sleep tests. This small experiment establishes that useful restoration remains possible under strict zero closure; it does not establish the best realistic node-local algorithm.

## Concrete concurrent integration plan

The integration target is `EpisodeTemporalProtocol` in `temporal_episodes.py`, using its existing reliable delivery, endpoint episode copies, pair posting queue and ordered ledger observer. Do not wrap the serial simulator in a global lock and call that concurrent Headroom.

1. Add a separate residual-search actor and token containing ordered signed arcs `(source, peer, direction, episode, revision, quoted_capacity)`. A debtor can offer reduction from its local positive balance; a creditor can offer restoration from its local negative balance and episode ceiling. No closed episode supplies either candidate. Token aggregation accepts only simple cycles with more reduction than restoration arcs and positive common capacity. Local residual ranking is a separate configuration from this safety mechanism.
2. Reserve each traversed pair through its current debtor owner. A reverse traversal therefore needs a neighbour reservation request/reply, not direct access to the debtor's object. Use exclusive, fail-fast pair reservations initially: a busy pair rejects the proposal and releases earlier reservations through the abort path. This avoids waiting on multiple pair locks, but does not guarantee starvation freedom. Both endpoints check the quoted live generation/revision and consent; the owner records transaction ID, direction, amount and quote. The authoritative available amount is `x` for reduction or `B-x` for restoration, and restoration additionally requires `x>0`.
3. Make external posting's pair-busy predicate account for both reduction and restoration reservations. Queued transfers on unrelated pairs may still post. An episode, its direction and its ceiling cannot change while its prepared pair update is pending. Route observation alone gives no reservation authority; a changed generation/revision aborts at preparation.
4. After every pair is prepared, run an irrevocable commit lap. Each pair owner applies exactly one signed debt mutation under its reservation; no unknown commit can reopen authority. Keep duplicate receipts keyed by transaction ID and episode. Release only the committed pair's reservation and permit its queued external posting. Use the ordered ledger observer immediately per pair mutation, not an invented atomic whole-cycle event. The existing bilateral state-installation adapter remains an explicit simulator assumption until replaced by replicated endpoint agreement.
5. On zero, close economic admission immediately. In-flight commit/abort/receipt traffic is limited to admitted operation IDs; old-generation search or prepare messages cannot proceed over control grace. A later external transfer starts a fresh ceiling. Reverse paths must carry their own quoted generation and revision, rather than reusing the baseline's positive-outgoing quote shortcut.
6. Validate the original blocked Alice example and live restoration example with interleaved delivery, simultaneous opposite-direction reservations, an external reversal waiting behind a reservation, duplicate commits, lost data/ACKs and finite sleeps. Independently replay every pair mutation and report partial settlement exposure before drain. Only then run matched strict-episode cancellation versus Headroom using identical arrivals, fault schedules and cutoffs. Report reservation rejections, pending transfers and transport retries as well as final debt.

These are outstanding implementation steps. The current results above provide no evidence that this concurrent protocol is safe, live or faster.
