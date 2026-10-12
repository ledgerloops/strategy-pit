# One-unit retention: a prospective Headroom preference

**Documented research baseline, not an app feature.** This note combines a proposed node-local preference with an implemented offline min-cost-flow reference. The reference is not a distributed algorithm or a network benchmark. It does not change any frozen replication source or result.

## Relationship to comfort zones

Product development now focuses on [shared comfort zones and their hashlock implementation](../app/COMFORT.md). Headroom remains a useful comparison: it constrains each original directed balance to `[0,B]` and seeks lower total debt. This retention variant raises the lower bound to one integer unit to keep indebted relationships open. Comfort clearing instead uses mutually chosen credit limits and preferred intervals, and can increase total debt while reducing discomfort.

Trustline limits can express Headroom-style bounds, but the current conservative comfort policy is not equivalent to Headroom’s debt-reduction objective. These experiments are retained to document that tradeoff and the negative examples below, not as a pending requirement for the app. No dynamic retention strategy or unattended execution is implemented here.

A peer could decline clearing that would extinguish its last integer debt unit. Call this **one-unit retention**. On every live directed pair, ordinary clearing would leave `x >= 1` in the dataset's agreed integer unit, while restoration would remain limited by the current episode ceiling `B`. Real external transfers could still close or reverse a pair normally. The economic channel would therefore remain open because real debt remains, under the existing exact zero-close rule.

This may preserve useful Headroom routes, but the extra final debt is **not bounded by one unit per relationship**. Conservation can amplify the cost dramatically. That distinction must be settled before treating this as an inexpensive improvement.

## Local rule and invariants

For a live episode with integer `0 < x <= B`:

- Reduction capacity becomes `max(0, x - 1)`.
- Restoration capacity remains `B - x`, available only while the episode is live.
- Both endpoints must agree to the preference and still approve each proposal. A creditor who wants the relationship extinguished may refuse retention or revoke unused headroom; the algorithm cannot infer that perpetual debt is desirable.
- External transfers retain the canonical cap update. A live same-direction transfer changes `x` and `B` by the same signed amount; zero discards the cap, and reversal opens a new opposite episode at `x = B`. Transfers cannot be rejected merely to preserve a useful route.

Completed signed cycle updates still preserve each node's net position, and the strictly positive total debt-reduction criterion still applies. Floors narrow the set of allowable moves; they do not create a new balance or permit restoration after closure. A unit-capacity edge (`x = B = 1`) cannot participate in either residual direction until a genuine external transfer changes its state.

The unit must be declared prospectively. On the existing Sarafu integer scale, one unit represents 0.001 of the source monetary unit. Changing the precision to make the floor look smaller changes the experiment. With a larger arbitrary floor or fractional transfers, extra rules would be needed when an external posting leaves a positive balance below the floor; the smallest common integer unit avoids that ambiguity.

Preparing a reduction must reserve against `x - 1`, including concurrent reservations, rather than reserve against `x` and alter the amount late in commit. The current exclusive pair-lock substrate could enforce that locally. Restoration and external posting still need the same episode freshness, pair locking and staged-settlement checks as ordinary Headroom.

## A real opportunity, with a visible cost

In the original Alice example, Alice–Charlie, Charlie–Doris and Doris–Alice each start at five. Clearing only four units retains all three relationships at one. The Charlie→Alice→Bob→Charlie residual cycle can then restore Alice–Charlie while reducing the other two obligations. Because Bob–Charlie starts at three, its one-unit floor limits that second cycle to two units.

The resulting balances are Alice–Bob five, Alice–Charlie three, Bob–Charlie one, Charlie–Doris one and Doris–Alice one: total eleven. Without floors, the first loop could clear five and leave total ten, although the Alice–Charlie restoration route would then close. Thus preserving the formerly useful route does **not** even improve this motivating example. Further available moves would need to be evaluated under the same floors; a simple residual-graph check shows no further improving cycle here.

## Counterexample to the “one unit per edge” cost bound

Create ten two-edge branches `u → w_i → v`, each edge owing one unit. Add one return path from `v` to `u` with ten edges, each owing ten units. Every node's signed net position is zero. There are 30 relationships and total debt 120.

Without floors, the ten cycles can clear completely. With a one-unit floor, every branch edge is frozen at one. Conservation requires ten units along every edge of the shared return path, so **none of the 120 units can clear**. The gap is 120, not the proposed 30-unit bound.

More generally, with `k` branches and a return path of length `L`, there are `2k + L` relationships and retained debt `2k + kL`. The ratio of the gap to the sum of one-unit floors is unbounded as `k` and `L` grow. The issue is not a numerical artifact: a frozen low-capacity segment can force much larger debt to remain elsewhere in the network.

Even a uniform one-unit triangle is a complete failure case: ordinary cancellation clears everything, while retention clears nothing. Future external transfers may eventually create capacity or close channels, but that is an assumption about future inputs, not a guarantee supplied by the strategy.

## A weaker offline bound, with explicit qualifications

For a **fixed** graph with `n` nodes and `m` live directed debts, assume there is a feasible reference ledger with every debt at least `δ`, the same net positions, and the same ceilings. Compare the minimum total debt with lower bounds zero against the minimum with lower bounds `δ`, allowing all original edges in the offline optimization. The difference between these two optima is at most `n × m × δ`, rather than `m × δ`.

To see this, take a zero-floor optimum and the reference ledger. Their signed difference is a circulation; direct each residual difference toward the reference and decompose it into simple cycles of length at most `n`. For each edge below its floor, select enough of these cycle components to fill its remaining deficit, at most `δ`. Selecting a component moves every affected balance toward the feasible reference, so it cannot violate ceilings or make an already adequate balance fall below its floor. The total selected cycle weight is at most `mδ`; its total debt increase is at most `n` times that weight. The resulting ledger is floor-feasible, so its cost bounds the floor optimum.

This is an existence bound for offline feasible ledgers. It neither supplies node-local routes nor guarantees that the clearing heuristic finds that ledger. It also does not bound the gap between two evolving runs whose episode closures, later ceilings, timing and future transfers differ. The factor `n` can make it economically useless even on a fixed graph; the trap above shows why amplification cannot be dismissed.

## Fairness and a finite experiment, if pursued

This is a named **clearing preference and retention strategy**, not a permission to use zero-balance channels. It is legitimate to investigate if peers knowingly accept the tradeoff. It would evade the model if remaining units were hidden from debt scores, channels were kept after actual zero, or stale headroom survived an external close/reversal. All retained debt, active channels, messages and storage must count.

Use a prospective 2×2 comparison: cancellation versus Headroom, each with floor zero versus floor one. Keep transfer inputs, precision, clocks, faults, seeds and budgets fixed. This separates the effect of retaining balances from the effect of restoration. Record final debt, debt area, completed-cycle reduction, restored volume, actual closures, open channels, transfer delay and wire attempts. Include the branch/return-path trap and one-unit cycles alongside random dynamic graphs; do not tune the unit on held-out Sarafu results.

The useful question is whether a deliberate refusal to fully clear sometimes buys enough future local routing opportunity to offset its immediate and possibly amplified cost. There is no general tiny-cost guarantee, and any future dynamic experiment should use a separate, prospectively frozen configuration. The original replication is complete and remains unchanged.

## Separate static Sarafu oracle check

A bounded offline calculation on the existing Sarafu 50k CSV fixture (30,726 STANDARD transfers, bilaterally netted into 13,831 positive debts) finds a small **optimal-ledger** price for the one-unit floor on this particular snapshot:

| Fixed-cap reference | Minimum retained debt, source monetary units | Debt cleared |
| --- | ---: | ---: |
| Lower bound zero | 6,027,873.395 | 18.92118853% |
| Lower bound 0.001 on every positive input edge | 6,027,876.703 | 18.92114403% |

The optimal-debt difference is **3.308 source monetary units**, or **0.00004449% of initial debt**. All 13,831 relationships remain nonzero in the floor solution; the zero-floor solution retains 11,995. Initial debt is 7,434,585.295. The fixture's balances are large enough that one quantum often is small, but the counterexample above remains valid.

For the floor reference, substitute `y = x - 1`, use capacities `B - 1` and supplies induced by that shifted starting ledger, solve the exact min-cost flow, then add one back on every original edge. Original net positions and `1 <= x <= B` are independently checked after reconstruction. Simply clipping a zero-floor optimum would not preserve net positions.

[Source](headroom_floor_reference.py), [pinned result including both final ledgers](results/headroom-floor-reference.json), and [three focused tests](test_headroom_floor_reference.py) are separate from the completed replication. Tests include the 30-edge/120-unit amplification trap. OR-Tools returns `OPTIMAL` for both static references. This ignores transaction chronology, episode closures, communication, discovery and faults; it establishes neither a node-local performance gain nor a cheap dynamic execution path.

```sh
/workspace/tools/strategy-pit-python/bin/python experiments/headroom_floor_reference.py \
  --csv /workspace/jerboa-review/__tests__/fixtures/sarafu-50k.csv \
  --output experiments/results/headroom-floor-reference.json
```

## Publication verification

The three focused tests pass. Re-running the static Sarafu calculation with the fixture and software versions pinned in the result reproduces the saved JSON byte for byte, including both reconstructed ledgers. This validates reproducibility of this offline reference; it does not establish a safe distributed implementation of retention.
