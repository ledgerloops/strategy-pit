# PRD 05 — Node service and hosted operations

Draft v0.1. Owner role: runtime/protocol engineering. Depends on PRDs 01–04 and the [product roadmap](../../product-roadmap.md). Audience: self-hosting participants, community hosts, client developers and support operators.

## Outcome and scope

An always-online node represents one participant and exchanges messages with direct neighbours while that participant's phone sleeps. The first implementation serves fixture-backed, read-only views. A later testnet provides separate durable stores and authenticated transport. Live authorizations remain disabled until independently reviewed settlement/recovery gates pass. No production language, host, pricing or cryptographic finality mechanism is selected by this PRD.

## Requirements

| ID | Requirement | Release |
| --- | --- | --- |
| NODE-01 | Publish a versioned API capability document identifying read-only/testnet/live mode, unit support, protocol version and synchronization status. Enforce allowed operations server-side. | Alpha |
| NODE-02 | Expose only the authenticated participant's records. Deny cross-tenant IDs and support access by default. A hosted operator's actual access and key custody must be disclosed. | Alpha |
| NODE-03 | Run discovery and acceptance using local state and direct-neighbour messages. No shared graph service may select clearing routes or authorize a participant. | Testnet |
| NODE-04 | Persist local decisions, reservations, deduplication and outbound messages transactionally before acknowledging operations that depend on them. Restart preserves their identities and ordering constraints. | Testnet |
| NODE-05 | Authenticate neighbours and bind messages to identity, protocol version, unit, transaction and bilateral episode/revision. Reject replay, malformed/oversized input and incompatible versions. | Testnet |
| NODE-06 | Retry with bounded concurrency, backoff and per-peer quotas. Expose delayed work without silently dropping accepted financial operations. Bound memory through reviewed receipt-retention rules, never by forgetting replay protection prematurely. | Testnet |
| NODE-07 | A participant pause stops new discovery/preparation but permits recovery of existing irrevocable work. Uncertain reservations cannot expire into reusable balance solely on elapsed time. | Testnet |
| NODE-08 | Restore from backups only after validating freshness and recovering in-flight outcomes. Detect rollback; freeze conflicting writes. Key rotation/migration preserves verification of prior receipts. | Testnet |
| NODE-09 | Package documented installation, encrypted transport, upgrades, backup/restore and export. Verify tenant isolation, resource quotas and audit trails for hosted administration. | Pilot |
| NODE-10 | Provide opt-in aggregate health metrics without collecting the whole credit graph. Support bundles preview local data before export; redact secrets. | Alpha/pilot |

## Conceptual API and data boundaries

Names are draft interfaces, not implemented endpoints. `GET /capabilities`, `/sync-status`, `/peers`, `/balances`, `/proposals` and `/activity` power the read-only client. Mutation endpoints for imports/consent/pause accept an authenticated principal, idempotency key and expected revision; return a durable operation ID and explicit state, never implied completion from HTTP success. Repeated identical requests return the same operation; reusing a key for different payloads fails.

Use integer minor-unit strings and explicit unit/scale. Reject overflow, unknown units and conflicting revisions. Events have monotonic local sequence numbers for reconnect; gaps trigger authenticated snapshot/reconciliation. Device caches are subordinate to node authority. Do not cache signing material or sensitive financial responses in a public service-worker cache. Define authenticated local cache retention and deletion before enabling offline storage.

Keep discovery, bilateral agreement and whole-cycle settlement as distinct interfaces. A signed request proves authorization, not global atomicity. The protocol specification must define who can issue a binding decision, how it is recovered after coordinator loss, and what an equivocating participant can do. A community-trusted settlement service, if chosen, requires an explicit trust-model revision and user disclosure.

## Operational states and failures

`read-only`, `ready`, `paused-for-new-work`, `recovering`, `incompatible` and `attention-required` describe node availability separately from each settlement's state. Network loss may make progress impossible while preserving reservations. Disk-full or persistence failure must stop acknowledgements that imply durable acceptance. A restore with stale state enters recovery, not ready. An unavailable host does not authorize the phone to fabricate receipts.

Operators need runbooks for unavailable peers, storage exhaustion, restore, signing-key compromise, failed upgrade and an unexplained balance divergence. In the last case stop new clearing, preserve evidence and reconcile. No automatic reversal of a potentially final settlement. Define support ownership and host exit/export arrangements before the pilot.

## Acceptance criteria

- A read-only client cannot cause settlement even by calling the write API directly.
- Three independent processes and databases recover after termination at each durable-write/send boundary; no duplicate change or unexplained net-position drift occurs.
- Duplicate requests and reordered messages preserve one logical operation; stale revisions fail with a refresh path.
- A partition after preparation keeps uncertain capacity unavailable until valid outcome evidence arrives. Recovery continues while new clearing is paused.
- Wrong-tenant identifiers, denied keys and unsupported protocol versions are rejected; logs contain no signing secrets.
- A stale-backup restore cannot spend previously committed capacity. Restore and host-migration drills produce verifiable continuity or explicitly block operation.
- Test latency, queued work, disk/memory and traffic under representative faults; agree load and cost budgets before the pilot rather than inventing service guarantees.

## Open decisions and dependencies

Protocol trust/finality and malicious-peer assumptions require independent review. Select signing/recovery policy with PRD 01; receipt evidence and retention with PRD 04; authoritative ledger integration with PRD 02. Hosting pricing, infrastructure sizing, support coverage, data residency and production language remain open. These block a production service commitment, not the fixture-backed alpha.
