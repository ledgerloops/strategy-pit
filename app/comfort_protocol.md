# Comfort-assisted private hashlock settlement

This extension implements `bilateral-comfort-v1` in the existing honest-peer TEST network. It joins the address-book preference model to real neighbour HTTP messages, durable reservations and locally verified hashlock fulfillment. It is not unattended settlement or a production security claim. See [private protocol assumptions](private_protocol.md) and [network tests](COMFORT_NETWORK_TESTING.md).

## Choosing and approving a move

`POST /api/discover` accepts `{ "amount": 2, "mode": "comfort" }`. Omitting the mode retains cancellation-only discovery. The state API advertises supported `discovery_modes`. Comfort search may use configured zero-balance relationships; ordinary cancellation search still requires debt capacity. It does not create contacts or read a global graph.

An origin chooses a direct relationship whose distance from the shared comfort interval strictly decreases. It tries signed directions locally. The direction stays fixed along the opaque search: each participant changes its predecessor balance by `-direction * amount` and successor balance by `+direction * amount`. Their signed sum is unchanged. A participant selects its next neighbour from local state, excludes immediate reflection and rejects non-origin revisits. Returning to the origin through a distinct neighbour preserves the existing minimum-three rule under distinct honest identities; no roster or count is transmitted.

Every changed edge must have received peer preferences and a nonempty shared zone. Discomfort may not increase. Neutral moves or increases in absolute exposure require both endpoints' assistance permissions (`auto_adjust` in the historical API). Strict debt reduction may reduce existing excess exposure after a lowered credit limit; new or increased excess exposure is forbidden. A helper need not know which remote relationship benefits.

The amount is fixed and discovery tries one selected path. A failed attempt does not establish that no useful cycle exists. This local conservative policy is not an optimum and can finish with more total discomfort than a policy allowed to worsen individual relationships.

## Bilateral admission

Comfort `probe` and `prepare` messages carry an `edge_quote` containing only the sending relationship's `before`, `after`, `own_revision` and `peer_revision`. The receiver requires negated balances and swapped matching revisions against its own current records. No preference from a third party or remote participant identity is forwarded.

Each node durably records its own incoming and outgoing quote, including both local preference snapshots, the shared interval and discomfort before/after. Preparation revalidates those snapshots and local economic rules, then reserves both edges and binds the exact terms into the approval digest. Stale admission causes explicit rejection and abort propagation, rather than silently accepting a newer limit. A reserved edge defers incoming preference updates and refuses local edits until its outcome is recorded.

All participants still manually approve their own immutable proposals. Assistance permission makes a move eligible; it is not authorization to skip approval. The existing prepare/ready chain establishes readiness under honest-peer assumptions, without collecting identities or individual votes at the origin.

## Fulfillment and evidence

The comfort scheme is `sha256-comfort-v1`. SHA-256 covers compact, alphabetically sorted JSON with these fields:

```
amount, clearing_mode="comfort", direction, id,
policy="bilateral-comfort-v1", preimage,
protocol="private-hashlock-v2", unit="TEST"
```

Mode, policy and direction are immutable across messages. Existing cancellation conditions and receipts retain `sha256-context-v2`. Browser verification and the standalone receipt verifier recognize both schemes. The latter also checks local economic consistency against the pinned snapshots. Receipt contents are not public signatures or independently authenticated proof of remote application.

Fulfillment requires valid preimage evidence, local approval, unchanged reserved balances and the durable admitted terms. The local balance changes, decision, receipt and outgoing message are committed together. Replay is idempotent. Preference updates after local completion do not rewrite the receipt or outstanding decision.

## Cancellation, recovery and compatibility

Before approval, a participant can decline. Failed admission and declines propagate rejection to the origin; only a durable abort before secret release permits reservation release. After approval, a participant waits for fulfillment or evidenced abort. There is no timer-based unlock, expiring comfort credit or rollback after release. Lost messages/acknowledgements retry from durable outboxes. A sleeping or crashed node must return with its retained database. Permanent loss or an indefinite partition can leave work blocked indefinitely.

Existing cancellation data stays compatible with the extended runtime. Older runtimes do not understand comfort wire messages: upgrade participating test nodes before using comfort mode, and do not downgrade a database containing pending comfort work. There is no mixed-version fallback that converts an admitted comfort operation into cancellation.

Timing, amounts, direction, shared condition identifiers, transport observations and collusion can reveal information. The privacy boundary is no required remote identities or exact total loop length in protocol-visible local state/messages, not absolute anonymity. Hostile readiness claims, Sybil identities, key compromise, stale backups and public deployment remain outside this prototype's safety claim.
