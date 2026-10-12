# 005 — Shared comfort zones and helping neighbours

**Status:** In progress · **Opened:** 2026-10-12

[Issue tracker](README.md) · [Product roadmap](../product-roadmap.md)

## The owner's model

Each contact has a hard credit grant and a personal preferred balance interval. Positive balance means this peer owes you. Your own credit grant controls the positive hard limit; your peer's grant controls the negative hard limit. Neither participant edits the other's preferences.

For personal intervals `A=[a_min,a_max]` and `B=[b_min,b_max]`, the shared comfort zone in A's perspective is:

`C = A ∩ [-b_max,-b_min] ∩ [-B.credit_limit,A.credit_limit]`.

An empty intersection is **no shared comfort zone**, not `[0,0]` and not permission to choose a compromise. Preferences can be meaningful even when zero lies outside them. Never label the negative of a peer's minimum as the shared minimum without reversing the endpoints.

Inside C there is no demand to clear. With explicit permission, a balance may move within C to help other relationships become more comfortable. Each participant's total signed net position remains unchanged. A comfortable balance and permission for automatic changes are distinct decisions.

## Economic objective

For nonempty C, discomfort is the distance from the current balance to C. Score each bilateral edge once. Clearing should reduce discomfort rather than necessarily reduce total absolute debt. Report both, since helpful adjustments can increase gross debt while reducing discomfort.

The first simulated policy is deliberately conservative: every changed relationship's discomfort must not increase; at least the initiating relationship improves strictly. Helpers can move within a jointly accepted zone when permissions allow. It does not claim a global optimum or permission to sacrifice one uncomfortable relationship for others. Empty-zone relationships do not provide comfort-assisted capacity.

A shared zone allowing movement through zero is an explicit alternate routing policy. It does not silently change the cancellation-only channel rule in the existing hashlock testnet.

## App behaviour

- Address-book entries show current signed balance in plain language, your credit grant, the peer's grant, each personal zone and the resulting shared zone.
- Edit only your own grant, interval and automatic-adjustment preference. Peer values are received over the authenticated direct relationship.
- Version updates and reject stale edits. Distinguish unreceived peer preferences from a known empty intersection; never assume missing peer permission.
- Lowering a grant does not erase debt. Show current exposure above a new cap and permit risk-reducing repayment; do not create further excess exposure.
- Existing prepared/approved settlements keep their admitted terms. Preference changes must not rewrite quotes or release reservations. The initial implementation can defer settings changes while affected capacity is reserved.
- Clearly distinguish storing a preference from an actively implemented automatic settlement policy. The existing app's hashlock settlement and the serialized preference simulation have different guarantees.

## Validation

Test interval mirroring, hard-limit clipping, empty intersections, missing/stale peer updates, opposing preferences, asymmetric limits, lowering below existing exposure, changes during reservations and per-peer isolation. Exercise actual neighbour synchronization and browser editing.

Simulations must include an example where discomfort falls while debt rises, seeded graph families, explicit cooperation permissions and conserved signed positions. Record offered/accepted external transfers and unmet demand for any changing-graph experiment. Runtime decisions use local balances/preferences and neighbour messages; global graph access is permitted only for fixtures and independent scoring. Preserve negative results and disclose any serialized settlement shortcut.

## Delivery evidence

[Address-book implementation](../../app/COMFORT.md) now persists and synchronizes per-peer settings. [Simulation results](../../experiments/COMFORT-SIMULATION.md) cover 32 matched synthetic runs and an example with rising debt but falling discomfort. Actual comfort-assisted hashlock settlement remains a separate integration task; the stored preference is not active authority in the current manual cancellation protocol. This issue does not equate editable limits with production credit issuance or safe automatic hashlock settlement under new policies.
