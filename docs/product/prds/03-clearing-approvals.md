# Clearing proposals and approvals

Status: draft for read-only alpha and gated testnet; 11 October 2026. Owner role: client and protocol. Parent: [product roadmap](../../product-roadmap.md). Companion: [receipts and recovery](04-receipts-recovery.md).

## Outcome and scope

A participant can understand an eligible cancellation, inspect its effect on their own peer balances, and give authority for exactly that change. A proposal is not a completed clearing. Discover routes using node-local neighbour messages; neither the client nor hosting control panel needs a community graph.

The alpha previews proposals using reconciled sample/imported data. “Try approval” records demo feedback only and is labelled “Demo — no books change.” Authoritative approval endpoints remain disabled. A separate testnet uses test units. Live approval ships only after the settlement design, durable recovery, security and capped-pilot gates in the roadmap pass.

Version one supports one accounting unit and cancellation only. Automatic clearing, Headroom, new borrowing, cross-unit conversion and bank transfers are outside this component's first release. Hosting a node does not itself grant authority to approve.

## Participant flow

1. Open a proposal from the balances screen or an invitation. Show identity, unit, exact changes, approval expiry and the freshness of the local node's data.
2. Read both sides of their change. Canonical fixture: Alice owes Bob 7 and Doris owes Alice 5. A cancellation of 3 leaves Alice owing Bob 4 and Doris owing Alice 2. Alice's signed net position remains −2. These are Alice's two incident edges of a larger eligible loop; those two edges alone do not establish that a loop exists.
3. Review eligibility/terms and choose “Approve this change” or “Decline.” Explain: “Approval permits this exact proposal. It does not mean clearing has completed.” The demonstration replaces the approval action with “Try approval.”
4. An authenticated live request checks the proposal digest and local revisions before accepting authority. A stale response opens a new review, never silently updates the approved amount.
5. Display approved, reserved and settling states separately. Completion opens a verified receipt. Lost contact opens an explicit unknown-status screen with the last verified update and a retry-status action.

## Requirements

| ID | Requirement |
| --- | --- |
| CAP-01 | Show all of the participant's affected peers, agreed unit, before/change/after amounts and net-position comparison before approval. Use exact integer minor units internally and unambiguous formatting. |
| CAP-02 | Require reconciled obligations, current bilateral revisions, undisputed eligibility and compatible terms. Missing peer agreement blocks approval with a specific reason. Do not claim legal eligibility solely from a balanced cycle. |
| CAP-03 | Bind approval to participant, proposal digest, ordered local edge changes, bilateral revisions/episode IDs, amount/unit, terms and policy versions, expiry, authorization scope and nonce. A changed economic proposal needs fresh approval. |
| CAP-04 | Check current authority and revisions on the node when processing approval; a disabled UI is not an authorization boundary. A duplicate idempotency key returns the same decision, and reuse with a different digest is rejected. |
| CAP-05 | Never increase an affected debt or create a fresh peer debt in cancellation mode. Verify per-participant signed net conservation before reservation and settlement admission. |
| CAP-06 | Show only the participant's own changes by default. Do not put traversed peer lists into push notifications, client analytics or URLs. Describe unavoidable route/host metadata exposure in privacy documentation. |
| CAP-07 | Offline clients may view a labelled cached proposal but cannot assert approval acceptance or completion. Do not queue silent approval for later submission in version one. Network loss after submission triggers status lookup by the same request ID. |
| CAP-08 | Decline prevents granting authority for this proposal. Withdrawal is a request, available only while the chosen settlement protocol proves it remains safe; do not describe it as guaranteed cancellation. |
| CAP-09 | “Pause new clearing” blocks new admissions; it neither rolls back nor abandons an in-flight irrevocable decision. Approval expiry limits new use of authority, and never releases a reservation when a commit may already exist. |
| CAP-10 | Device authentication, node hosting, ledger access and settlement signing permissions are separate capabilities. Explain who holds signing authority before the first live approval and when that arrangement changes. |
| CAP-11 | Keep an audit record of the reviewed digest, authorization result and reasons without storing full community routes in product telemetry. Count only verified completed settlements as cleared. |

## State contract

The client renders node evidence; it cannot infer protocol state from elapsed time. The names below are product states, not a specification of the eventual commit protocol.

| State | Entry and allowed next states | User-facing meaning |
| --- | --- | --- |
| Preview | Reconciled proposal; may become approved, declined, stale or expired | No authority granted. |
| Approved | Node accepted exact authority; may become reserved, safely withdrawn, stale or expired before admission | Authorized; no completed balance change. |
| Reserved | Durable protocol admission; may become settling or safely aborted on protocol evidence | Affected capacity is held. |
| Settling | Recovery must determine/finish the decision; may become completed or proven aborted | Do not spend reserved capacity or promise cancellation. |
| Completed | Verified settlement evidence and reconciled local entries | Receipt available. Immutable outcome. |
| Aborted / declined / expired / stale | Explicit evidence or pre-admission condition; retry requires a new proposal as appropriate | No new clearing authorized by this proposal. An expiry cannot overrule admitted settlement. |

“Offline” and “status unknown” are display overlays, not terminal settlement outcomes. If a response is lost, preserve the last verified state and query; do not label the proposal declined or submit a new settlement ID. Conflicting evidence enters recovery hold as defined in the companion PRD. A proposal invalidated by an external transfer is stale before admission; handling transfers after reservation is owned by the protocol and must not bypass its locks.

## Conceptual API and data contract

These are interface requirements for the persistence/transport spike, not a published wire specification.

- `GET /v1/proposals/{id}` returns `mode` (`demo`, `testnet`, `live`), participant scope, accounting unit/scale, `proposalDigest`, local edge tuples (`peerId`, `episodeId`, `revision`, `before`, `delta`, `after`), terms/policy versions, expiry, eligibility reasons and an evidence-backed status/revision.
- `POST /v1/proposals/{id}/approvals` requires authenticated signing scope, expected digest/status revision and idempotency key. Return accepted authority ID or structured `STALE_PROPOSAL`, `NOT_ELIGIBLE`, `AUTHORITY_REQUIRED`, `MODE_DISABLED` or `CONFLICT`; transport acceptance alone is never settlement completion.
- `POST /v1/proposals/{id}/decline` records a decision before authority is given. `POST /v1/settlements/{id}/withdrawal-requests` requests safe withdrawal; `409 IRREVOCABLE_OR_UNCERTAIN` explains why a promise cannot be made.
- `GET /v1/requests/{id}` resolves ambiguous submission outcomes. Status/event responses include a monotonic local journal cursor, observed time and evidence reference. Reconnect clients catch up from that cursor and perform a snapshot fetch when history is unavailable.

Never place private signing keys in these payloads. Exact expiry admission semantics, signatures and proof contents are decisions for the reviewed settlement specification.

## Acceptance and validation

- In the canonical fixture, render 7→4 and 5→2 with −2→−2 net position; reject a request that changes either proposed amount while retaining its digest/approval ID.
- Alpha approval simulation produces no authoritative ledger mutation or live signing operation, including direct API attempts. Test and live modes cannot share proposal identities or keys accidentally.
- A peer revision change between render and click yields an actionable stale response; the user sees and approves the replacement separately.
- Duplicate submissions create one authority record; lost responses recover that same record by request ID. Expiry during a partition never frees a potentially committed reservation.
- Restart/offline/reordered-event tests retain the last verified status and never present pending as completed. A proposal completed while the phone sleeps becomes a receipt on reconnect.
- At least five pilot participants can explain both local changes, unchanged net position and the difference between approval and completion without coaching. Keyboard, screen-reader, large-text and non-colour status checks cover the whole flow.

## Dependencies and open decisions

Requires bilateral reconciliation, identity/signing roles, integer amount rules, durable journal, API authentication and the independently reviewed settlement model. Decide at the design gate whether the pilot uses peer-operated settlement or an explicitly trusted community service; the UI must name whichever authority actually decides settlement. Decide approval expiry duration, authentication strength, eligible obligation terms and notification channels with the pilot community. Do not choose these from benchmark scores. Automatic policies and Headroom need new PRDs and explicit consent, not a hidden configuration switch.
