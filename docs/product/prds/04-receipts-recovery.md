# Receipts, history and recovery

Status: draft for alpha exports and gated durable testnet; 11 October 2026. Owner role: protocol/runtime with client and operations. Parent: [product roadmap](../../product-roadmap.md). Companion: [clearing approvals](03-clearing-approvals.md).

## Outcome and release boundary

Participants can distinguish a preview from a completed change, obtain evidence of their own settled obligations, and recover uncertain work without inventing a result. A useful receipt explains what changed and why its status is trustworthy. It does not certify that cash moved, that an invoice never existed or that a peer will repay the remaining debt.

Alpha exports are clearly marked “Preview — not a settlement receipt,” reference their source snapshot and never enter authoritative accounting. A three-node testnet uses separate durable stores and test keys. Live receipts and recovery remain gated on the chosen settlement model, independent review and crash/replay conformance. The simulator's atomic pair-state update is not an acceptable production settlement mechanism.

## Main flows and example

**History:** show preview, pending, completed and aborted items with separate totals. Opening a completed item shows affected peers, unit, before/after amounts, effective journal references and verification status. For Alice's cancellation of 3, the receipt shows debt to Bob 7→4, receivable from Doris 5→2 and net position −2→−2. It represents Alice's local slice of a valid loop; the UI does not reveal the entire loop.

**Export:** download the participant's readable receipt, machine-readable evidence and local accounting adjustments. Preserve source invoice references rather than editing invoice history. Preview and testnet files remain unmistakable after download or printing.

**Uncertain outcome:** show “We cannot yet verify the result,” the last verified event, affected reserved capacity and an action to retry reconciliation. Support can collect a consented diagnostic bundle, but cannot force “completed” from the dashboard.

**Restore or change host:** restore a verified backup into a restricted recovery mode, detect stale state, reconcile authenticated peer/settlement evidence, then re-enable new clearing only when invariants pass. An old backup must not create new spendable capacity. A host disappearing does not justify writing a guessed outcome.

## Requirements

| ID | Requirement |
| --- | --- |
| RCR-01 | Use one stable settlement ID and immutable, append-only local journal events. Deduplicate inbox deliveries and outbox retries across restart. A receipt references the exact proposal/authority and local entries. |
| RCR-02 | Show “Completed” only after the selected protocol supplies its required decision evidence and local durable ledger application/reconciliation checks pass. Define that evidence in the reviewed settlement specification; signatures alone are insufficient. |
| RCR-03 | Separate final local balance, reserved capacity and uncertain work. Exclude proposed, reserved and partially applied work from cleared-value totals and ordinary completed-accounting exports. |
| RCR-04 | Retain reservations during uncertain prepared outcomes, including expiry, loss, sleeping peers and partitions. A timeout triggers retry/escalation, not unilateral abort or release. Waiting may be indefinite. |
| RCR-05 | Detect missing, invalid or conflicting evidence, stale backups and replayed certificates. Quarantine affected relationships/transactions and pause new clearing where safety requires; preserve evidence for investigation. |
| RCR-06 | Retain sufficient authenticated evidence for independent verification and recovery after host loss. Export scope is the participant's own records; disclose any required remote metadata and minimize it. |
| RCR-07 | Do not mutate completed history to fix an error. A correction is a separately authorized, linked accounting event under agreed terms; automatic compensation is outside scope. |
| RCR-08 | Distinguish protocol acknowledgement, durable decision and completed local application. A push notification, HTTP success or neighbour ACK does not establish settlement finality. |
| RCR-09 | Backup/restore covers journal, inbox/outbox, identity references, bilateral revisions and reservations. Key recovery/rotation has a separately reviewed design. Never imply that an email reset restores cryptographic authority or inaccessible evidence. |
| RCR-10 | Recovery/control traffic for previously admitted settlements may continue after a balance reaches zero; new discovery may not use that channel under cancellation-only policy. Leaving or pausing must preserve a way to retrieve pending evidence. |
| RCR-11 | Provide accessible pending/error states, last verified update and manual refresh. Do not require the phone to remain online for a hosted node to retain durable work. Host/signing trust is disclosed separately. |
| RCR-12 | Every recovery transition records evidence and reason. Operator tools cannot directly edit balances, erase reservations or mark success; privileged operations are authenticated and audited. |

## Recovery state model

This model constrains the production protocol but does not select a distributed commit mechanism.

| State | Evidence/action | Safe transition |
| --- | --- | --- |
| No durable admission | No accepted reservation; proposal may expire normally | New review or evidenced rejection. |
| Prepared / reserved | Durable reservation and exact admitted authority | Await reviewed decision protocol; no timeout release. |
| Decision unknown | Required outcome evidence unavailable or ambiguous | Retry authenticated recovery; retain reservation. |
| Commit evidenced, application pending | Valid decision under selected model; local application incomplete | Idempotent replay to durable application, then reconciliation. Never abort. |
| Completed | Valid evidence, durable local application, reconciliation checks | Read/export immutable receipt. |
| Abort evidenced | Protocol proves that abort is safe | Release reservation exactly once; retain abort record. |
| Evidence conflict / stale restore | Conflicting certificates, identity/revision anomaly or insufficient restore proof | Recovery hold, pause affected new work, investigate; never pick the convenient outcome. |

The exact proof that permits abort or establishes commit is a release-blocking decision. If a trusted pilot service is selected, its signed decision and availability/recovery obligations must be named; do not market the result as peer-operated atomic settlement. In a peer-operated model, document coordinator loss, malicious peers and availability limits explicitly.

## Conceptual interfaces and records

- `GET /v1/settlements/{id}` returns mode, participant-scoped local changes, proposal digest, authority reference, current evidence-backed state, journal cursor, evidence references, reserved capacity and last verified time. Observation timestamps are not globally agreed settlement order.
- `GET /v1/settlements/{id}/receipt` returns a completed receipt only when RCR-02 passes. Pending requests return a structured pending response with recovery link, never an empty successful receipt. Preview exports use a separate preview endpoint/type.
- `POST /v1/settlements/{id}/reconciliation-requests` is authenticated and idempotent. It schedules neighbour/decision evidence exchange; a successful response says “request accepted,” not “settled.”
- `GET /v1/history?cursor=...` exposes ordered local events and explicit pagination/cursor expiry. `GET /v1/exports/{id}` requires ownership scope; export generation records snapshot cursor and schema version.
- Receipt envelope: `schemaVersion`, `mode`, `settlementId`, participant identity/key references, unit/scale, proposal digest, local edge before/delta/after values and revisions, authority/terms versions, journal references, decision evidence/profile, verification result and linked source obligations. Use integer amount strings and versioned canonical serialization; never private keys.
- Export bundle: readable summary, receipt/evidence records, manifest of hashes/schema versions and accounting adjustments. Define signature coverage and a supported offline verifier after settlement-model selection. An unsigned printable summary is labelled as such and links to its evidence bundle.

The public API never exposes arbitrary journal rewriting, forced commit, forced abort or raw key recovery. Backup paths, encryption and export delivery must be reviewed before real participant data is stored.

## Acceptance and validation

1. Alice's completed fixture exports 7→4 and 5→2 with unchanged net −2 and exact source references. Importing/exporting twice produces no duplicate adjustment. A preview cannot be imported as verified settlement evidence.
2. Crash each node before and after every persistence/send boundary across at least three independent processes/stores. Restart, deduplicate and reconcile with zero unauthorized changes or unexplained divergence. Save conformance traces and evidence, not just aggregate pass rates.
3. Withhold decision evidence after preparation, let timers expire and restart the node. Capacity remains reserved, history remains pending, and no receipt or cleared-value credit is produced until evidence resolves the outcome.
4. Deliver duplicate/reordered commit, abort and ACK messages. Apply one outcome at most; conflicting valid-looking evidence enters recovery hold. Test stale keys, incorrect units, malformed amounts, version mismatches and altered receipt bytes.
5. Restore an old backup after a settlement and verify new clearing stays blocked until authenticated reconciliation establishes current state. A missing peer or unavailable decision service keeps uncertainty visible.
6. Disconnect a phone while its hosted node settles; reconnect shows durable history. Shut down a host and exercise the documented export/recovery path; state precisely what cannot be recovered if keys or all evidence copies are lost.
7. A participant can identify a preview, a pending item and a verified completed receipt, explain what remains owed and locate the export without developer help. Screen readers announce state and change amounts in a sensible order.

## Dependencies, metrics and decisions

Dependencies: approvals PRD; durable transactional journal/outbox/inbox; authenticated neighbour transport; bilateral revision and identity/key model; incident runbook; privacy/accounting review. Protocol/runtime owns evidence production; client owns faithful presentation; operations owns assisted recovery without inventing authority.

Measure prepared/unknown duration distributions, oldest unresolved item, locked capacity over time, duplicate/replay rejection, recovery success, export verification and discrepancies. Segment test/demo/live and report pending alongside completed totals. Set pilot latency/support targets with participants; zero unauthorized or unexplained balance changes is a release gate, not a statistical target.

Open before implementation of live settlement: peer-operated versus trusted pilot decision service; decision/abort certificates and proof verification; key custody/rotation/recovery; stale-backup detection; retention/compaction and legal retention periods; accounting entry mapping; accessible support and host-exit procedures. The first implementation task is to specify and independently review the durable state machine, then build the three-node crash harness. UI work may proceed against clearly labelled fixtures meanwhile.
