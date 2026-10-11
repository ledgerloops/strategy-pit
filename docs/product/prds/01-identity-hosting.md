# PRD 01 — Identity, hosting and recovery

Status: draft for implementation planning, 11 October 2026. Owner: product + runtime (roles, not assigned people). Parent: [product roadmap](../../product-roadmap.md). This specification describes proposed behaviour; no hosted service or secure recovery implementation exists by virtue of this document.

## Outcome and users

A cooperative participant can open LedgerLoops on a phone or desktop, identify their account, choose where their node runs, and understand who can act for them. A community operator can host participants without accidentally receiving undisclosed signing authority. A self-hosting participant can connect their own compatible node.

The client is a responsive, installable web app (PWA). Installation is optional. A phone is a user interface, not an assumption of continuous node availability: a hosted or self-hosted node processes neighbour messages while the browser is closed. Native apps are deferred until demonstrated needs justify them.

## Release boundary

**Read-only alpha:** a demo workspace or consented read-only workspace, app authentication, proposed hosting-choice screens, connection diagnostics and export. Existing accounting books remain authoritative. No real signing authority is delegated, no automatic clearing enabled, and no production keys are solicited. Mock choices must say “preview”; they must not imply that a service has been provisioned.

**Testnet:** real test identities, independent node stores, authentication, recovery exercises and explicit test-only authority. Test units cannot be confused with live obligations.

**Gated live pilot:** actual provisioning and signing choices only after the roadmap's settlement, recovery, security and pilot gates pass. Initially require explicit approval of each clearing proposal. Automatic authority, paid plans and native clients are outside this component's initial release.

## Requirements

| ID | Requirement and release |
| --- | --- |
| IH-01 | All: show workspace name, accounting unit and mode (`demo`, `read_only`, `testnet`, `live`) persistently; never upgrade a workspace's authority implicitly. |
| IH-02 | Alpha: let a user create or join a private workspace, sign out and revoke an app session. Separate app user ID, node ID and peer signing identity; display names are not cryptographic identity. |
| IH-03 | Alpha: compare managed hosting and self-hosting in plain language: availability, operator, data visibility, backup responsibility and support. Mark unavailable choices as planned. |
| IH-04 | Testnet/live: display two separate choices: **where the node runs** and **who holds settlement keys**. Hosting selection must not silently grant signing rights. Store explicit, versioned acknowledgements of the selected model. |
| IH-05 | Testnet/live: bind connection to an authenticated node identity and supported protocol version. Fail closed on a mismatched identity, invalid certificate or incompatible version; do not offer an “ignore security” shortcut. |
| IH-06 | Testnet/live: show health as last observed time and status, separately from unsettled transactions. A reachable host is not proof that every settlement completed. A stale view must be visibly stale. |
| IH-07 | All: accessible phone and desktop login, keyboard navigation, clear labels, touch targets and connection errors; core read-only views work without PWA installation. Cache only data explicitly permitted by the privacy policy. |
| IH-08 | Testnet/live: require reauthentication for session management, authority changes and exports containing sensitive records. Define inactivity and session expiry centrally; preserve unsent form input only when safe. |
| IH-09 | Testnet/live: recover app access separately from settlement keys. Resetting a login must not create authority to sign as an old peer. Key recovery/rotation requires an independently reviewed protocol and peer-visible identity continuity evidence. |
| IH-10 | Testnet/live: pause new discovery/approvals from the account controls. Existing irrevocable work continues recovery. Report outstanding reservations and uncertain outcomes before leaving or migration. |
| IH-11 | Testnet/live: support export and tested restoration of journal, peer revisions and receipts. Detect stale backups before enabling writes; never replace current state with an older snapshot silently. |
| IH-12 | Live: explain operator/key custody consequences at onboarding and in settings. Do not claim a host cannot inspect or alter state when the selected model gives it keys or plaintext. |

## Core flow and states

1. Open the app → select demo/read-only workspace or accept an invitation.
2. Authenticate → see mode and authority explanation.
3. Preview or select hosting → separately review signing authority → establish a compatible node connection if enabled for this release.
4. Complete the appropriate recovery checklist → enter balances/peers view.

Connection states: `not_configured → connecting → connected`; failures become `unreachable`, `identity_mismatch`, `unsupported_version` or `authentication_required`. Retry is safe and does not create a second node. Persist separate lifecycle states `active`, `paused`, `migration_pending`, `closed`; a paused node can still communicate to recover admitted settlements.

A session expiry returns to authentication without approving any pending action. Loss of internet shows the last-observed timestamp and disables authority-changing actions. Lost keys lead to a recovery/support flow, never a substitute identity presented as the same signer. An unavailable host leaves transaction outcomes unknown until durable evidence is recovered. Account closure distinguishes access removal from retention of records needed by peers and accounting requirements.

## Conceptual data and API contracts

These are interface proposals, not an implemented API or a decision about the production language.

- `Workspace {id, mode, unitId, authoritativeLedgerRef?, createdAt}`. `mode` is server-enforced and included in every state-changing request.
- `AppUser {id, displayName, membershipRoles[]}` and `Session {id, deviceLabel, createdAt, lastSeenAt, expiresAt}`. Never expose session tokens in audit exports.
- `NodeBinding {nodeId, authenticatedEndpoint, protocolVersion, operatorId, hostingMode, signingAuthorityModel, status, lastObservedAt}`. The signing model is an explicit approved enum; unsupported models cannot be selected.
- `AuthorityAcknowledgement {userId, modelVersion, textHash, acknowledgedAt}` records understanding; it is not a clearing approval or delegation certificate.
- `RecoveryReadiness {lastVerifiedBackupAt?, lastRestoreTestAt?, keyRecoveryMethod?, blockedReason?}` avoids storing recovery secrets in the UI database.

Proposed endpoints: `GET /session`, `GET /workspaces/{id}/node`, `POST /node-connections`, `POST /sessions/{id}/revoke`, `POST /workspaces/{id}/pause`, and `POST /exports`. Mutations require authenticated workspace scope, an idempotency key and expected resource version. Alpha capabilities reject authority operations with `MODE_FORBIDS_OPERATION`; hiding a button is insufficient. Responses distinguish accepted work from completed work and include request IDs safe for support.

A browser connection to a self-hosted node must not turn the SaaS backend into an unrestricted URL fetcher. Endpoint verification, SSRF controls, TLS/CORS/origin policy and DNS rebinding protections belong in the runtime spike before this connection API ships.

## Privacy and security

Collect the minimum account/contact data required for the selected authentication method. Do not require public profiles or global peer discovery. Never place keys, recovery phrases, balances or invitation secrets in analytics, URLs or diagnostic logs. Notifications use generic text until the user opens an authenticated view. Browser caches must be clearable on sign-out; shared-device mode avoids offline financial records.

A host may observe counterparties, timing and amounts depending on custody/encryption choices. Document the chosen threat model before claiming confidentiality. Recovery information must explain what the operator can and cannot restore. Separate application administrator privileges from participant signing rights in authorization tests.

## Acceptance evidence

- **IH-A1:** five alpha participants complete login, identify the workspace mode and explain hosting versus signing authority without developer help; record failures for redesign.
- **IH-A2:** direct API calls to alpha authority endpoints fail; a demo account cannot access a live/testnet workspace by changing IDs.
- **IH-A3:** disconnect/reconnect, session expiry, duplicate provisioning requests, wrong node identity and incompatible version fixtures yield the specified states without duplicate identities or implicit approval.
- **IH-A4:** a testnet recovery drill restores current receipts and flags an older backup; recovering an app login does not recover signing authority automatically.
- **IH-A5:** pause prevents new work while an already admitted settlement remains visibly pending/recoverable; logout does not report it as aborted.
- **IH-A6:** responsive layouts, screen-reader labels and keyboard access cover onboarding, sign-out, errors and pause. Audit logs and notifications contain no raw keys or financial detail.

## Dependencies and decisions before implementation

Depends on the settlement/finality specification, durable journal/outbox, authenticated node transport and a common mode/capability model. Live launch also depends on support and incident ownership.

Resolve in the initial spike: authentication method (passkeys, supported fallback), the single custody model offered first, identity rotation/recovery protocol, supported self-host endpoint deployment, browser caching policy and retention obligations. Do not implement multiple unreviewed custody models to make the choice screen look complete. The product can prototype the choices now while those decisions remain explicit.
