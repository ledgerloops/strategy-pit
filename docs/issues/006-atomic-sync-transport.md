# 006 — LedgerLoops over Atomic Sync

**Status:** Proposed — not implemented · **Opened:** 2026-10-25

[Issue tracker](README.md) · [Private hashlock protocol](../../app/private_protocol.md) · [Comfort extension](../../app/comfort_protocol.md)

Written after direct discussion with the user. This is an adaptation of the public private-hashlock-v2/comfort design, not a verified description of the hosted Postgres backend. No application or protocol code is changed.

## Recommendation

Use Atomic Sync to replicate durable, independently verifiable protocol events between neighboring LedgerLoops nodes. Keep a trustline descriptor and derived view, but do not let concurrent assignments to a shared `balance` or `status` field decide settlement. Each node runs a serialized local protocol actor that validates events and owns its reservations and decisions.

This can remove the need to build a separate HTTP message-delivery mechanism. It does not remove the LedgerLoops settlement state machine or automatically replace its transactional storage. Native nodes can meet over Iroh, browsers can meet over WebRTC, and an AtomicServer can provide an optional always-online meeting point. Closed browsers cannot run unattended clearing.

## Existing implementation facts

- [Atomic's outbox](https://github.com/ontola/atomic-server/blob/6c2fc2347f01871056c91a80f3a936ce9cc9905b/lib/src/sync/outbox.rs) tracks dirty subjects and can sign/coalesce their changes at drain time. It is not an ordered application message queue preserving every intermediate state or a counterparty receipt.
- [Peer sync](https://github.com/ontola/atomic-server/blob/6c2fc2347f01871056c91a80f3a936ce9cc9905b/lib/src/sync/engine.rs) can import snapshots using drive/replica trust. Signed envelopes are checked separately; a rejected optional envelope does not reject the imported snapshot. Protocol authorization must not treat materialized fields as independently signed evidence.
- [Envelope retention](https://github.com/ontola/atomic-server/blob/6c2fc2347f01871056c91a80f3a936ce9cc9905b/lib/src/envelopes.rs) defaults to the latest envelope. The application must retain the evidence it needs rather than assume every historical commit is available indefinitely.
- [AtomicNode](https://github.com/ontola/atomic-server/blob/6c2fc2347f01871056c91a80f3a936ce9cc9905b/lib/src/runtime/node.rs) supplies local saves, outbox access and ingestion policies. Its current application surface does not expose a general multi-resource settlement transaction. A save followed by outbox marking must not be assumed to atomically include arbitrary application state changes.
- The [public LedgerLoops protocol](https://github.com/ledgerloops/strategy-pit/blob/72d364f382aa9ef669a85229a50ee0822e108402/app/private_protocol.md) commits local state transitions, inbox deduplication and outgoing messages together. It uses neighbor-private hashlock messages and promises local receipt evidence, not Byzantine-safe global finality. Preserve that scope.

## Resources and identity

| Resource/state | Purpose and ownership |
| --- | --- |
| Trustline descriptor | Names both logical peers, unit, protocol version and incarnation. One peer proposes it; the other explicitly accepts its hash. The accepted agreement defines each party's obligations and limits. |
| Event Resource | One proposed immutable signed message: offer, acceptance, probe, prepare, approval, ready, fulfillment, rejection, abort or acknowledgment. A new message gets a new Resource; later steps do not overwrite its `status`. |
| Trustline view | A projection of verified protocol events: accepted balance/checkpoint, pending requests and local status. Editing the view does not change the protocol's accepted state. |
| Private actor state | Local balance projections, reservations across trustlines, processed message IDs, decisions, secrets and durable outbound work. This state is not synchronized to counterparties. |

Use ordinary minted Atomic Resource IDs. Bind both peers to one agreed application `channelId` and descriptor hash; do not assume that independently minting Atomic Resources deduplicates the same trustline. Include a new incarnation when intentionally replacing a channel. Preserve mappings to existing LedgerLoops node identities when introducing Atomic Agents.

For an initial deployment, use two directional, pair-specific publication scopes, ideally separate Drives: Alice publishes events to her stream and Bob reads it; Bob publishes to his and Alice reads it. Restrict authoring and validate expected authors at the protocol layer. Do not grant every neighbor write access to the node's other trustlines or private state. Establish and pin the expected pair and bootstrap roots explicitly.

ACLs and transport admission remain required, but ACLs alone do not prove the validity of a settlement event. Verify application signatures even when a drive owner or relay can deliver a snapshot containing arbitrary fields. The exact read-only receiver/bootstrap path and pairing UX require integration tests.

## Signed event envelope

Define canonical signed bytes with a LedgerLoops-specific domain separator. Include protocol version, channel/incarnation, sender and recipient identities, a unique message ID, message kind and its payload. Bind proposal IDs, exact unit/amount, condition and the relevant previous accepted-state or quote hash where the transition requires them. Local before/after quotes remain local to the participant and its existing consent rules.

Use an explicitly specified exact numeric representation across Rust and JavaScript. Preserve the public protocol's context-bound hashlock construction unless introducing a separately versioned protocol change. Routing and delivery metadata must not change signed business meaning.

Each event carries its own application signature over these bytes, in addition to the Atomic Commit carrying it. This makes evidence verifiable after snapshot replication, delayed delivery or commit-envelope pruning. Using an Atomic Agent key for this requires an explicit domain-separated signing API and key policy; it is proposed application work, not an existing LedgerLoops event API.

Treat signed payloads as immutable at the protocol layer. Verify the signature, expected author, context and transition before using them. An edit to a payload under the old signature is invalid. Conflicting valid signatures from the same logical sender must be detected as equivocation, not resolved by a Loro winner. Maintain an event-ID/hash registry and predecessor/checkpoint evidence; fork detection and recovery rules must be specified before production.

## A two-peer trustline update

1. Alice's local actor validates a proposed transition against the accepted trustline state and all relevant reservations. It durably records the proposal, its own consent and any held capacity, then schedules a signed offer event referencing that exact state and quote.
2. Atomic Sync makes the event available to Bob, immediately or after reconnection. Bob's actor verifies evidence and context before considering it. Transport delivery is not acceptance.
3. Bob approves only after verifying the expected state, his own limits and local reservations. He durably records his decision and a signed acceptance of the exact proposal hash. A refusal is a separate event.
4. Each actor derives the next accepted state from the required consent evidence and applies it once. An observer with only the offer displays it as pending. An acknowledgment can confirm observation; it is not an additional consent requirement unless the protocol specifies that.
5. Reservations are released according to the protocol decision. A published consent that the other side can still accept cannot be withdrawn merely because a local timer expired. Cancellation/withdrawal races need an explicit agreed rule. For the first prototype, retain committed reservations until acceptance, rejection or a mutually valid cancellation resolves them.

The signed proposal and acceptance establish bilateral agreement. They do not provide simultaneous visibility or an atomic transaction across devices. Repeated delivery, gaps and reordering must be handled by message IDs and expected-state checks. A message awaiting dependencies stays pending; do not use receipt order or a CRDT timestamp as settlement order.

## Multi-party loop clearing

Carry the existing neighbor messages as events rather than broadcasting one global loop Resource:

| Existing phase | Adaptation |
| --- | --- |
| Probe / probe rejection | Pairwise events carrying the existing opaque proposal ID, condition and fixed amount. |
| Prepare | The local actor reserves its incident capacity and persists its exact local quote before forwarding. |
| Consent / ready | Preserve explicit local consent and readiness forwarding. Automatic CRDT merging is not consent. |
| Fulfill | Publish the preimage only after the origin's existing durable release condition. Each actor verifies the hashlock, its consent and reservations, applies once and durably schedules forwarding. |
| Abort / rejection | Preserve the phase and bound-neighbor restrictions. No timeout unlock or rollback after commitment is introduced. |
| Receipt | Persist evidence of the node's own decision and application, not a claim that every node completed. |

Each actor bridges only its own predecessor/successor exchanges; Atomic is not expected to forward a frame through the whole clearing route. Keep unreleased preimages and remote topology out of synchronized resources. Do not put the full route, participant list or all trustlines in a shared Drive. Transport metadata and relay operators still affect privacy; this does not create anonymity or end-to-end encryption against a plaintext storage replica.

Signing pairwise messages attributes them to their local senders. It does not by itself upgrade the existing honest-peer protocol to Byzantine-safe settlement, prove global readiness, or fix permanent-origin loss. Such changes need a separate protocol/security design.

## Durability and one logical writer

Keep these local effects atomic: consumed message ID, reservation/balance/decision changes, and durable outbound message intent. A crash must not apply a balance transition without preserving its forwarding work or allow a retry to apply it twice. Delivery acknowledgments and message retention need an explicit policy; a sync acknowledgment is not a LedgerLoops acceptance.

There are two implementation paths:

1. **Initial adapter:** keep the existing transactional store/actor, and publish its durable outbound events as Atomic Resources. Store stable mappings from business message IDs to published Resources so replay does not create uncontrolled duplicates. Rebuild the publisher from pending work after a crash. Atomic becomes the peer message carrier; PostgreSQL or SQLite remains local protocol storage.
2. **Atomic-only actor:** implement and test a durable actor aggregate and outbound intent together in `atomic_lib`. One possible design stores local decisions and pending signed events in one private aggregate, then projects immutable event Resources idempotently. Another adds a dedicated atomic storage operation. Neither is implemented by this document, and both need API and crash-consistency review before removing the SQL store. Private actor data must never leak through the public event projection.

Run one fenced logical settlement writer per node. The same Agent key active on two offline devices does not provide mutual exclusion. Devices may submit requests, but failover requires a deliberate epoch/fencing and recovery design. Do not let CRDT merging silently choose between conflicting reservations. Existing event evidence and peer checkpoints must prevent replaying a stale backup as a fresh accepted state.

## Implementation and verification checklist

- [ ] Confirm the hosted LedgerLoops protocol/schema and define the exact compatibility target.
- [ ] Specify descriptor handshake, canonical event bytes, identity mapping, exact amounts, signature verification and accepted-state transitions.
- [ ] Specify cancellation races, equivocation handling, checkpoints, event retention, writer fencing and recovery.
- [ ] Implement a deterministic local actor and Atomic event publisher/receiver, initially retaining transactional storage.
- [ ] Verify pair-specific Drive bootstrapping, authenticated sync, ACLs, invalid snapshots/payloads and relayed delivery.
- [ ] Test duplicates, reordered/missing events, two offline proposals spending the same capacity, and multiple devices sharing an Agent.
- [ ] Inject crashes before/after local decisions, publication and receipt; verify conserved balances, reservations and recoverable forwarding.
- [ ] Exercise three-party fulfillment, creator departure, offline readiness, conflicting abort/fulfill messages and replay after restore.
- [ ] Choose supported transports and test actual browser/native paths, including no always-online replica and delayed availability.
- [ ] Decide whether an Atomic-only durable actor is justified after the adapter passes these tests.
