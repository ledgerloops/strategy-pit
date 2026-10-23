# 006 — Account recovery

Status: Open — design exploration; implementation deferred.

GitHub issue: [#45 — Account recovery: standard server-assisted options and peer-assisted exploration](https://github.com/ledgerloops/strategy-pit/issues/45).

## Problem

The hosted TEST demo currently ties an account to a persistent browser cookie. Users created in private browser profiles lose access when those profiles close, although their server-side trustlines, balances and history remain. Passkey/recovery-code setup was intentionally removed from the demo UX.

We need to investigate account recovery without prematurely choosing one blanket solution. Separate concerns specific to the demo, to hosted accounts, and to LedgerLoops generally. **This issue records future design/prototyping work; leave the current recovery behavior unchanged for now.**

## Server-assisted recovery

A hosted service can solve part of this using standard account recovery, for example an expiring, single-use password-reset/sign-in link sent to a previously verified email address. The current demo is passwordless, so the operation would restore account access or bind a new credential rather than necessarily reset a password.

Explore optional verified recovery email and/or additional credentials, account enumeration protections, expiry/replay protection, rate limits, recovery notifications, and deliberate session revocation policy. Email must be enrolled and verified while access exists; attaching a new address after losing access is not itself proof of ownership. Existing cookie-only accounts need a separate migration/operator-recovery policy.

This relies on the hosting service and email account. It does not resolve recovery for self-hosted, offline or decentralized LedgerLoops deployments.

## Peer-assisted recovery: open research

Brainstorm and prototype before adopting a mechanism. Possible models include:

- Several accounts/devices having access to the same trustline endpoint, or a recovered account regaining only a subset of its former relationships.
- Separating a login account/device, a trustline endpoint, and the grant that authorizes an account/device to operate that endpoint.
- Recovering one relationship first, while others remain inaccessible until independently authorized by their peers through an established out-of-band channel.
- Owner-created additional-device grants or saved recovery tokens, predesignated recovery contacts, or multiple independent recovery approvals.

These are alternatives/questions, not an agreed protocol or implementation plan.

## Threats and unresolved boundaries

- **Address-book harvesting/social engineering:** one peer approval must not expose the rest of the contact list and help an impostor solicit more reset links. Greyed-out names are still disclosure. Consider anonymous placeholders or hiding locked relationships entirely; enforce restrictions in APIs, history, exports and messaging, not only the UI. Do not automatically contact other peers on behalf of a recovery claimant.
- **Controlling both sides:** if Alice can mint and redeem a restore token for Bob's endpoint, Alice can approve both sides of a delivery. Decide whether that authority is intentionally delegated, requires an independent factor, or is prohibited. Two distinct accounts/keys do not establish two independent people.
- **Proof vs endorsement:** if every old credential is lost, a new device's cryptographic proof establishes control of its new key; a peer approval establishes endorsement of that key. Neither alone proves it belongs to the original human. Current shared server-held channel secrets are not a personal recovery credential distinguishing the two endpoints.
- **Scope and existing access:** distinguish restoring access, adding a device, delegating to another person and transferring an endpoint. Decide what remains available to old devices, how grants are revoked, and whether one compromised peer can cause account-wide denial of service.
- **Ledger preservation:** recovery must not reset balances, duplicate credit limits, erase history, silently rewrite existing consent, or disrupt durable reservations/pending protocol work. Access to one relationship must not confer authority over unrelated relationships.
- **Cryptographic design:** if peer-approved device grants are pursued, investigate binding approval to the intended endpoint, new device public key, recovery context, expiry and single-use challenge. A forwarded link should not silently grant unrelated account-wide access.

## Work to do

- [ ] Classify requirements across cookie-only TEST demo, hosted service, and LedgerLoops protocol/deployment models.
- [ ] Propose a conventional server-assisted recovery path and migration policy.
- [ ] Write threat models for owner-controlled and peer-assisted recovery, including address-book disclosure and both-endpoint control.
- [ ] Brainstorm peer-assisted designs and prototype their UX and authorization boundaries before selecting one.
- [ ] Document which trust assumptions and guarantees each approach provides, and which questions remain unresolved.

No recovery implementation, credential reset, or account migration is requested as part of filing this issue.
