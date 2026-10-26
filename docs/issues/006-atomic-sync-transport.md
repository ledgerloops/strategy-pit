# 006 — LedgerLoops over Atomic Sync

**Status:** Proposed — not implemented · **Opened:** 2026-10-25

[Issue tracker](README.md) · [Private hashlock protocol](../../app/private_protocol.md) · [Comfort extension](../../app/comfort_protocol.md)

Written after direct discussion with the user. This is an adaptation of the public private-hashlock-v2/comfort design, not a verified description of the hosted Postgres backend. No application or protocol code is changed.

## Product rationale and first scope

Ontola wants to test-drive its in-house Atomic product in a useful application. LedgerLoops is a suitable case because it combines local-first interaction with explicit bilateral financial agreement and double-spend prevention. Useful applicability and learning about Atomic are sufficient reasons for the experiment; a cheaper replacement for PostgreSQL or a complete backend rewrite is not a prerequisite.

The first concrete scope is browser-to-Heroku synchronization: local views of trustlines and history, offline drafts or requests, and live updates from the hosted actor. The browser must use Atomic's local store and subscriptions to obtain those benefits; a server-only database swap would not deliver them. Peer-to-peer transports and moving protocol storage into `atomic_lib` remain separate possible steps.

The two logs, current-state views, checkpoints, Agent identities and permissions are application data modeled directly as Atomic Resources. This is a way to exercise Atomic's resource model, persistence, history, subscriptions and sync while keeping transaction validity explicit. It does not require treating a CRDT scalar as a spendable balance or making every device a simultaneous settlement writer.

## Recommendation

Use two sender-owned message-log Resources per trustline: Alice appends to the Alice-to-Bob log and Bob appends to the Bob-to-Alice log. Each log has a JSON array of signed protocol messages. The other peer reads and processes new valid entries. This simpler representation follows the user's suggestion in our design discussion.

Keep a trustline descriptor and derived view, but do not let concurrent assignments to a shared `balance` or `status` field decide settlement. Each node runs a serialized local protocol actor that validates messages and owns its reservations and decisions. A separate Resource for every message is an optional representation, not required for correct delivery.

This can remove the need to build a separate HTTP message-delivery mechanism. It does not remove the LedgerLoops settlement state machine or automatically replace its transactional storage. Native nodes can meet over Iroh, browsers can meet over WebRTC, and an AtomicServer can provide an optional always-online meeting point. Closed browsers cannot run unattended clearing.

## Relationship to SNAP half-ledgers

The user's earlier [SNAP overview](https://github.com/ledgerloops/snap-checker/blob/79c1d129ee4ba358587b53c3306617dc62aa2139/README.md) describes a `ChannelWatcher` combining two directional `SimplexWatcher`s, each accounting for committed and pending transfers. Its [protocol notes](https://github.com/ledgerloops/snap-checker/blob/79c1d129ee4ba358587b53c3306617dc62aa2139/protocol.md) distinguish proposal receipt (`Proposing -> Proposed`), acceptance/confirmation (`Accepting -> Accepted`) and rejection/confirmation (`Rejecting -> Rejected`). This is conceptual lineage, not a claim that the historical code or its timing rules have been validated for reuse.

The proposed Atomic logs are authored by sender. Alice's log contains both proposals she makes and replies to Bob's proposals; Bob's log does the converse. These two outbound logs carry evidence for the two directional transfer half-ledgers, but a log is not itself just the list of transfers proposed in one direction. A reducer consumes the relevant messages from both logs to calculate each half-ledger and the bilateral state.

The baseline to discuss is bilateral acknowledgment of each transaction's exact identity, amount, unit, condition and predecessor/terms. Alice's signed proposal and Bob's signed acceptance can express both parties' consent; a final confirmation establishes the proposer's observation rather than asking Alice for the same consent again. Rejecting a proposal is a separate outcome. Acknowledgments must not require an endless acknowledgment-of-acknowledgment exchange.

Atomic synchronization acknowledgments establish transport/storage progress, not necessarily application processing, acceptance or financial finality. Existing SNAP receipt/confirmation phases might remain explicit log entries or be represented partly by durable processed-frontier acknowledgments/checkpoints. That simplification requires an explicit state machine and recovery argument; it is not implied by Atomic having delivered a Commit. Conditional loop fulfillment still follows its reserved, consented hashlock transition rather than a fresh manual decision at each retransmission.

## Design questions for the next discussion

- **Agreement boundary:** choose the exact point at which proposal plus counterparty acceptance binds the bilateral ledger, what the proposer confirmation establishes, and when each party moves an amount between pending/reserved and accepted balances. Keep replica convergence and application finality distinct.
- **Who acknowledges:** define whether each transaction needs a fresh human action, an agent applying a previously approved policy, or delegated hosted execution. Two-party agreement does not inherently mean two people clicking on every message. Do not silently turn existing manual consent into automatic approval.
- **Writer authority:** choose which actor can emit binding messages for each half-ledger. Browser-to-Heroku sync can carry device-authored drafts to a hosted authority that serializes admitted transactions. Giving the browser and Heroku the same signing key and simultaneous offline writer rights does not prevent double-spending. Offline binding writes would require a separate allocation/fencing design.
- **Use of Atomic evidence:** decide whether independent message signatures remain the default or a stricter retained-Commit proof mode could serve the same purpose. Both must cover exact business meaning after batching, snapshot replication and recovery; the existing snapshot-trust path does not by itself prove every author's consent.
- **Depth of integration:** start with Atomic Resources as the persistent/synchronized half-ledger representation and state views. Decide separately whether the deterministic reducer and crash-safe reservation/state/outbound-intent updates should move into `atomic_lib`. Keeping SQL initially is an implementation option, not the product objective.
- **First useful exercise:** synchronize one participant's browser with its hosted node, demonstrate offline viewing and queued requests, and make pending versus accepted state visible. Then exercise two-party acknowledgment and recovery, followed by three-peer conditional loop resolution. Record both useful behavior and Atomic API gaps; this is not contingent on first proving a full backend migration.

## Existing implementation facts

- [Atomic's outbox](https://github.com/ontola/atomic-server/blob/6c2fc2347f01871056c91a80f3a936ce9cc9905b/lib/src/sync/outbox.rs) tracks dirty subjects and can sign/coalesce their changes at drain time. Retained appended messages remain in the synchronized list even when several appends travel in one Commit. Coalescing is a concern when messages are overwritten or deleted before receipt, not a reason to require one Resource per message. A sync acknowledgment is not a counterparty receipt.
- The TypeScript [Resource API](https://github.com/ontola/atomic-server/blob/6c2fc2347f01871056c91a80f3a936ce9cc9905b/browser/lib/src/resource.ts) provides `pushListItem(property, item)` for native Loro-list appends to JSON-array properties. The Rust [Loro wrapper](https://github.com/ontola/atomic-server/blob/6c2fc2347f01871056c91a80f3a936ce9cc9905b/lib/src/loro.rs) also supports JSON-array list items and append operations. A JSON array of message objects does not require separate message Resources; Atomic's `resourceArray` datatype instead represents resource references.
- [Peer sync](https://github.com/ontola/atomic-server/blob/6c2fc2347f01871056c91a80f3a936ce9cc9905b/lib/src/sync/engine.rs) can import snapshots using drive/replica trust. Signed envelopes are checked separately; a rejected optional envelope does not reject the imported snapshot. Protocol authorization must not treat materialized fields as independently signed evidence.
- [Envelope retention](https://github.com/ontola/atomic-server/blob/6c2fc2347f01871056c91a80f3a936ce9cc9905b/lib/src/envelopes.rs) defaults to the latest envelope. The application must retain the evidence it needs rather than assume every historical commit is available indefinitely.
- [AtomicNode](https://github.com/ontola/atomic-server/blob/6c2fc2347f01871056c91a80f3a936ce9cc9905b/lib/src/runtime/node.rs) supplies local saves, outbox access and ingestion policies. Its current application surface does not expose a general multi-resource settlement transaction. A save followed by outbox marking must not be assumed to atomically include arbitrary application state changes.
- The [public LedgerLoops protocol](https://github.com/ledgerloops/strategy-pit/blob/72d364f382aa9ef669a85229a50ee0822e108402/app/private_protocol.md) commits local state transitions, inbox deduplication and outgoing messages together. It uses neighbor-private hashlock messages and promises local receipt evidence, not Byzantine-safe global finality. Preserve that scope.

## Resources and identity

| Resource/state | Purpose and ownership |
| --- | --- |
| Trustline descriptor | Names both logical peers, unit, protocol version and incarnation. One peer proposes it; the other explicitly accepts its hash. The accepted agreement defines each party's obligations and limits. |
| Alice-to-Bob log Resource | Alice writes, Bob reads. Its JSON-array property contains Alice's signed offers, acceptances, probes, approvals, fulfillment and other protocol messages to Bob. |
| Bob-to-Alice log Resource | Bob writes, Alice reads. The matching sender-owned JSON-array message log. |
| Trustline state cache | Each peer maintains its current balance, credit/comfort revisions, pending reservations and processed log frontiers. It can be a sibling property on that peer's outgoing log Resource or a separate sender-owned view. It names the evidence it summarizes; editing it does not authorize a ledger transition. |
| Agreed checkpoint | Both peers acknowledge the same canonical trustline state and exact log prefixes. A validated checkpoint plus the log suffix avoids replaying years of history. |
| Private actor state | Local balance projections, reservations across trustlines, processed message IDs, decisions, secrets and durable outbound work. This state is not synchronized to counterparties. |

Use ordinary minted Atomic Resource IDs. Bind both peers to one agreed application `channelId` and descriptor hash; do not assume that independently minting Atomic Resources deduplicates the same trustline. Include a new incarnation when intentionally replacing a channel. Preserve mappings to existing LedgerLoops node identities when introducing Atomic Agents.

For an initial deployment, use two directional, pair-specific publication scopes, ideally separate Drives: Alice publishes events to her stream and Bob reads it; Bob publishes to his and Alice reads it. Restrict authoring and validate expected authors at the protocol layer. Do not grant every neighbor write access to the node's other trustlines or private state. Establish and pin the expected pair and bootstrap roots explicitly.

ACLs and transport admission remain required, but ACLs alone do not prove the validity of a settlement event. Verify application signatures even when a drive owner or relay can deliver a snapshot containing arbitrary fields. The exact read-only receiver/bootstrap path and pairing UX require integration tests.

## Appending and consuming the logs

Each message is a list item containing its canonical payload and application signature. Use native list append operations, then persist the Resource through the normal local-save path. Preserve the Resource's existing Loro document and list lineage. Do not rebuild it from an array on every reload, repeatedly replace the whole array, overwrite an earlier message's status, or treat an ephemeral presence channel as durable protocol delivery.

Only one logical actor appends to each log. Each entry binds a per-sender sequence number, previous-entry hash, message ID and channel incarnation. The receiver verifies the next contiguous signed entry, persists its processing decision and cursor together with any outgoing intent, and resumes from that durable point after restart. An array index may optimize scanning but is not the sole identity or recovery checkpoint. A notification is a prompt to inspect the log, not proof that exactly one new message arrived. Process all unseen valid entries; repeated notifications, replayed entries and batched delivery are normal. A duplicate of an already verified message is a no-op; different signed messages claiming the same sender sequence require equivocation handling.

The two logs have independent sequences. Acknowledgments, acceptances and phase transitions refer to the particular message/proposal or quote hash they answer. Do not infer one global order from array positions across both logs, Loro timestamps, or arrival order.

Append-only is a protocol rule, not a property granted by a write ACL. A writer can technically edit or truncate its Resource. Verify payload signatures and the accepted hash chain, retain already accepted evidence locally, and quarantine changes that contradict it. Detecting a missing suffix requires a previously known checkpoint or additional evidence; a hash chain alone cannot prove that an unseen message was never withheld.

Start with two logs and no destructive pruning. Long-running channels need the state/checkpoint design below and a bounded retention policy: rotate to hash-linked log-segment Resources before snapshots or frame limits are exceeded, and agree checkpoints/receipts before discarding old data. Preserve unfinished settlement evidence and restore protection. Segmentation and compaction are proposed work, not implemented capabilities.

## Current state, updates and checkpoints

The logs are the record of messages, not the only way to read a trustline. Maintain a durable current-state cache so normal reads do not replay years of entries. For each channel it records:

- Channel/incarnation, unit and canonical balance orientation; for example, positive means Bob owes Alice. Bob's own display negates balances and swaps directional reservations.
- Applied balance, each party's credit grant and preference revision, personal comfort intervals, derived shared comfort interval and assistance policy.
- Outstanding reservation IDs, signed deltas, pinned terms/condition, phase and release evidence; plus separate capacity totals in each direction. Reveal only this relationship's necessary state, not another trustline or an unreleased preimage.
- Accepted checkpoint/state hash, both processed log-prefix sequence/hash pairs and the local actor revision. Persist private decision/deduplication and outbound-intent state atomically alongside its corresponding local transition.

Ledger-update messages should contain the resulting values that changed, not merely an instruction to infer them from the distant past:

| Message | Signed resulting state and context |
| --- | --- |
| Balance update | Proposal/reservation ID, exact `before`, signed `delta`, resulting `after`, and base state/quote hash; verify `after = before + delta` and the required consent/fulfillment evidence. |
| Credit or comfort update | The author's complete new credit/preference values and new revision, including current comfort endpoints and assistance setting, with its prior revision. Send the resulting values for the fields being changed; omission does not reset other fields. |
| Reservation/release | ID, signed delta, pinned term revisions and condition/phase; the sender may include resulting reservation totals for the stated state cut, but the receiver verifies them against individual entries. |

A sender-signed post-state is an assertion about that sender's evidence and state cut. It is not a last-writer-wins replacement for the recipient's ledger. Validate the message against its expected predecessor and protocol rules. A preference message carrying a cached balance does not authorize a balance change. Two concurrent updates based on the same old balance cannot each install their absolute `after` value; use the existing serialized quote protocol initially. Any future parallel protocol must define how fixed, uniquely applied deltas and their evidence produce the post-state.

Periodically propose a checkpoint containing the canonical shared trustline state, both included log-prefix hashes, preference revisions and previous checkpoint hash. Exclude private actor revisions, deduplication internals, outbound intents and secrets; those stay in each node's durable local cache. Both peers sign/acknowledge exactly the same checkpoint hash. Initially checkpoint only when there is no unresolved settlement on that trustline; covering pending work later requires retaining its complete reservations, phase and recovery evidence. Each included cut must cover the dependencies used to derive its state, not an arbitrary pair of sequence numbers.

A restored or newly authorized device validates the checkpoint and then processes the suffix. Existing devices retain their latest accepted checkpoint/epoch to detect rollback; a fresh device still needs a trusted way to select a current checkpoint, since signatures alone do not prove recency. Historical signatures can remain archived separately. Pruning must retain the checkpoint, necessary audit evidence and everything required to finish or reject outstanding work. A unilateral latest-state cache is useful for display, but is not a mutually agreed recovery checkpoint.

## Reservations and credit bounds

Capacity must be reserved when a proposal becomes binding, before publishing consent that the peer may act on. A discovery probe alone does not reserve capacity. Track reservations individually by ID; an aggregate `reservedAmount` alone cannot establish which decisions may release it or prevent double counting.

Use canonical signed balance `b` and hard credit bounds `[L, U]`. If Alice grants Bob credit `C_A` and Bob grants Alice credit `C_B`, with positive balance meaning Bob owes Alice, then `L = -C_B` and `U = C_A`. For unresolved proposals with fixed signed deltas `d_i`, maintain gross directional reservations:

```text
R_plus  = sum(max(d_i, 0))
R_minus = sum(max(-d_i, 0))

b - R_minus >= L
b + R_plus  <= U

available_increase = U - b - R_plus
available_decrease = b - L - R_minus
```

These conditions cover every independently possible subset and order of commitments, not only the outcome if all proposals commit. Do not net opposite reservations against one another. With `b = 5`, bounds `[0, 10]` and proposals `+4, +4, -4`, all committing gives `9`, but the two positive proposals alone reach `13` if the negative one aborts or arrives later. Admission must reject that reservation set.

Both endpoints check admission using all their held commitments, including outbound proposals whose outcome is not yet known. Canonical reservation IDs ensure local and remote copies of one proposal are counted once. A valid commit atomically applies its delta, marks that ID consumed, and removes the matching directional reservation. A valid abort releases the reservation without changing balance. Those transitions preserve the capacity inequalities when the admitted balance starts within fixed bounds. Replays are no-ops; losing a message, restarting or reaching a local timeout does not release binding capacity.

New ordinary balance changes must account for existing holds too. A tighter effective credit bound must not silently invalidate them. Preserve the current policy that rejects local preference edits on reserved contacts and defers incoming updates until settlement resolves; pin both preference revisions in consent. Broadening concurrency or allowing limit changes during holds requires a separately specified admission rule.

There is an existing compatibility exception: [the current app](../../app/COMFORT.md) allows a credit grant to be lowered below existing exposure without forgiving that debt. Therefore `b` need not always be within the latest nominal bounds. Display the excess explicitly, prohibit new/increased excess and permit only the existing policy-approved exposure reductions. Do not claim the strict inequalities above for such a channel until it re-enters bounds, or change the current grant-reduction behavior implicitly. A different mode that defers activating an infeasible lower limit would be an explicit protocol/product change.

Credit-capacity safety is also distinct from comfort consent. For a comfort target of zero, two separately quoted moves of `-4` from `b = 5` each predict `5 -> 1`; applying both gives `5 -> 1 -> -3`, and the second step worsens discomfort. Directional headroom alone does not make those quotes valid together. Keep one prepared settlement per trustline initially, as required by the [current comfort protocol](../../app/comfort_protocol.md), with unchanged reserved balances and exact pinned quotes. Multiple outstanding prepared settlements require a new consent/quote design in addition to the reservation arithmetic.

## Discovery can be ephemeral; commitments cannot

Loop-finding probes and tentative search paths can be short-lived if losing them creates no financial obligation and discovery can safely restart. Keep them outside the durable hash-chained ledger log if they may disappear: use a verified ephemeral transport path where available, or separate short-lived discovery resources. Do not put a disposable probe in the middle of the durable sequence and then require it to verify later ledger messages.

Once state is used to bind a counterparty, reserve capacity, record approval/readiness or release/forward fulfillment, retain the necessary state and messages durably. Prepared proposals, pinned quotes, reservations and irreversible decisions cannot be treated like presence. Short-lived probes still need authentication, stale-search rejection, deduplication and rate limits; they do not expose remote routes or full loop membership.

## Signed event envelope

Define canonical signed bytes with a LedgerLoops-specific domain separator. Include protocol version, channel/incarnation, sender and recipient identities, sender sequence, previous-entry hash, a unique message ID, message kind and its payload. Bind proposal IDs, exact unit/amount, condition and the relevant previous accepted-state or quote hash where the transition requires them. Local before/after quotes remain local to the participant and its existing consent rules.

Use an explicitly specified exact numeric representation across Rust and JavaScript. Preserve the public protocol's context-bound hashlock construction unless introducing a separately versioned protocol change. Routing and delivery metadata must not change signed business meaning.

Each message carries its own application signature over these bytes, in addition to the Atomic Commit carrying the list append or batch of appends. This makes evidence verifiable after snapshot replication, delayed delivery or commit-envelope pruning. Using an Atomic Agent key for this requires an explicit domain-separated signing API and key policy; it is proposed application work, not an existing LedgerLoops event API.

Treat signed payloads as immutable at the protocol layer. Verify the signature, expected author, context and transition before using them. An edit to a payload under the old signature is invalid. Conflicting valid signatures from the same logical sender must be detected as equivocation, not resolved by a Loro winner. Maintain an event-ID/hash registry and predecessor/checkpoint evidence; fork detection and recovery rules must be specified before production.

## A two-peer trustline update

1. Alice's local actor validates a proposed transition against the accepted trustline state and all relevant reservations. It durably records the proposal, its own consent and any held capacity, then schedules a signed offer message in her outgoing log referencing that exact state and quote.
2. Atomic Sync makes the event available to Bob, immediately or after reconnection. Bob's actor verifies evidence and context before considering it. Transport delivery is not acceptance.
3. Bob approves only after verifying the expected state, his own limits and local reservations. He durably records his decision and appends a signed acceptance of the exact proposal hash to his outgoing log. A refusal is a separate message, not an edit to Alice's offer.
4. Each actor derives the next accepted state from the required consent evidence and applies it once. An observer with only the offer displays it as pending. An acknowledgment can confirm observation; it is not an additional consent requirement unless the protocol specifies that.
5. Reservations are released according to the protocol decision. A published consent that the other side can still accept cannot be withdrawn merely because a local timer expired. Cancellation/withdrawal races need an explicit agreed rule. For the first prototype, retain committed reservations until acceptance, rejection or a mutually valid cancellation resolves them.

The signed proposal and acceptance establish bilateral agreement. They do not provide simultaneous visibility or an atomic transaction across devices. Repeated delivery, gaps and reordering must be handled by message IDs and expected-state checks. A message awaiting dependencies stays pending; do not use receipt order or a CRDT timestamp as settlement order.

## Multi-party loop clearing

Carry the existing neighbor messages as events rather than broadcasting one global loop Resource:

| Existing phase | Adaptation |
| --- | --- |
| Probe / probe rejection | Pairwise discovery carrying the existing opaque proposal ID, condition and fixed amount. It may be ephemeral only before it creates a durable protocol obligation; preserve any bound-neighbor state needed by later phases. |
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

1. **Initial adapter:** keep the existing transactional store/actor, and append its durable outbound messages to the correct outgoing log Resource. Reuse stable signed message IDs and sequence numbers during crash recovery. If a crash makes it uncertain whether an append succeeded, replay must not become a second business operation; the publisher inspects existing entries and the receiver deduplicates by message ID. Atomic becomes the peer message carrier; PostgreSQL or SQLite remains local protocol storage.
2. **Atomic-only actor:** implement and test a durable actor aggregate and outbound intent together in `atomic_lib`. One possible design stores local decisions and pending signed messages in one private aggregate, then projects them idempotently into outgoing logs. Another adds a dedicated atomic storage operation. Neither is implemented by this document, and both need API and crash-consistency review before removing the SQL store. Private actor data must never leak through the public log projection.

Run one fenced logical settlement writer per node. The same Agent key active on two offline devices does not provide mutual exclusion. Devices may submit requests, but failover requires a deliberate epoch/fencing and recovery design. Do not let CRDT merging silently choose between conflicting reservations. Existing event evidence and peer checkpoints must prevent replaying a stale backup as a fresh accepted state.

## Implementation and verification checklist

- [ ] Confirm the hosted LedgerLoops protocol/schema and define the exact compatibility target.
- [ ] Review the historical SNAP half-ledger lifecycle and choose transaction consent, receipt and final-confirmation boundaries without assuming historical implementation correctness.
- [ ] Specify manual versus delegated acknowledgment and the browser/hosted writer-authority boundary for the initial browser-to-Heroku exercise.
- [ ] Specify descriptor handshake, canonical message bytes, sender sequences/hash chains, identity mapping, exact amounts, signature verification and accepted-state transitions.
- [ ] Specify current-state caches, signed post-state fields, agreed checkpoint cuts, trusted bootstrap/restore freshness and archival/retention policy.
- [ ] Verify directional reservation bounds for arbitrary commit/abort subsets and orders, exact-once release, lowered-limit excess and pinned preference revisions.
- [ ] Preserve exclusive prepared comfort quotes initially; separately specify any concurrency extension and its consent rules.
- [ ] Separate restartable ephemeral discovery from durable prepare/readiness/fulfillment obligations.
- [ ] Specify cancellation races, equivocation handling, checkpoints, event retention, writer fencing and recovery.
- [ ] Implement a deterministic local actor and two-log Atomic publisher/receiver, initially retaining transactional storage.
- [ ] Verify pair-specific Drive bootstrapping, authenticated sync, ACLs, invalid snapshots/payloads and relayed delivery.
- [ ] Test duplicates, reordered/missing events, two offline proposals spending the same capacity, and multiple devices sharing an Agent.
- [ ] Verify multiple appends delivered in one Commit, durable receive cursors, edited/deleted entries, withheld suffixes and log-segment rotation before size limits.
- [ ] Inject crashes before/after local decisions, publication and receipt; verify conserved balances, reservations and recoverable forwarding.
- [ ] Exercise three-party fulfillment, creator departure, offline readiness, conflicting abort/fulfill messages and replay after restore.
- [ ] Choose supported transports and test actual browser/native paths, including no always-online replica and delayed availability.
- [ ] Decide whether an Atomic-only durable actor is justified after the adapter passes these tests.
