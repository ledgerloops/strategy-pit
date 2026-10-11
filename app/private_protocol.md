# Private-route hashlock testnet, version 2

`private_node.py` is a separate TEST-only protocol implementation. The earlier `node.py` ring-coordination demo remains version 1 and is not used for this protocol. Version 2 refuses databases without its explicit protocol marker. Start all participants with fresh version 2 databases; never replace a database to escape outstanding obligations.

## What each node knows

A node stores its own direct neighbours, local bilateral balances, and—for each proposal—one predecessor, one successor, an opaque random identifier, a condition and a fixed amount. Only the origin stores its own origin flag and the unreleased secret. No wire message contains a route, participant roster, origin identity, hop count, bottleneck history or global graph. The state API exposes only local balance changes, consent and local receipt evidence.

This is **message-content privacy**, not anonymity against traffic analysis. Nodes see adjacent transport endpoints, timing, amounts and a shared opaque identifier/condition. Colluding peers can correlate observations; graph knowledge and timing may allow inferences about route length. The protocol does not promise resistance to those inferences.

## Condition and messages

The origin draws independent 32-byte identifier and 32-byte secret with `secrets.token_bytes(32)`. Both use canonical lowercase hexadecimal. `hashlock_scheme` is `sha256-context-v2`; the helper `hash_condition(id, amount, preimage)` computes SHA-256 over the ASCII bytes of this compact JSON, with alphabetically sorted keys and no whitespace:

```
{"amount":3,"id":"<64 lower-case hex>","preimage":"<64 lower-case hex>","protocol":"private-hashlock-v2","unit":"TEST"}
```

The secret is stored in a private SQLite table before probing and is not returned in proposals or the state API before irreversible release. A proposal's approval digest binds its condition, version, amount, local before/after changes and creation time. Released receipts include the preimage, condition and scheme so anyone holding the receipt can verify the hash relation. That verifies a **local fulfillment condition**, not identities or whole-network completion.

All wire envelopes contain only `kind`, `id`, `condition`, `amount`, `protocol` and a transport `message_id`. Only `fulfill` may carry `preimage`; unexpected fields are rejected. The amount stays fixed throughout discovery. The prototype deliberately gives up bottleneck adaptation and exhaustive search to avoid exposing route aggregates.

## Admission, consent and release

1. The origin chooses one locally eligible outgoing debt neighbour and sends `probe`. Each new participant binds its incoming neighbour, chooses an eligible outgoing neighbour other than the sender and forwards. Local capacity must cover the exact amount. A non-origin revisit is refused; a probe returning to its origin from a neighbour different from its original outgoing neighbour closes a cycle. Under unique honest node identities, this excludes one- and two-node cycles without transmitting a count.
2. Discovery records are durable. A successful return starts `prepare` along each node's locally stored successor. Each node reserves its two incident balances and stores its local quote. A failing prepare sends rejection backwards through locally stored predecessors.
3. When prepare returns to the origin, it can begin `ready` after its own approval. Each participant holds readiness until its own immutable quote is manually approved. It then forwards exactly once. Readiness returning to the origin establishes the honest-peer readiness chain without a named vote list.
4. The origin atomically records local fulfillment and a durable outgoing `fulfill` containing the secret. Only then is the secret released. Each recipient verifies the context-bound preimage, its local approval and both reservations, applies its local balance changes once and forwards fulfillment. A returning fulfillment terminates at the origin. Receipts report local application only; they do not assert a known cycle size or complete membership.
5. A participant may decline before approving. This durably prevents subsequent approval and routes rejection backwards. The origin can durably ABORT only before releasing the secret. Abort travels along successor links and releases reservations. Approval cannot be revoked. There is no timeout release or cancellation after commitment.

A refused revisit uses a distinct `probe_rejected` response. The immediately preceding node records that its successor refused admission; later abort stops at that edge. This permits failed subcycles to unwind without circulating abort forever or relaxing bound-neighbour authentication. Semantic probe replays from an already bound predecessor do not reopen proposals. Terminal abort and fulfillment replays do not create fresh forwarding work.

## Durability and limitations

Local updates, inbox deduplication and forwarded outbox messages share one SQLite transaction. WAL and FULL synchronous mode are enabled. Outbox retries survive process crashes and lost HTTP acknowledgements. Immutable conditions and valid preimages are checked even on terminal fulfillment replays. Forward phases require the bound predecessor; rejection phases require the bound successor. Pausing stops new admission and approvals, while admitted settlement control continues.

This is an honest-peer crash/restart protocol, **not a full HTLC system or Byzantine-safe network**. There are no timelocks, public signatures, elected coordinators, automatic release deadlines or permanent-origin-loss recovery. A malicious participant can lie about readiness; the origin can disclose its secret improperly; a valid preimage alone does not prove all participants consented. Local approval and reservations remain mandatory. No claims of simultaneous balance visibility are made.

Balances initially come from mutually consistent test fixtures. There is no external transfer, live asset, changing trustline, headroom, currency conversion or account enrollment API. Plain HTTP is appropriate only for loopback or isolated trusted tests; public use requires a different deployment and security design. Durable databases must not be rolled back or shared by concurrent logical-node processes. Tables and secrets are retained indefinitely, with no production retention or operational recovery policy.
