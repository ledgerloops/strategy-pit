# Reusing clearing gains as trustline headroom

Research policy design, 22 October 2026. The user chose a per-trustline allowance
with **no time expiry**: it ends when that trustline receives a new external
transaction or either endpoint changes its relevant preferences. This note
specifies an isolated local consent model. It is not a change to the running
application, a private discovery protocol or a new hashlock implementation.

The user's consent is conditional: restore a local gain **when doing so serves
the whole loop's interest**, meaning the complete settlement strictly reduces
aggregate gross debt. Historical headroom alone is not settlement authorization.

The standalone [`recent_gain_policy.py`](mdg2/recent_gain_policy.py) model exposes
`RecentGainConsent.willing(changes)` as only that local conditional willingness.
Its `observe_completed` method records already completed operations; it does not
approve or execute them. The accompanying
[`test_recent_gain_policy.py`](mdg2/test_recent_gain_policy.py) fixtures distinguish
local willingness from the missing private proof of collective benefit. No live
policy is activated.

## Local rule

Each endpoint keeps, for each direct neighbour, a signed baseline `B`: the balance
at the beginning of that trustline's current clearing epoch. Every subsequent
clearing move on that trustline must stay in the signed segment between zero and
`B`. Clearing never moves this baseline. For example, if `B = -5`, successive
balances `-5 -> -2 -> -4` are admissible under this historical envelope, but
`-4 -> -6` and `-4 -> +1` are not. A zero baseline grants no additional exposure.

Reducing exposure creates reusable headroom; increasing it consumes that
headroom by returning toward the same prior signed balance. There is no pooled
allowance transferable to another neighbour and no allowance created by the
passage of time. Repeated clear/recreate operations cannot ratchet the ceiling
upward. No remote account identity, path, hop count, global graph or optimizer
answer is needed to evaluate the rule.

This is a deliberately bounded alternative to the existing research policy.
It applies the historical segment to **all** clearing moves, including moves
that leave a node's total exposure unchanged. It does not retain a fallback
that could shift exposure above one edge's baseline by reducing another edge.
Consequently each edge remains below its own epoch's original magnitude. A node's
total exposure is bounded by the sum of its current edge-baseline magnitudes;
different edges may have begun their epochs at different times.

The existing bilateral `comfort_move` gate still applies. Its hard-limit checks,
shared comfort interval, discomfort rule and automatic-assistance preferences
are not bypassed by historical headroom. Thus a reduction from an uncomfortable
balance may still be irreversible under that gate: this proposal does not permit
increasing discomfort merely because it restores a historical balance. Fresh
manual consent, where required by the surrounding application, remains separate.

## Epoch boundaries and settlement integration

A newly posted external transaction sets that trustline's baseline to its new
balance. A relevant preference change starts a new epoch at its current balance.
Neither event grants authority to restore the older baseline. Unrelated
trustlines retain their own baselines. Preference changes should invalidate
stale quotes even when the new values happen to match an earlier configuration.

The prototype records observed completed clearing changes exactly once by
operation identity, rejecting conflicting reuse of an identity. Repeating an
unchanged preference snapshot does not start a new epoch. Its transaction observer
expects an already deduplicated, ordered posted balance; it is not an event-ingestion
API and does not itself reject duplicate or stale external transaction observations.
Production delivery must not repeat a ledger movement, reset a baseline, or
restore an obsolete allowance.

Production integration needs durable, atomic local accounting, per-trustline
reservations and immutable approval evidence tied to the baseline epoch and
quoted preferences. Concurrent operations must not spend the same headroom.
A settings change cannot revoke an already authorized hashlock fulfillment;
the old operation must safely resolve before the new epoch governs subsequent
work. Those mechanisms are not supplied by an in-memory consent model.

Both endpoints independently enforce their own local records and current bilateral
preferences. The host must not reconcile epochs or repair stale state by reading
both nodes' stores. Protocol messages must establish any needed agreement.

## What this repairs

In the six-node competing-loop example in
[the convergence analysis](PRIVATE-CONVERGENCE.md), clearing the short loop leaves
gross debt 3, although gross debt 2 is reachable. The blocked helper previously
had one unit on each of its two affected trustlines; both were cleared. Restoring
those same two exposures now fits their signed historical segments. With broad
unchanged comfort zones, the local consent obstruction is removed.

The steps are concrete:

1. Initially there is one unit on every arrow in `A -> B -> C`,
   `C -> D -> A`, and `C -> E -> F -> A`: gross debt 7.
2. Clear `A -> B -> C -> D -> A`. The remaining debt is
   `C -> E -> F -> A`: gross debt 3. D's exposure fell from 2 to 0.
3. A compensating residual loop `A -> D -> C -> E -> F -> A` clears the three
   remaining debt edges and restores the two old debts `C -> D -> A`.
   Gross debt falls from 3 to 2. D's exposure returns from 0 to 2, exactly
   reverting its earlier gain; E and F each reduce their exposure from 2 to 0.

This is a new settlement with fresh consent and hashlock evidence, not revocation
of the first settlement. D can decide its local willingness from its own history.
Establishing that the full operation saves one unit must also happen through
the private protocol, not through a graph-reading host.

This is a claim about admissibility of the repair. An offline fixture supplying
the candidate cycle does not demonstrate that private discovery finds it or
that concurrent hashlock settlement completes it.

## Local headroom does not establish aggregate benefit

Consider these initial one-unit debts:

```text
Short path: A -> B -> C
Long path:  A -> E -> D -> C
Return:     C -> A
```

Initial gross debt is 6. Clearing `A -> E -> D -> C -> A` leaves the short path,
with gross debt 2. A later residual cycle can cancel that short path and restore
the long one, raising gross debt from 2 to 3. Every restored edge remains inside
its historical signed segment. B strictly reduces its local exposure, A and C
leave theirs unchanged, and D and E each restore two units of prior exposure.
All these moves can pass broad bilateral comfort gates.

Thus a strictly improving initiator plus permitted helpers no longer proves a
globally improving loop. The production policy must not be switched merely by
replacing its local nonexpansion test. A neighbour-private way to establish a
strict aggregate improvement remains an independent protocol requirement.
Hashlocks provide conditional fulfillment; they do not establish economic
improvement. The host must not supply the missing benefit calculation.

## Conditional convergence claim

For a transaction-free epoch with fixed preferences, these signed historical
segments are exactly a fixed-cap headroom model: orient each edge in its original
debt direction, and its magnitude stays in `[0, |B|]`. If every required move in
that box is also admitted by the comfort and consent rules, the residual-cycle
optimality theorem applies **within that box**. No time expiry means an admissible
repair is not lost merely because fair discovery takes a long time.

Fair complete discovery, privately established aggregate improvement and live
concurrent settlement are still needed. External transactions or settings changes
alter the feasible problem. This policy does not establish optimality over the
larger signed hard-limit box: a beneficial route requiring a never-used edge or
exposure beyond its baseline can remain forbidden. Benchmark clearing potential
must therefore use the same fixed-cap feasible set as the algorithm under test.
