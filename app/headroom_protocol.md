# Comfort-zone headroom clearing with a bounded surplus certificate

Implemented alpha mode: `headroom`. Protocol: `private-hashlock-v2`; policy:
`comfort-surplus-bit-v1`; fulfillment scheme: `sha256-headroom-v1`.

This is a neighbour-private, coordinator-free **sufficient test** for beneficial
clearing. It implements ordinary debt cycles, direct-trustline shortcuts and some
beneficial rerouting with increased helper exposure. It is not a complete search
or a proof of reaching the global optimum. The larger permitted model is described
in [the comfort-zone design](../experiments/COMFORT-ZONE-POLICY.md); its conditional
optimality theorem remains in [the convergence note](../experiments/PRIVATE-CONVERGENCE.md).

## Permission versus choice of an adjustment

Each participant accepts local changes only inside both endpoints' shared comfort
interval, intersected with hard credit limits. Both must enable assistance. Existing
zero-balance trustlines are eligible; unknown nodes and nonexistent relationships
are not. Each participant checks its own two edge changes and conserved signed net
position. There is no history-of-gains requirement or independent prohibition on
increasing local exposure. The surrounding application still requires the proposal's
actual approval; assistance eligibility alone does not override manual consent.

The alpha selects a safe subset of these permitted changes. For an operation amount
`a > 0`, each affected balance moves by exactly `a`, and no edge crosses through zero.
Ending or starting at zero is allowed. The absolute exposure change on an edge is
therefore exactly `-a` or `+a`. A participant's two-edge cost is `-2a`, `0` or `+2a`.

## The single-bit rule

The origin starts on a debt-reducing edge. When the search closes, it must also
reduce exposure on the incoming edge: its local cost is `-2a`. It keeps that saving
out of the surplus allowance and sends the bit **false**.

Every other participant computes its actual two-edge cost from its own quoted
balances, never from a reported gain by another participant:

| Own local exposure change | Rule for the surplus bit |
| --- | --- |
| `-2a` | Set the outgoing bit to true; discard any additional stored surplus. |
| `0` | Forward the incoming bit unchanged. |
| `+2a` | Require an incoming true bit, consume it, and forward false. |

A participant receiving false may explore another outgoing neighbour rather than
accept an unsupported exposure increase. The current search chooses a random
eligible direct neighbour and rejects repeated non-origin visits; it does not
perform exhaustive backtracking. A failed attempt is not proof that no loop exists.

**Soundness for honest participants.** Every accepted positive-cost non-origin
participant consumes a distinct previously earned negative-cost participant's
allowance. No positive participant can spend an allowance twice, and the origin's
negative cost is never offered. Hence the sum of all local costs is at most `-2a`.
Every trustline's cost is counted at its two endpoints, so the completed cycle
reduces gross debt by at least `a`. This uses only local arithmetic and one bit;
the host does not calculate or supply a global benefit decision.

The fixed-capacity bit deliberately discards savings. Some globally improving
cycles require accumulating several savings before consecutive helper increases;
this rule can reject them. Consequently the full no-negative-residual-cycle
optimality criterion is not established by this implementation. With fixed integer
balances and no external arrivals, successful operations strictly decrease debt,
but search fairness, availability and the restricted certificate limit completion.

## The examples now execute through hashlocks

With an agreed zero-balance C–A trustline, `C -> E -> F -> A` can become `C -> A`:
gross debt **3 -> 1**. Starting at E, E keeps its own reduction, F earns surplus,
and A and C have neutral local costs. Likewise `C -> D -> A` becomes `C -> A`:
**2 -> 1**, with D retaining the strict reduction and the other costs neutral.

Without a direct C–A link, the previously trapped three-unit path can be repaired
through `E -> F -> A -> D -> C -> E`: E keeps a reduction, F earns surplus, A
passes it, D consumes it to restore two comfortable exposures, and C passes false.
The result is `C -> D -> A`: **3 -> 2**. D needs no historical-gain record.

The automated fixtures use real separate local databases, proposals, immutable
approvals, context-bound SHA-256 secrets, readiness and fulfillment messages. They
inspect the result offline, without giving any participant a global graph or route.

## Binding the certificate to actual settlement

Only `probe` and `prepare` envelopes carry the Boolean field `surplus`. Each node
stores `surplus_in`, `surplus_out`, and its own `surplus_origin` role along with
its ordered incoming/outgoing edge quotes. Outgoing packets use this local stored
output, not an unexamined forwarded field. During prepare, the received bit must
match the stored input; the node recomputes the transition from its current quotes.
Changed balances, preferences, or an altered bit abort before approval/release.

The existing local digest binds these snapshots into approval. Per-trustline
reservations prevent competing local changes. The hashlock includes the mode,
policy, direction, amount and operation identity, so a fulfillment from another
policy or direction cannot be substituted. No balance changes during discovery.
An origin releases the secret only after the readiness traversal; every node
verifies the secret, approval and reservations before local application.

Restarted nodes retain pending bits and approvals in their own durable state.
Repeated fulfillment cannot reapply balances. There are no timeout-based unlocks:
an unavailable peer can leave work pending. A local receipt verifies its hashlock,
quoted changes and surplus transition, not signatures or remote finality.

## Privacy and trust boundary

No path, participant roster, remote identity, total saving or loop length is sent.
The surplus bit reveals one capped predicate about the preceding search segment;
it is not zero information about others. Existing timing, traffic correlation,
shared-operation identifiers, and colluding-peer limitations still apply.

The proof assumes honest execution by peers. An authenticated malicious peer
could fabricate a surplus bit; this is **not** a Byzantine-secure aggregate proof.
The hosted alpha runs the prescribed node software with operator-controlled node
credentials, and must disclose that operator access. Users' passkeys authenticate
their accounts; they do not turn the protocol into a malicious-peer secure system.
Neither shared hosting nor the observer is allowed to repair a decision using
cross-node visibility. General private verification against dishonest contributors
requires a separate reviewed cryptographic protocol.

Run the focused tests:

```sh
python -m unittest discover -s app -p 'test_headroom*.py' -v
```
