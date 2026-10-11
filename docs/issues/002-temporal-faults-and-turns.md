# 002 — Changing graphs, unreliable messages and neighbour turns

**Status:** In progress · **Opened:** 2026-10-10

[Issue tracker](README.md)

## Goal

Compare node-local clearing under continuously arriving transactions, dropped messages and sleeping peers. Use real Sarafu timestamps as well as controllable synthetic scenarios. Determine whether local turn-taking improves discovery and settlement rather than assuming it does.

## Model decisions to make explicit

- A transaction establishes a peer relationship. A zero balance closes it to new economic search. Report the control-message grace used to finish already-started work; that is not permission to reuse a zero balance for Headroom.
- External transfers bilaterally net and may reverse the direction of a debt. A transfer waiting for an in-flight reservation or sleeping peer is pending input, not cleared debt.
- Sleep retains state; it is not a crash. Acknowledgements, retransmission and duplicate suppression implement eventual application delivery under the tested bounded outages. Permanent loss must remain visibly incomplete.
- Commit is staged. Replay individual ledger events when transfers interleave with a partially committed cycle; an atomic-at-completion replay would misrepresent their ordering.
- Separate concurrent transport, a scheduler's stop-and-wait reference, and genuine endpoint-local turn ownership. The latter needs explicit requests, grants, epochs and bounded batches.
- Headroom's original limits need an epoch/update policy before integration with new transactions. Strict closure at zero can remove a useful restoration path.

## Progress

- [x] Parse real Sarafu timestamps and exactly reproduce the historical final ledger.
- [x] Implement loss, ACK loss, retries, duplicate suppression and bounded sleep.
- [x] Test receipt-once application and local decision access independently.
- [x] Implement an endpoint-local turn gate with reordered/duplicate-message tests.
- [x] Complete synthetic and 1,000/5,000-transfer timestamped comparative matrices.
- [x] Complete larger full-prefix followups within declared event budgets (six strict-admission cases complete; multi-seed replication next).
- [x] Integrate and benchmark the local turn gate (504 audited runs across synthetic, 1,000-transfer and 5,000-transfer comparisons).
- [x] Compare outstanding-debt area, posting delay, clearing and all message attempts.
- [x] Integrate Headroom with explicit changing-cap and reopening semantics (concurrent small-fixture prototype; performance does not yet justify promotion).
- [ ] Bound long-running protocol memory without allowing old packets to revive stale transactions.

## Evidence

[Timestamped fixture](../../experiments/TEMPORAL-SARAFU.md) · [Temporal protocol](../../experiments/temporal_protocol.py) · [Local turn gate](../../experiments/LOCAL-TURNS.md)

No single current experiment establishes the best algorithm across workloads, fairness policies and failure rates. Retain negative results and distinguish safety in the tested model from progress guarantees.
