# 001 — Headroom Clearing: reuse cleared capacity without exceeding original debts

**Status:** In progress · **Opened:** 2026-10-10

[Issue tracker](README.md) · [Prototype](../../experiments/headroom.py) · [Tests](../../experiments/test_headroom.py)

## Proposal

Treat each original directed debt as a bounded credit relationship for a fixed clearing epoch. If its initial balance is B, its current balance x may move anywhere within 0 <= x <= B. Clearing creates headroom B - x that a later agreed loop may reuse. The direction cannot reverse, and no original creditor's exposure to that peer can exceed the starting amount.

This is **Headroom Clearing**: greedy loop clearing with reversible choices inside the original balance limits. It could become a node-local extension to Numbat rather than a new permission to create unlimited credit.

## Alice's example

Alice initially owes Bob 7 and Charlie 5, and Doris owes Alice 5. Write her three incident balances as (owed to Bob, owed to Charlie, owed by Doris):

- Initially: (7, 5, 5), signed net debt 7.
- A loop through Doris, Alice and Charlie clears 5: (7, 0, 0), signed net debt 7.
- A later loop comes into Alice through Charlie and leaves through Bob, for amount 3. Restore 3 of Alice's debt to Charlie and reduce her debt to Bob by 3: (4, 3, 0), signed net debt 7.

The Charlie relationship becomes worse than its current zero balance, but remains within its original ceiling of 5. Alice's total outgoing debt stays 7 in the second move. She may be indifferent or prefer the new distribution; Charlie must also accept the restored exposure.

For a complete example, add initial Charlie->Doris 5 and Bob->Charlie 3. The first cycle clears 15 total units, taking total debt from 25 to 10. The second cycle restores Alice->Charlie 3 while reducing Alice->Bob 3 and Bob->Charlie 3, taking total debt from 10 to 7. This is a strictly positive overall reduction.

## Rules to test

1. Fix the original bounds for an epoch. Every original edge remains between zero and its original balance, including while it is temporarily unused by search.
2. Preserve every participant's signed net position after each completed agreement. This is not a promise that each participant's gross outgoing debt decreases at every step.
3. Allow each participant to veto a proposed redistribution according to local preferences. Remaining inside original bounds is an agreed eligibility rule, not automatic consent to any counterparty change.
4. Initially accept only cycles with strictly positive total debt reduction. Neutral moves and locally preferred moves that increase total debt should be separate policies, with separate termination arguments.
5. Make search, validation and consent node-local: participants use their own balances/limits and direct-neighbour messages. A token may accumulate the cost and bottleneck of its traversed path without collecting the entire graph.
6. Reserve capacity and coordinate updates. Reliable-delivery simulation is a first step; crashes, duplicates and replicated bilateral ledgers require additional protocol work.

## Relationship to min-cost flow

For an original edge u->v with current debt x and initial ceiling B, residual actions are:

- Traverse u->v to decrease that debt: capacity x, cost -1 per unit.
- Traverse v->u to restore that debt: capacity B-x, cost +1 per unit.

A residual cycle with negative total cost decreases total debt while preserving all net positions. Its maximum amount is the smallest residual capacity on the cycle. This permits undoing part of an earlier greedy choice to unlock a better combination of clearings.

For a fixed graph, bounds and a common unit, with no extra preference vetoes, the feasible final ledgers are exactly those of the original MCF problem. Thus this changes how a local algorithm can reach the optimum, not the optimum itself: approximately 67.36% on the pinned full Sarafu graph, or 18.92% on the 50k fixture. It is distinct from the unlimited-credit model.

If no negative-cost residual cycle exists, the ledger is globally optimal for this objective. A bounded search failing to find a cycle does not certify that condition. Extra local preferences may rule out some improving cycles and prevent reaching that global optimum.

## Experiments / acceptance criteria

- Reproduce Alice's two moves with exact accounting and peer consent.
- Include a greedy trap where ordinary cancellation leaves an acyclic debt graph but Headroom Clearing finds a mixed decrease/restore cycle and improves it.
- Compare tiny cases with exhaustive search or MCF, using the global solver only as an external reference.
- Compare on the pinned Sarafu and 50k fixtures: reduction, restored amounts, messages, payload, contention and remaining opportunities.
- Separate a fully local run from a diagnostic run initialized with a centralized DFS result.
- Test new transfers and continuously added links with an explicit rule for changing epoch ceilings; do not silently reset ceilings after every clearing or permit old authority to expire unnoticed.
- Assert 0 <= x <= B, conserved signed net positions, strictly decreasing total debt per accepted cycle, and released reservations after completion/abort.

Open questions: how should local preferences rank counterparties; can preferences be shared without revealing the whole ledger; when do starting limits expire; and how should a new transfer or counterparty revocation change the available headroom?

## Progress

- [x] Specify fixed original caps and the residual-cycle objective.
- [x] Reproduce Alice’s example: total debt 10 → 7 after the first clearing.
- [x] Recover from a greedy dead end: remaining debt 3 → 2.
- [x] Implement neighbour-message search with local balances and peer advertisements.
- [x] Benchmark the prototype on the 50k Sarafu fixture with independent replay.
- [ ] Add concurrent initiation and settlement with explicit conflict handling.
- [ ] Add participant preference callbacks and test vetoes.
- [ ] Specify cap updates and invalidation for continuously arriving transfers.

The first prototype serializes search initiators and settlements in the simulator. Nodes choose routes using only local information, but this is not yet a concurrent distributed scheduler. Original bounds are its default consent policy; arbitrary preference algorithms remain future work.

## Measured outcome

[Headroom results](../../experiments/HEADROOM.md): the idea repairs both tiny greedy traps and improves the tested Numbat postpass from 13.50–13.69% to 14.12–14.68%. Cold-start Headroom performs worse. The postpass still assumes serialized initiators and retained channels at zero; it has not established superiority under the newer temporal channel rule.
