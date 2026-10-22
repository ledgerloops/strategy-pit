# Hosted LedgerLoops TEST alpha

Target: **https://app.ledgerloops.com**. The user authorized implementation and
Heroku deployment on 22 October 2026. A target URL is not evidence of a successful
deployment; the deployment record must include the actual release and live checks.

## What is implemented

- Passkey accounts backed by maintained WebAuthn verification, user verification,
  exact origin/RP binding, expiring single-use challenges and opaque server sessions.
- Secure, HttpOnly, SameSite session cookies; authenticated writes require an exact
  Origin and a session CSRF token. Cookies do not hold the node's identity or keys.
- Second passkeys and one-use recovery codes. Recovering the account preserves its
  node, balances, preferences, peer credentials and outstanding hashlocks.
- Private invitations establish zero-balance direct relationships. No public roster
  or network graph is supplied to nodes. Both endpoints set their own credit grants,
  comfort zones and assistance preference before headroom can be used.
- Obligation proposal/approval/history and the existing responsive comfort controls.
- Real cancellation and [comfort-zone headroom clearing](headroom_protocol.md),
  with local reservations, context-bound SHA-256 fulfillment and durable retries.
- Explicit optional background clearing. Enabling it allows own-node searches and
  conditional approval of clearing only when both endpoints of each local edge
  enable assistance and the quoted results stay inside shared comfort zones.
  It never automatically approves a new obligation. Default is manual approval.

The original local demo remains usable with its existing bearer tokens and data
directory. Hosted sign-in uses cookies and never exposes those protocol credentials
to browser JavaScript. No demo migration or reset is performed by deployment.

## Theory and actual implemented scope

The preferred consent model permits any net-position-preserving adjustment inside
mutually agreed comfort intervals and hard limits. A separate selection condition
requires strictly lower aggregate gross debt. See
[the full fixed-bound model](../experiments/COMFORT-ZONE-POLICY.md) and
[conditional residual-cycle optimality proof](../experiments/PRIVATE-CONVERGENCE.md).

The implemented alpha uses a **bounded-surplus sufficient certificate**, not a
general private sum comparison. Each node knows its own two changes. One Boolean
surplus bit permits a helper to increase exposure after another participant has
provided a compensating reduction. The origin retains its own strict reduction.
Thus accepted honest-peer settlements strictly reduce total debt without exposing
the complete route, remote identities, an aggregate number or exact loop length.
The bit does disclose a capped fact about the preceding traversal.

This implements the 3-to-1 and 2-to-1 direct-trustline examples and the original
3-to-2 repair with increased helper exposure. It rejects some beneficial residual
loops, and random single-branch discovery is not exhaustive. Do not describe the
alpha as reaching 100% of clearing potential or as proving global convergence.
Dishonest protocol peers can fabricate the surplus bit; honest hosted node
execution is the alpha threat model. Hashlocks do not turn it into a Byzantine
benefit proof. These limits are explicit in the protocol note and UI.

## Hosting provides infrastructure, not clearing decisions

Each node receives only its own durable store, its own configured direct peers,
and addressed neighbour envelopes. Actor code neither reads other node stores
nor receives a global optimizer, route, winning-loop choice or benefit oracle.

`HostedRuntime` opens one node transaction at a time. Its local outbox is committed
before an HTTP request is sent. The recipient authenticates the neighbour and
commits independently. A sender removes an outbox entry only after receiving an
acknowledgment; retries are handled by the protocol's idempotent message identities.
There is no database transaction or global lock that settles an entire loop.

Infrastructure may list node identities to schedule independent wakeups. Workers
run several nodes concurrently, and per-node storage locks serialize only local
state transitions. Own-node randomized search timing is stored locally. Scheduling
does not select clearing routes or inspect balances across nodes.

Account enrollment has a separate stable channel-key registry to handle concurrent
crossed invitations. It is account infrastructure, never an algorithm capability.
Installing the relationship is a separate zero-balance transaction at each endpoint.
Retries repair interrupted enrollment without rotating an established peer key.

## Durability and operations

Heroku web processes serve the UI, accounts and local-node APIs; separate worker
processes recover outboxes and initiate explicitly enabled local work. PostgreSQL
is authoritative for accounts and every node. The current compatibility adapter
stores each private in-memory SQLite image in a separate PostgreSQL row, committing
the ledger and outbox together before success. There are no authoritative SQLite
files on an ephemeral dyno. See [storage semantics and tests](HOSTED_STORAGE.md).

This preserves local protocol semantics but incurs O(node-state-size) storage I/O
per operation. It is a small TEST alpha design, not a scale claim. Account/passkey
data are separate from node ledgers. Python capability scoping is not hostile-code
sandboxing or confidentiality from the operator, who can access node data, keys
and hashlock secrets. The enrollment UI discloses that access before account creation.

Missing peers can leave reservations pending indefinitely. Restart/retry is supported;
timeout-based unlocking, stale-backup rollback and Byzantine recovery are not. Do
not restore an old node backup while its peers continue from later ledgers. No
real financial assets or obligations belong in this TEST alpha.

## Validation

Protocol tests use separate local databases and serialized neighbour messages.
Storage tests additionally use real PostgreSQL, independent OS processes and
process death before commit. Account tests generate real P-256 WebAuthn signatures;
gateway tests combine real accounts, PostgreSQL, invitations, obligations and
hashlock fulfillment. Browser tests cover passkey flows and preserve standalone
authentication. See [deployment runbook](HEROKU_DEPLOYMENT.md) for execution commands
and live checks required before calling the target deployed.
