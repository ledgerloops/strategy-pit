# 004 — Restore neighbour-private hashlock settlement

**Status:** In progress — v2 honest-peer implementation; broader security work remains · **Opened:** 2026-10-11

[Issue tracker](README.md) · [Product roadmap](../product-roadmap.md) · [Current app protocol](../../app/protocol.md)

## Requirement and architectural gap

Restore the original LedgerLoops requirement: a participant needs to know only its direct neighbours. It must not need the identities of other loop participants or the exact total loop length. The protocol must enforce a minimum of three participants without providing a global participant list or total-hop count.

The legacy v1 `app/node.py` sends an enumerated `path`, indexes into it for forwarding, and collects votes from every named participant at the origin. `app/protocol.md` explicitly describes this mechanism. Even though messages travel over neighbour links, it exposes remote membership and changes the trust model. That v1 app is an **honest-peer infrastructure prototype**, useful for testing HTTP delivery, storage and UI integration; its tests do not validate the original LedgerLoops hashlock protocol or its privacy requirement.

Replacing COMMIT with a preimage check alone does not fix this. Discovery, conditional bilateral approval, fulfillment, abort and recovery evidence must all respect the same knowledge boundary. Hiding a route in the browser while retaining it in node state, logs or messages also fails the requirement.

## Proposed direction to investigate

Review historical LedgerLoops/Jerboa discovery, proposal and fulfillment flows, documenting which privacy and safety properties they actually establish. Jerboa's `src/Jerboa.ts` uses proposal hashes and commit preimages; source reuse is not a proof of the complete required protocol.

Develop a specification using local incoming/outgoing relationships, scoped opaque handles and conditional bilateral commitments. Investigate whether a returning opaque probe and local anti-reflection rules can establish an eligible loop without enumerating it. Explicitly address repeated visits, intersecting probes, two-party echoes and whether three distinct participants can be established under the selected identity/adversary assumptions. An opaque identifier, saturating threshold or cryptographic proof is only a candidate until its leakage and soundness are analyzed.

For settlement, define the hash algorithm, high-entropy fresh secret generation, condition binding, consent, when disclosure becomes irrevocable, and how an approved node checks fulfillment locally. Bind amount, unit, bilateral state/version and protocol context so a preimage cannot authorize a different obligation. Investigate recovery by neighbour evidence rather than collecting a membership list at an origin. Do not assume a public secret by itself proves all participants approved or applied changes.

Cancellation requires particular care: an approved conditional obligation cannot be released while a valid fulfillment may still emerge elsewhere. Specify any trusted clock, delay bound, expiry ordering or dispute/enforcement assumption before using timeouts. If safe expiry under the chosen asynchronous failure model cannot be achieved, retain locks and document the liveness limitation. Do not silently add a membership-enumerating coordinator to make cancellation or completion convenient.

## Threat model and metadata

Separate safety, liveness and privacy claims. Initially evaluate crash/restart with durable storage and authenticated direct-neighbour transport, then explicitly analyze malicious peers, forged/replayed probes, secret withholding, collusion and identity aliasing. State what is guaranteed under each model; do not infer Byzantine tolerance from honest-peer tests.

“No remote identities or exact loop length required” is a protocol knowledge constraint, not absolute anonymity. Timing, traffic volume, packet size, endpoint metadata, repeated interactions, shared hash conditions and colluding neighbours can correlate activity or reveal topology. Document such leakage and any mitigation assumptions. Global test instrumentation may know the generated graph for scoring, but must not provide that information to participant code, its API, logs or recovery decisions.

## Acceptance criteria

1. **Knowledge boundary:** a reviewed protocol specification and implementation require no non-neighbour identity, participant roster, exact total-hop counter or route vector in a node's protocol-visible state/messages, including discovery, preparation, receipts and recovery. Audit local storage, API responses, logs and evidence formats as well as wire traffic. Opaque fields must not merely encode a recoverable list.
2. **Minimum three:** demonstrate exclusion of two-party cycles/reflections and the required meaning of three distinct participants without a global list. State identity/Sybil assumptions and supply counterexample tests for probe collisions and repeated visits. Do not claim this is solved by asserting it in a message.
3. **Conditional consent:** each participant authorizes its own bilateral changes and verifies local conservation, capacity, version and terms. No origin needs a named vote from every participant. Rejection and consent races have specified outcomes.
4. **Locally verifiable fulfillment:** a node verifies the preimage against its stored hashlock and exact authorized obligation; missing, wrong, reused or context-mismatched evidence cannot settle. Secret creation, persistence, release and propagation are specified and tested.
5. **Durable recovery:** separate-process tests exercise loss, duplicate/reordered delivery and crashes around reservation, secret release, local application and evidence forwarding. Fulfillment applies at most once; uncertainty stays visible; recovery needs no membership-enumerating coordinator. Preserve the existing-database/stale-backup distinction.
6. **Safe cancellation/expiry:** document and test when abort is provably safe, what becomes irrevocable on fulfillment, and how release/cancellation races are handled. No timeout silently releases potentially fulfillable capacity. State blocking and permanent-loss limits explicitly.
7. **Honest completion semantics:** distinguish local fulfillment from any stronger whole-loop claim. Supply evidence and assumptions for stronger claims without requiring the full roster or exact loop length; otherwise omit those claims from receipts and UI.
8. **Privacy validation:** instrument participant views on varying-length/topology fixtures to detect explicit or encoded remote-membership/length leakage; independently review metadata and collusion limitations. These tests support a scoped claim, not information-theoretic anonymity.
9. **Migration and documentation:** version the replacement protocol and define handling of existing pending work. Never reinterpret current prototype reservations under a new protocol. Update app labels and PRDs; publish independent review and negative findings before calling it the restored LedgerLoops protocol.

## Work plan and release gate

- Inventory historical hashlock designs and current path/vote dependencies.
- Write candidate message/state schemas plus safety, liveness and privacy arguments; seek counterexamples before implementation.
- Resolve minimum-three detection, conditional consent and safe cancellation together; document unresolved assumptions.
- Build a separate versioned experimental protocol with instrumented local views and fault tests.
- Integrate the reviewed candidate behind the app after migration and UI evidence semantics are defined.

This is a blocking architecture gate for claiming the product restores neighbour-private LedgerLoops. A trusted settlement service can be evaluated as a separately named alternative, but cannot satisfy this issue by silently changing its requirements. Recording this issue does not authorize replacing or migrating running app state now.

## Progress

- 2026-10-11: gap recorded from the owner's clarification; current app and roadmap labelled accordingly. No claim that the combined requirements are solved. Immediate work is specification and investigation, not an in-place protocol swap.

## Implemented v2 checkpoint

The owner's subsequent instruction authorized implementation. [Private v2](../../app/private_protocol.md) now replaces enumerated paths with durable local predecessor/successor bindings and opaque condition references. Fixed-amount discovery excludes reflection and rejects revisits; local conditional approvals gate readiness propagation. SHA-256 conditions bind protocol, identifier, amount, unit and a fresh 32-byte secret. Nodes verify fulfillment locally; no roster or exact hop count is required. Receipts deliberately claim local fulfillment only.

[Network and adversarial validation](../../app/PRIVATE_TESTING.md) covers differently sized rings, local-view/wire audits, minimum-three/reflection, failed subcycles, decline, invalid evidence, duplicates and selected crash/restart boundaries. A failed-subcycle cleanup defect and a semantic replay hazard were found and corrected during independent review. The client and standalone receipt verifier check released evidence; tampering fails verification.

This is an implemented candidate within honest-peer, stable-identity, durable-storage assumptions, not a proof against Byzantine behaviour, Sybils, traffic analysis or all possible failures. There is no deadline-based unlock or permanent-node-loss recovery. Legacy and v2 databases are mutually rejected rather than migrated. Remaining work includes broader crash exploration, explicit production identity/transport and rollback recovery, operational limits and adversarial privacy/security analysis. Keep this issue open for those release gates; do not equate implementation with full production readiness.

## Private asynchronous headroom experiment

The October 20 [private stream experiment](../../artifacts/mdg2-private-stream-2026-10-20/report.html)
keeps the actual v2 hashlock, conditional approvals and durable SQLite state while
transactions arrive asynchronously. Each node independently starts searches; a
simulator queue delivers packets, but does not select roots, routes or settlements.
No participant receives a remote identity, roster, route, global objective or hop count.
The loop initiator still creates/releases its secret; removing a network-wide
coordinator does not remove local consent or message ordering.

The separately bound `private-local-nonexpansion-v1` comfort policy permits helper
trustlines but requires every participant's two-edge absolute exposure not to
increase, with a strict decrease at the initiator. A later local filter rejects
already-inadmissible pairs before forwarding. Both are research variants; the
running demo and production policy are unchanged.

The policy is not complete. A broad-zone five-edge ring with signed balances
`[-1, -1, -1, 0, 0]` can move to `[0, 0, 0, 1, 1]`, reducing gross debt from 3 to 2.
The participant between the two helper edges would increase its local absolute
exposure by 2, so the present policy refuses it regardless of message budget.
Investigate privacy-preserving aggregate-benefit consent and concurrent-search
liveness without transmitting a path, membership count or recoverable loop length.
The earlier 100% coordinated exact reference does not satisfy this issue's boundary.
