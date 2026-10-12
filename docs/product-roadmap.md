# From Strategy Pit to a usable LedgerLoops

Status: proposed product roadmap, 11 October 2026. These are delivery gates and planning estimates, not claims that the research prototypes are production ready. [Research status](research-queue.md) remains the record of experiments.

## The first useful product

Help a small cooperative, community exchange or group of independent traders reduce outstanding mutual debts without requiring everyone to pay cash first. Start with one existing community, one accounting unit and roughly 10–30 consenting participants. Validate that they actually have reciprocal obligations and cycles before building for them.

The promise: **see what you owe, agree what can be cleared, and keep a receipt you and your peer can verify.** People should be able to run their own node or deliberately delegate hosting. Joining should not require understanding a graph algorithm.

First validate this with a clickable demo and a read-only clearing assistant. Participants import or enter obligations, reconcile them with their peers, and see proposed before/after balances. Nothing changes in their authoritative books during this phase. A lack of useful cycles, disputed balances or unacceptable counterparties can invalidate the product even if the algorithm performs well.

## A participant's journey

1. Create an identity, choose self-hosting or a clearly explained hosting provider, and set up recovery.
2. Invite a known peer and agree the unit, balance and terms of each obligation. An imported invoice is a proposal until acknowledged; deduplicate imports and identify the authoritative ledger.
3. See a proposal in plain language: “You owe Bob 7; this clears 3, leaving 4. Your net position stays the same.” Show the participant's own incoming and outgoing changes and any conditions, rather than exposing the community's whole graph.
4. Approve once, or later opt into automatic clearing within explicit per-peer and daily limits. Outstanding approvals bind exact balances, revisions, amounts and policy versions; changed proposals need fresh authority.
5. See separate proposed, reserved, pending and completed states. Export a receipt and accounting entries. Disputed or ambiguous settlements remain visible and block conflicting changes.
6. Pause new clearing, reconcile outstanding work, export data and leave. Pausing cannot revoke an already irrevocable settlement; the interface must explain that boundary.

Clearing changes obligations; it does not itself transfer bank money, forgive an unmatched debt, or guarantee repayment. Preserve invoice history and record the agreed discharge or adjustment separately. Participants need agreement about which obligations can legally and practically be offset, including due dates, disputes and tax/accounting treatment.

## Product scope and algorithm choice

Ship cancellation-only clearing first: a participating debt can decrease towards zero, each completed cycle preserves every participant's signed net position, and fresh search stops when a peer balance reaches zero. Keep recovery/control communication available for already admitted settlements.

Use random node-local DFS as the initial reference policy. In the completed single-seed, full-prefix temporal Sarafu comparison it clears more than Numbat in all three tested conditions. Numbat has message-cost advantages under faults and gains on synthetic graphs; neither is a universal winner. [Replication](../experiments/TEMPORAL-EPISODE-REPLICATION.md) is testing additional seeds. Keep discovery replaceable behind a common settlement interface; a product should not depend on finding the final animal.

Headroom is a later, explicit opt-in experiment. Original balances are not perpetual consent to restoring debt. Require fresh, versioned bilateral limits and explain changes in counterparty exposure, even when a participant's net position is unchanged. Concurrent Headroom currently works mechanically but has not earned promotion on measured cost and clearing results.

Defer multiple currencies, exchange rates, open anonymous membership, lending, bank payment initiation and token issuance. Each changes the accounting or threat model substantially.

## Neighbour-private hashlock architecture gate

[Issue 004](issues/004-neighbour-private-hashlock-settlement.md) is a required protocol workstream: participants know only direct neighbours, without an enumerated loop or exact total length beyond the minimum of three. The current HTTP/SQLite app is an honest-peer infrastructure prototype with path lists and origin-collected votes; it does not validate the original LedgerLoops protocol. A preimage check added to that design is insufficient.

Before claiming the original protocol is restored, investigate and independently review discovery, conditional bilateral consent, locally verifiable hashlock fulfillment, completion evidence and durable recovery under this knowledge boundary. Resolve minimum-three enforcement and safe cancellation/expiry without a membership-enumerating coordinator. Document timing/transport/collusion leakage and safety/liveness assumptions; do not promise absolute anonymity. Build a separate versioned candidate and define pending-work migration before integration. This is a gate within stage 2, preceding any live-pilot claim for the neighbour-private product.

The separate [private v2 testnet](../app/private_protocol.md) now implements this candidate under honest-peer assumptions, with local-view privacy audits, hashlock receipts and selected crash/replay tests. It does not add safe deadline expiry, hostile-peer protection or production identity. The legacy route-visible implementation remains isolated; no pending state is migrated. Further security and operational work remains part of stage 2.

## Architecture and the missing engineering

Each node stores only its own peer balances, permissions, reservations and journal. Discovery and acceptance use direct-neighbour messages. A relay can deliver encrypted envelopes; it must not choose routes or approve clearing from a global graph. Relays and hosting providers still see metadata, and a host controlling signing keys is trusted: document these facts instead of claiming graph privacy from locality alone. The current prototype discloses traversed relationships; eliminating its explicit route/membership disclosure is required by issue 004, while residual metadata leakage must be scoped separately.

Build a protocol core with a deterministic state machine and versioned wire format; a durable local database with transactional journal/outbox/inbox; an authenticated neighbour transport; an HTTP API and accessible mobile-friendly web interface. Keep the current Python simulations as executable references and conformance fixtures. Choose the production language after a small persistence/transport spike and maintainer review; reuse older repositories only after reviewing their current code and licences.

The simulator currently installs paired state atomically and assumes state-retaining sleep. Real peers have separate disks, can restart, lose state or equivocate. Replace that adapter before any authoritative balance changes. Define signed bilateral revisions, integer amount/overflow rules, idempotent transaction IDs, replay protection, key rotation, old-backup detection and safe receipt retention/compaction.

Specify the settlement decision and its recovery rules before selecting a mechanism. Durable preparation and an authenticated, recoverable commit certificate are candidates to evaluate; signatures or a timeout alone do not make a multi-party transaction atomic. A participant with uncertain outcome must retain its reservation and seek evidence. During an indefinite partition, safety may require waiting indefinitely. Never release a prepared balance merely because a timer expired while a commit could exist elsewhere. Define coordinator loss, conflicting certificates and malicious peers explicitly; cancellation-only discovery does not solve them.

An initial pilot may use a community-trusted settlement service if the community accepts that trust and it materially simplifies safe delivery. That would be an explicitly different settlement model, with node-local discovery still required; it must not be presented as the fully peer-operated protocol. Choose and document one model at the settlement-design gate.

## Delivery gates

Estimates assume two core engineers, part-time product/community support and independent security/distributed-systems review. They are rough elapsed ranges with overlapping work; discovery can stop or change the plan. No committed launch date or spending is implied.

| Stage | Deliverable and rough effort | Exit evidence |
| --- | --- | --- |
| 0 — Validate the need | 1–2 weeks: 5–8 interviews, one willing community, consented/anonymized sample ledger, clickable proposal/receipt screens | Participants understand the changes; community sees enough eligible clearing to justify adoption; agree authoritative books and success thresholds |
| 1 — Read-only alpha | 2–4 weeks: imports, bilateral reconciliation, proposal previews, exports, reproducible installation | At least five users finish the core flow without developer assistance; deterministic reconciliation; no authoritative writes; compare benefit and effort against existing manual netting |
| 2 — Durable protocol testnet | 4–8+ weeks: independent processes/databases, settlement specification, restart recovery, identity, API and end-to-end client | Independent review of trust/finality model; crash at every persistence/send boundary, duplicate/reordered messages, partitions, stale backups and incompatible versions tested; zero unexplained balance divergence or unauthorized changes |
| 3 — Shadow pilot | 2–4 weeks: replay actual arrivals beside existing books, human approvals, support and incident drills | Four weeks of reconciled daily results, tested restore/export, measured locked-balance duration and costs; participants accept the workflow; unresolved outcomes handled without fabricating finality |
| 4 — Capped live pilot | 4+ weeks after all previous gates: agreed small amounts, one community, staffed support, easy pause of new work | Signed participation/settlement terms and local legal/accounting review; zero unexplained discrepancies; useful clearing net of operating effort; no unresolved critical security findings |
| 5 — Wider release | Only after pilot evidence: documented self-hosting, maintained releases, interoperability tests and another independent community | Repeatable onboarding, sustainable support costs, demonstrated recovery and maintainers willing to operate the service |

Manual approval is a consent feature, not a substitute for the protocol safety gate. A live pilot must not silently use simulation settlement. Amount caps limit exposure but do not repair correctness.

## What to measure and when to stop

Track eligible obligations cleared, final outstanding debt versus a matched no-clearing replay, time with money locked, proposed-to-final latency, incomplete settlements, delayed incoming transfers, bytes/messages and infrastructure/support cost. Separate completed savings from temporarily reserved or staged amounts. Use offline MCF only as a research reference on appropriately consented data; it is not part of live node decisions.

Measure adoption too: time to first agreed peer, reconciliation disputes, proportion approving a proposal, repeat use and whether users can explain their receipt. Agree numerical latency/cost/value targets with the pilot community before the shadow trial; Sarafu percentages are not a customer promise.

Any unexplained divergence, unauthorized balance change or replayed settlement stops new live clearing and triggers reconciliation. A partition leaves affected transactions visibly pending; do not compensate automatically or rewrite settled history. An incident runbook must identify who supports recovery and how participants obtain their signed records if a host disappears.

## Ownership, sustainability and first backlog

Keep protocol specifications and a usable node implementation open source, with explicit licence review, reproducible releases and documented governance. Explore paid hosting, integration and community support after learning actual costs; validate willingness to pay rather than assume a fee per cleared debt. Minimize telemetry and collect aggregate metrics only with consent.

Proposed work streams (roles, not assigned people):

- **Community/product:** recruit a pilot partner, interview participants, define consent language and test proposal/receipt screens. Outreach needs a separately authorized contact plan.
- **Protocol:** write the failure/threat model and settlement state machine; decide peer-operated versus explicitly trusted pilot settlement; independently review it.
- **Runtime:** demonstrate three nodes on separate durable stores recovering from crashes, then extend to changing graphs and faults using the frozen research fixtures.
- **Client/integration:** agree a versioned balance/receipt/import schema, build read-only flows, then add approved writes after conformance passes.
- **Operations/review:** plan keys, backup/restore, upgrades, privacy, accounting treatment, incident response and a costed pilot budget.

The three-node infrastructure testnet and client now exist. A reviewed neighbour-private hashlock candidate now runs separately under issue 004. The next milestone is **broader failure/security validation and versioned bilateral transaction onboarding**, retaining the private protocol boundary; persistence tests alone do not close the production gate. Continue algorithm benchmarks in parallel; improvements should enter through the tested discovery interface without weakening settlement guarantees.

## Shared comfort-zone workstream

[Issue 005](issues/005-shared-comfort-zones.md) adds per-contact credit grants and personal balance ranges, mirrored/intersected into a shared zone. The [address book](../app/COMFORT.md) stores and synchronizes preferences; [serialized simulations](../experiments/COMFORT-SIMULATION.md) measure discomfort separately from debt. Integrating assisted adjustments into hashlock settlement requires versioned bilateral permissions, explicit zero-balance routing policy and recovery tests. Keep automatic execution disabled until that protocol work is validated.
