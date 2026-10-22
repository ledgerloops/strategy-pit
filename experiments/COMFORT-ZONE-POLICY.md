# Comfort zones as clearing permission

Research design, 22 October 2026. This supersedes the recent-gain-only proposal
as the preferred policy. The full local permission rule is modelled below.
The application now implements a sound but incomplete
[bounded-surplus selection protocol](../app/headroom_protocol.md) under that rule,
with actual hashlock settlement. The general private benefit predicate is still
open. Frozen benchmarks remain unchanged; implementation is not deployment evidence.

## Two separate requirements

1. **Local permission:** the resulting balance on each affected direct trustline
   is inside the mutually agreed comfort interval, intersected with hard limits.
   Each node's signed net position is preserved. For automatic operation, both
   endpoints have enabled automatic assistance; existing opt-outs are not silently
   removed. Historical gains and non-increasing local exposure are not required.
2. **Collective improvement:** the complete settlement strictly reduces aggregate
   gross debt, `F(x) = sum_e |x_e|`. This must be established by the neighbour-private
   protocol, not supplied by a graph-reading host. Local permission alone does
   not prove it. Hashlocks condition fulfillment but do not prove economic benefit.

The first requirement is implemented by
[`comfort_zone_policy.py`](mdg2/comfort_zone_policy.py), policy identifier
`comfort-zone-conditional-v1`. Its inputs are only a node's own two incident-edge
changes and bilateral preferences. Its result is conditional willingness, not
settlement authorization. No discovery, hashlock, reservation or private aggregate
verification implementation is supplied by this predicate.

This explicitly permits using an existing, agreed **zero-balance trustline**.
It does not invent a relationship with a remote node or authorize global peer
discovery. It supersedes the historical baseline restriction in
[the recent-gain proposal](RECENT-GAIN-POLICY.md); that earlier model remains
available as an alternative comparison, not the preferred design.

## The concrete shortcut example

Start with one unit on every arrow in `A -> B -> C`, `C -> D -> A` and
`C -> E -> F -> A`. Also establish a direct, initially zero C–A trustline whose
agreed comfort zone permits C to owe A one unit.

| First clearing choice | Remaining debts | Further permitted adjustment |
| --- | --- | --- |
| `A -> B -> C -> D -> A` | `C -> E -> F -> A`: gross 3 | Replace with `C -> A`: gross 1 |
| `A -> B -> C -> E -> F -> A` | `C -> D -> A`: gross 2 | Replace with `C -> A`: gross 1 |

The residual loop closes via `A -> C`, which creates debt `C -> A`; do not confuse
the adjustment direction with the resulting debt direction. C and A keep the same
total exposure, intermediaries reduce theirs, and all signed net positions are
unchanged. One is optimal here because C still owes A one net unit.

The historical-gain rule would forbid activating that zero-baseline link. The new
rule admits it directly on the strength of agreed comfort-zone capacity. Without
the added C–A link, the earlier 3-to-2 repair is also permitted, even though helper
D increases its exposure and need not present a gain history.

These are offline consent fixtures with author-specified loops, not evidence that
private discovery finds the loops or that concurrent hashlock settlement completes.
The tests also demonstrate that local permission admits reversing the shortcut,
raising debt from 1 to 3. The collective-improvement requirement must reject that.

## Scope of the convergence target

For fixed intervals, fixed net positions, integer units and a feasible starting
ledger, the [negative-residual-cycle theorem](PRIVATE-CONVERGENCE.md) applies.
No remaining improving residual cycle is equivalent to optimal gross debt within
that feasible box. This is stronger than no remaining cycles of positive debt.
One-hop outcomes are available only where direct trustlines and capacity permit;
shared capacities mean arbitrary obligations cannot be optimised independently.

An implementation must find residual moves even when every balance is already
comfortable. The current strict-discomfort origin condition is insufficient for
that task. Complete fair discovery, concurrent progress, immutable consent and
private verification of improvement remain separate protocol obligations.

For a finite amount, evaluate exact changes `|after|-|before|`. Initial marginal
unit costs cannot safely be multiplied through a zero crossing. For example,
cycle balances `(-1,-1,-10)` changed by `+5` become `(4,4,-5)`: gross debt rises
from 12 to 13 despite all initial unit marginal costs being negative. Batching
must stop at the next zero/bound breakpoint or verify the exact aggregate change.

Existing balances outside the shared comfort intervals need a separate recovery
rule; they do not satisfy the theorem's feasible-start assumption. New transactions
or changed preferences change the feasible problem. An already authorized
hashlock fulfillment cannot simply be revoked by changing settings.

Run the isolated fixtures with:

`python -m unittest discover -s experiments/mdg2 -p test_comfort_zone_policy.py -v`
