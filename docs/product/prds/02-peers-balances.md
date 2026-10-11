# PRD 02 — Peers, obligations and reconciled balances

Status: draft for implementation planning, 11 October 2026. Owner: product + client/integration (roles, not assigned people). Parent: [product roadmap](../../product-roadmap.md). Related: [identity and hosting](01-identity-hosting.md).

## Outcome and users

A participant can invite a known trading peer, inspect their own obligations, reconcile disagreements and understand which balances may enter clearing. A community bookkeeper can import records into an authorized workspace and resolve import errors without making an invoice appear mutually agreed merely because it was uploaded.

The interface speaks in “You owe Sam 7” or “Sam owes you 7”, avoiding unexplained signed numbers. It shows the agreed unit and the last reconciled revision. A participant sees their own relationships, not a community-wide credit graph.

## Release boundary

**Read-only alpha:** entry/import into a separate preview ledger, peer acknowledgement of proposed records, comparison with existing books and a read-only eligibility view. Label acknowledgements as agreement about the preview data, not a legal settlement or a write to accounting books.

**Testnet:** versioned bilateral statements, authenticated peer identities, concurrent updates and recovery fixtures using test units.

**Gated live pilot:** agreed rules for authoritative books, eligible obligation types and bilateral posting; signed versioned records and audit history. Manual clearing approval remains a separate workflow. Zero-balance invitation relationships may remain in the address book, but do not authorize fresh discovery traffic.

Out of scope: public peer search, credit scoring, currency conversion, new lending, automatic netting of disputed invoices, bank transfers and Headroom restoration permissions.

## Requirements

| ID | Requirement and release |
| --- | --- |
| PB-01 | All: display each peer, unit, own-perspective balance, reconciliation status, available amount and any reserved amount separately. Never label reserved or proposed clearing as completed. |
| PB-02 | Alpha: invite a known peer with an expiring, revocable, single-use token; show verified identity details before binding. A display name alone cannot authenticate the peer. Prevent self-links and duplicate peer/unit relationships. |
| PB-03 | Alpha: let both sides inspect a proposed opening balance and underlying references. Acceptance binds the exact statement version; an edit invalidates prior acceptance. Disagreement blocks clearing eligibility. |
| PB-04 | Alpha: provide a documented CSV template and preview each import before saving. Require source identity and record identity for deduplication; repeated identical imports create no duplicate obligations. Conflicting repeated IDs require review. |
| PB-05 | All: use integer minor units and a fixed declared precision. Reject unknown units, excessive precision, overflow, invalid dates and malformed rows without silent rounding or guessed currencies. |
| PB-06 | All: preserve source invoice/transaction history. Corrections append a superseding record or reversal with reason; never overwrite an accepted statement or erase a completed settlement. |
| PB-07 | Alpha: show eligibility reasons per balance: unreconciled, disputed, unsupported terms/unit, reserved, paused, zero or ready. Agreement to a balance is not approval of a future clearing proposal. |
| PB-08 | Testnet/live: post bilateral updates only through versioned authenticated acknowledgement. A stale revision yields a reconciliation flow, never last-write-wins accounting. Posting affected by a reservation stays pending and visible. |
| PB-09 | Testnet/live: new external transactions establish a live communication episode once agreed/posted; reaching zero closes fresh discovery permission. Retain recovery/control traffic for admitted settlements and retain receipts/history. |
| PB-10 | All: support a dispute reason and evidence reference with limited access. Exclude disputed amounts from clearing under the pilot's eligibility policy; do not settle them merely to simplify a net balance. |
| PB-11 | All: export own records and agreed statements in a documented machine-readable format plus a human-readable view. Include mode, unit, revisions, provenance and status so preview data cannot be mistaken for posted accounting entries. |
| PB-12 | Live: bind due dates, discharge/offset terms and authoritative ledger choice to the agreement version. Where eligibility cannot be determined, require review rather than treating all invoices between peers as fungible. |

## Primary screens and flow

**Peers:** rows show “You owe …” / “… owes you”, unit and a status badge. Separate gross amounts owed and receivable; their signed difference is the participant's net position, not cash available. A paused/offline peer is visibly distinct from an unreconciled balance.

**Peer detail:** agreed balance at revision, obligation history, reservations/pending updates, eligibility reason, identity confirmation and invitation/dispute actions. Show a timestamp for stale data. Clearing approvals link to a separate proposal view.

**Import:** select a source/template → upload → validate and deduplicate → preview accepted/error rows and totals → explicitly save selected valid rows as proposals. No hidden partial commit. An all-or-nothing option is the default; an explicit partial import must list excluded rows in its receipt.

**Reconcile:** compare “Your proposed statement” with “Peer's statement”, inspect differences and choose accept exact version, propose correction or dispute. Do not expose unrelated peer records.

## States and error handling

Invitation: `created → delivered/awaiting_peer → accepted`, or `expired/revoked`. Delivery does not prove acceptance. Retrying acceptance returns the existing relationship when valid; a token cannot bind a different account after use.

Statement: `draft → awaiting_peer → agreed`; disagreement becomes `disputed`; replacement becomes `superseded`. An agreed statement can be superseded only through a new agreed version. Operational relationship state (`active`, `paused`, `zero_balance`, `reconciling`) is separate from the invitation and individual obligation states.

An obligation has provenance and eligibility state; a posting has `proposed`, `pending`, `posted`, `rejected` or `uncertain`. Uncertain writes require recovery, not blind resubmission under a new ID. A conflicting revision returns the current authorized revision and a comparison, not another participant's private data. Missing peer acknowledgement stays pending. Imports preserve row-level errors and original input identifiers for correction without duplication.

## Conceptual data and API contracts

- `PeerRelation {id, localNodeId, peerNodeId, unitId, status, episodeId?, agreedRevision?, lastObservedAt}`. Unit is immutable for a relation; another unit needs a separate agreement and is deferred for the pilot UI.
- `Unit {id, label, minorUnitScale}`. Serialize amounts as decimal integer strings to avoid JavaScript precision loss; enforce a documented bounded integer range in every layer.
- `Obligation {id, relationId, sourceId, sourceRecordId, amountMinor, direction, issuedAt?, dueAt?, evidenceRef?, termsVersion, eligibility, supersedesId?}`. `direction` is explicit relative to the local participant.
- `BilateralStatement {id, relationId, revision, previousStatementHash?, localBalanceMinor, obligationDigest, termsVersion, acknowledgementRefs[], mode}`. Positive local balance means the peer owes the local participant; the peer view has the opposite sign. A preview acknowledgement must be distinguishable from a protocol signature.
- `ImportBatch {id, sourceId, inputDigest, parserVersion, mode, rowResults[], status}`. Uniqueness is workspace/source/source-record ID; changed content under the same ID is a conflict. File hashes alone cannot deduplicate the same rows in different files.
- `ReservationView {transactionId, relationId, amountMinor, state, observedAt}`. Computed availability derives from the settlement core; the UI cannot unlock a reservation.

Proposed operations: `POST /peer-invitations`, `POST /peer-invitations/{id}/accept`, `GET /peers`, `GET /peers/{id}/statements`, `POST /imports/preview`, `POST /imports/{id}/confirm`, `POST /statements/{id}/acknowledge`, `POST /disputes`. Writes require authenticated workspace scope, idempotency keys and expected revisions. Signed acknowledgements bind mode, both peer identities, unit, statement digest and terms version, with protocol-defined replay protection.

Import parsing must be sandboxed/bounded by file size and row limits. Exports escape spreadsheet formula prefixes; source text is never rendered as HTML. Numeric totals include only clearly identified status groups and may not mix units.

## Privacy and accounting boundaries

Do not upload an entire cooperative ledger into every node. Imports scoped to a participant must reject or segregate unrelated rows; any bookkeeper access requires explicit delegation. Evidence documents may contain commercial or personal data: expose references only to authorized parties and avoid attaching them to search messages. Invitations and balances never enter analytics logs or notification previews by default.

A balance aggregates obligations only under agreed terms. Reducing the displayed total does not erase invoices, establish tax treatment or prove a bank payment. Read-only exports carry a prominent “preview — not posted” marker. Live entry mappings and retention policy require review with the pilot's bookkeeper before authoritative use.

## Acceptance evidence

- **PB-A1:** import a fixture twice and then import the same records reordered/renamed: counts and totals remain unchanged. A changed amount under an existing source ID yields a conflict with no silent overwrite.
- **PB-A2:** missing units, fractional excess precision, oversized integers, formula-like text and malformed rows yield safe deterministic results. Import/export round trips preserve exact integer amounts and provenance.
- **PB-A3:** two peers accept revision 4; editing to revision 5 invalidates the old acceptance. A request for revision 4 cannot approve revision 5. Opposite peer views have equal-magnitude, opposite-sign balances.
- **PB-A4:** disputed, unreconciled, paused and zero balances are excluded from fresh discovery by the node, even when a client directly calls the API. Recovery traffic for admitted transactions remains available at zero.
- **PB-A5:** a transfer arriving during reservation is visibly pending or handled by the specified core transition; it is never omitted from totals or reported as posted early. Duplicate retries create one posting.
- **PB-A6:** at least five alpha users can distinguish owed/receivable, agreed/proposed and available/reserved amounts; they can reconcile a mismatch and explain that the preview has not updated their books.
- **PB-A7:** unauthorized workspace/peer IDs reveal no relationship, evidence or balances. Export contains only the authorized participant's records and distinguishes preview acknowledgements from signed protocol records.

## Dependencies and open decisions

Depends on identity binding and workspace modes (PRD 01), settlement-owned reservations/revisions, receipt/export formats and an authoritative-ledger adapter. The alpha can use deterministic mock adapters that are explicitly marked as such; live bilateral state cannot use the simulator's atomic paired-state shortcut.

Before alpha: choose the first accounting unit/precision, CSV template, invitation confirmation method and pilot eligibility policy. Before testnet/live: fix signed statement encoding, obligation-to-balance reconciliation rules, pending-post behaviour, retention periods and treatment of partly disputed obligations. Resolve whether the pilot permits offset across different due dates; absent agreement, treat those records as ineligible. Keep automatic reconciliation and multiple accounting-system integrations out of the first implementation.
