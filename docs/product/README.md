# LedgerLoops product specifications

Draft v0.1 · 11 October 2026 · [Roadmap](../product-roadmap.md)

**22 October design discussion:** the [hosted alpha proposal](hosted-alpha-discussion.md)
records the user's agreement to host at `ledgerloops.com` with disclosed operator
access, while forbidding algorithmic use of cross-node visibility. It discusses
passkeys, sessions, durable hosting and a writable TEST alpha; it is not a deployed
service or an implementation authorization. Older release proposals below remain
background and must be reconciled with that discussion before implementation.

**Subsequent authorization and implementation:** the user requested implementation
and Heroku deployment at `app.ledgerloops.com`. The
[hosted architecture](../../app/HOSTED_ALPHA.md) and
[local-worker handoff](../deployment-handoff.md) supersede the earlier read-only
scope and discussion-only status. Deployment still requires a verified release
and live domain checks; do not infer it from the existence of these files.

An installable, mobile-friendly web app with optional hosted nodes and self-hosting. The first alpha is a read-only clearing assistant. Durable node operation and live settlement are separate release gates. These specifications are proposed contracts for implementation and review, not descriptions of existing services.

## First implementation

The [private hashlock app](../../app/README.md) implements authenticated node connection, fixture balances, neighbour-only discovery/consent without a roster, context-bound fulfillment, locally verified receipts and durable recovery. [Validation](../../app/PRIVATE_TESTING.md) covers differently sized real HTTP networks and adversarial state checks. Enrollment/imports, production identity, dynamic transfers and live deployment remain unimplemented; the PRDs describe the wider target.

## Component PRDs

| Component | Responsibility | Prototype screens |
| --- | --- | --- |
| [01 Identity and hosting](prds/01-identity-hosting.md) | Invitations, identity, hosting choice, authorization and recovery setup | Join, Your node |
| [02 Peers and balances](prds/02-peers-balances.md) | Bilateral agreement, imports, units and reconciliation | Overview, Peers, Import |
| [03 Clearing and approvals](prds/03-clearing-approvals.md) | Local proposal discovery, preview and explicit consent | Review |
| [04 Receipts and recovery](prds/04-receipts-recovery.md) | Pending outcomes, evidence, history and exports | Pending, Receipt |
| [05 Node service and operations](prds/05-node-service.md) | Persistence, neighbour transport, API, hosted isolation and release gates | Your node |

## Explore the wireframes

Open [wireframes/index.html](wireframes/index.html) in a browser. GitHub displays its source; download the file or serve this directory locally to interact with it:

```sh
python3 -m http.server 8080 --directory docs/product
# Open http://localhost:8080/wireframes/
```

The prototype is a single dependency-free HTML file, responsive on phones and desktops. It uses fictional data, makes no network requests, stores no credentials and resets on refresh. It is not an installed PWA or an implemented backend. Navigation to future live-state examples is for design review, not a settlement transition.

Static previews: [phone](wireframes/mobile-review.png) · [desktop](wireframes/desktop-review.png). Browser checks covered all eight screens at 320px, 390px and 1280px, plus stale/offline approval guards. This is not a full accessibility audit.

Try: Join → Overview → Review → check consent → record demo response. Then select “Balance changed” or “Your node is offline” and confirm approval is blocked. Inspect the separate Pending and Receipt examples, download the explicitly unsigned demo receipt, and try pausing new clearing in Your node.

The common scenario is Alice owing Bob 7 CU and being owed 5 CU by Doris. A cancellation of 3 changes those balances to 4 and 2; Alice's signed net position stays −2 CU. The client shows Alice's two relationships, without a global network view. Real discovery must establish the rest of a valid loop before presenting a proposal.

## Shared design and engineering decisions

[Issue 004](../issues/004-neighbour-private-hashlock-settlement.md) constrains all components: discovery, approvals, receipts and recovery must not require remote identities or exact total loop length in node state/messages. The legacy path-based app does not meet this target. Private v2 implements a reviewed honest-peer candidate with minimum-three enforcement and local hashlock consent; it deliberately has no timeout-based expiry and no claim of whole-loop completion. Production and adversarial-security gates remain open.

- Alpha actions record draft/demo responses only. Live settlement requires the roadmap's protocol and pilot gates. Server capability checks enforce this separation; hiding a button is insufficient.
- Mobile and desktop share the same product and API. Native apps are deferred until secure signing, notifications or offline requirements justify them. Browser sleep is normal; a node handles durable delivery independently.
- Amounts in product screens name their unit. Production contracts use integer minor-unit strings plus unit/scale, never floating-point money. Signed balances are positive when owed to the current participant.
- API paths in component drafts are illustrative; standardize them under `/v1` and reconcile error names in one OpenAPI contract before implementation.
- Pass explicit identity, proposal, policy and revision references across component boundaries. No client-supplied completion flag can finalize a ledger entry.
- Show when data was last synchronized. Offline review is allowed; stale approval is not silently queued. Revalidate against the current node before any live authorization.
- Target WCAG 2.2 AA: semantic labels, keyboard operation, visible focus, text status in addition to colour, touch targets and usable 320px layouts. Test with assistive technology before alpha release.
- Plain-language content should distinguish hosting from signing authority, consent from commitment, and pending from completed. Keep protocol internals in expandable diagnostic details.
- No graph-wide routing dashboard. Optional support exports contain only explicitly selected local records and explain metadata exposure.

## Implementation order and review

1. Agree identity/recovery and settlement trust models; stabilize the draft entity contracts across all five PRDs.
2. Implement the read-only shell, fixture-backed API, imports and proposal previews. Run five moderated usability sessions with an authorized pilot group.
3. Build the three-node persistence/transport testnet; make recovery and receipt verification pass independently of the UI.
4. Integrate approved writes behind a server-enforced capability only after independent settlement review. Test stale/offline/duplicate authorization and uncertain outcomes end to end.
5. Add PWA packaging, safe cache policy and hosted operations; conduct the shadow pilot before enabling live clearing.

Review questions: do users understand which claims decrease; can they distinguish a demo response from a final receipt; do they understand who can sign; can they find pause/export/recovery without assistance? Record observations and update these drafts before treating the wireframes as final design.
