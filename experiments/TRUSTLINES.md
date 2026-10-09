# Signed trustlines and the alternating-credit ratchet

This experiment extends obligation clearing to the proposed trustline model: a link has a signed balance and an agreed interval, and a cycle may increase some bilateral debts if it reduces their total. It implements a centralized, exact cycle decision rule and compares it with a global convex-flow oracle. It does not yet extend the asynchronous distributed settlement protocol.

## Accounting model

For peers A and B, let `b_AB` be the balance from A's perspective: positive means B owes A, negative means A owes B. Their views must agree:

```text
b_BA = -b_AB
lower_BA = -upper_AB
upper_BA = -lower_AB
```

A's allowed credit exposure to B supplies `upper_AB`; B's allowed credit exposure to A supplies `-lower_AB`. The experiments assume fixed, agreed bounds containing zero and integer accounting units. They enforce the bounds on every applied move. A line is stored once in canonical endpoint order; zero-balance lines remain part of the network.

The quantity minimized is **gross bilateral debt**:

```text
D = sum over unordered peer pairs of abs(balance)
```

Each node's net position, the sum of its signed peer balances, is preserved. Consequently the sum of positive node net positions (often called net internal debt) is also preserved. Reducing D means reducing or rerouting offsetting obligations, not eliminating the community's net creditor/debtor positions.

## The best amount for a detected cycle

Write a cycle as `A → B → C → A`. Add the same signed amount `delta` to every balance viewed from the source toward the next peer. Each node gains `delta` on one relationship and loses it on the other, so its net position does not change.

If the balances viewed along the cycle are `b_i`, its feasible interval is:

```text
max_i(lower_i - b_i) <= delta <= min_i(upper_i - b_i)
```

The changing part of the objective is:

```text
F(delta) = sum_i abs(b_i + delta)
```

This is convex and piecewise linear. Its slope changes only when a balance crosses zero. The implementation evaluates the feasible endpoints, zero, and feasible zero-crossing values `-b_i`; these suffice for an exact integer optimum. Equivalently, choose a median of `-b_i`, constrained by the feasible interval. Both directions are considered by allowing positive and negative delta.

Ties prefer the smallest absolute move. A plateau produces no transaction. Every accepted move strictly reduces D, so the integer model cannot oscillate forever while merely moving debt around. The network-wide total is only needed for reporting: deciding whether a *given* cycle improves the objective needs that cycle's balances and limits, not unrelated ledgers.

## The ratchet, explicitly

Give A–B a zero initial balance and limits `[-1,+1]`. The four other obligations are:

```text
B owes C 3
C owes A 3
A owes D 3
D owes B 3
```

Their lines permit balances from -3 to +3 in either endpoint's view. Alternate the triangles `A → B → C → A` and `B → A → D → B`:

| Move | Delta in that cycle's orientation | A's balance with B | Total D |
| --- | ---: | ---: | ---: |
| Initial | — | 0 | 12 |
| ABC | +1 | +1 | 11 |
| BAD | +2 | -1 | 7 |
| ABC | +2 | +1 | 3 |
| BAD | +1 | 0 | 0 |

The shared credit line never exceeds one unit in either direction. It repeatedly changes direction, allowing the outer obligations to shrink. All node net positions remain unchanged at every step.

This particular example also has the ordinary debt cycle `B → C → A → D → B`, which clears all 12 directly. The ratchet therefore demonstrates **reuse of bounded credit through short loops**, not a better unrestricted optimum than conventional clearing on this graph.

## A genuine extension of the old feasible set

Now consider only:

```text
A owes B 3
B owes C 3
A–C has balance 0 and permits up to 3 in either direction
```

The old directed debt graph is a chain; it has no debt cycle to clear, even with an optimal search. With the unused trustline, exercising `A → B → C → A` by 3 replaces both debts with **A owing C 3**. D falls from **6 to 3**. A remains net -3, B remains zero, and C remains +3.

This shows why zero-balance trustlines and permission to move away from zero matter. It also shows what is changing economically: C ends up exposed directly to A rather than to B, within C's agreed credit limit.

## Exact reference and cycle search

The oracle represents each canonical balance as the difference between two nonnegative directed flows. Capacities are `upper` and `-lower`, arc costs are +1, and node supplies are the original signed net positions. Positive costs ensure an optimal solution does not maintain unnecessary opposing flows, so its cost equals `sum(abs(balance))` exactly.

For this separable convex objective, absence of **any feasible improving cycle** certifies the global optimum. The small-network implementation exhaustively enumerates simple cycles and recomputes their best amount after each move. First-improvement, best-improvement and seeded random-improvement policies are compared.

This is intentionally expensive: simple-cycle enumeration can grow exponentially. Restricting cycle length or count makes an exhaustive optimality claim invalid. The optimizer records incomplete scans rather than claiming that a truncated search proved optimality.

The model also permits a useful distinction at zero additional headroom. Fixed bounds `[min(0,initial_b), max(0,initial_b)]` have the same global feasible optimum as the original clearing problem, but permit undoing some earlier cancellation while improving other edges. Greedy original DFS only decreases its remaining debts and cannot revisit a consumed edge that way.

## Measured small-network results

The recorded study contains **40 distinct six-node synthetic balance graphs** (20 seeds, two density settings), each tested with three headroom settings and six policy/length combinations: **120 cases and 720 runs**.

For an initial balance `b`, headroom `h` sets:

```text
lower = min(0,b) - h
upper = max(0,b) + h
```

Initial balances and topology are identical across headroom settings. Larger h changes the authorized credit exposure and feasible set; it is not an algorithm-only speed or quality improvement.

Across the same 40 graphs, initial D totals 1,024:

| Additional headroom per direction | Exact final D | Gross debt reduction |
| --- | ---: | ---: |
| 0 | 806 | 21.29% |
| 1 | 671 | 34.47% |
| 5 | 600 | 41.41% |

Both positive-headroom settings improve the exact feasible optimum in 38 of the 40 graphs. These are toy synthetic results, not measured Sarafu trust limits or a recommendation for granting credit.

All **360 unrestricted cycle runs** reached the independently computed exact optimum. The **360 triangle-only runs** missed it in **140 cases**, with a maximum gap of 10 accounting units. The ratchet can help short-loop scheduling, but triangles alone are not sufficient on arbitrary networks.

Every accepted move was independently replayed to check signed balances, limits, strict D reduction, and unchanged node positions. Additional independent tests compare 240 random cycle decisions against every feasible integer delta, and 60 small networks against exhaustive enumeration of feasible balance states. The exact oracle is separately checked against exhaustive tiny-network solutions.

## What this means for distributed DFS

The previous directed search assumption—every useful step reduces its edge's current debt—no longer holds. Search must consider **residual credit capacity** in both directions, including currently zero-balance lines.

For a positive step in a source's balance, the marginal cost is -1 while that balance is below zero, then +1 above zero, until its upper limit. Searching for a feasible negative-marginal-cost cycle is the relevant optimization problem; crossing zero requires recomputing the marginal costs. This connects the trustline proposal directly to convex min-cost circulation.

Permanent dead-end pruning is invalid even on a fixed topology: another cycle can change a balance and reopen residual capacity. Bounded randomized searches can still be a discovery strategy, but failure to find a loop is not an optimality certificate.

The existing neighbor-message simulator has not been silently repurposed for signed trustlines. A distributed extension needs reservations for signed changes, agreement on both endpoint views, a way to aggregate cycle benefit, and recovery/consent semantics. The current bird's-eye model applies the complete cycle atomically as a simulation operation.

## Limits are not the same as everyone's local benefit

Bounds make a move feasible; they do not guarantee that every participant's incident gross exposure decreases. For example, along a five-cycle with source-view balances `[+1,+1,-3,-3,-3]`, a feasible delta +1 reduces total D from 11 to 10. The node between the two positive edges sees its two incident absolute balances rise from 2 in total to 4, while its net position stays zero.

If the agreed limits are standing authorization for that change, the global objective can be used as modeled. If participants require an additional per-cycle benefit condition, it must be part of negotiation and can reject some globally improving moves. Neither interpretation follows from the arithmetic alone.

## Reproduce

With the optional solver environment described in [README.md](README.md):

```sh
experiments/.venv/bin/python -m unittest discover -s experiments -p 'test_trust*.py' -v
experiments/.venv/bin/python experiments/trustline_experiments.py --seeds 20 \
  --output experiments/results/trustlines.json
```

For a standard-library-only run, use `python3` and add `--without-mcf`; solver-specific tests are skipped and the exact-reference comparison is omitted. The generated JSON contains the full input lines, per-run debt traces, fixtures, seeds, versions, source hashes, expected counts, and a completion flag. It overwrites the selected output file.

Files:

- `trustlines.py`: signed bounded network model, exact cycle quotes, application and cycle search.
- `trustline_experiments.py`: fixtures, independent replay, global oracle and seeded comparisons.
- `test_trustlines.py`, `test_trustline_adversarial.py`, `test_trustline_experiments.py`: model, independent exhaustive and experiment tests.
- `results/trustlines.json`: complete measured run.
