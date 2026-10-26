# Hosted LedgerLoops TEST alpha

Target: **https://app.ledgerloops.com**. The user authorized implementation and
Heroku deployment on 22 October 2026. A target URL is not evidence of a successful
deployment; the deployment record must include the actual release and live checks.

## What is implemented

- Browser-bound demo identities: enter a display name once, then return with the
  same opaque cookie. No passkey, password or recovery-code setup is required.
- Secure, HttpOnly, SameSite=Lax cookies persist for one year, renewed when the
  app resumes the browser identity. Authenticated writes retain exact Origin and
  CSRF checks. Cookies contain no node balances or protocol credentials.
- Clearing cookies, cookie expiry, private browsing or a different browser starts
  another identity. There is no demo account recovery. Existing account records,
  passkeys and sessions are retained; legacy passkey APIs remain available.
  Recovery-code issuance/redemption is disabled by default; the explicit server
  setting `LEDGERLOOPS_RECOVERY_CODES_ENABLED=1` restores the legacy feature.
- Named invitations create private `https://app.ledgerloops.com/#invite=…` links
  containing the inviter's name and intended peer name. The secret stays in the
  fragment, outside server request paths. Preview discloses names, expiry and the
  inviter's chosen maximum trust. An invited newcomer enters their name and own
  maximum, then explicitly connects in one step. Returning browser identities
  remain the same account; a display name is never an authentication credential.
- Both parties independently select maximum trust, prefilled with 10 TEST. For
  MAX, new local preferences are credit MAX and comfort [-MAX, floor(MAX/2)],
  with bilateral assistance enabled. Default shared comfort is [-5,5]. Whole TEST
  units round the positive half down for odd maxima. Existing relationship bounds,
  keys, labels, custom opt-outs and balances remain unchanged.
- Before the first peer, the home shows the name and an invitation action only.
  The operational view lists peers, named balances and shared comfort bands.
  **Invite a peer** and **Record a value delivery** open native modal dialogs
  (full screen on phones), with keyboard dismissal and retained drafts.
- A value delivery records goods or services moving from the selected provider
  to their peer. Its TEST amount adds to the current balance; the form previews
  exactly who will owe whom. Sending and confirming are explicit actions without
  extra consent toggles. The other peer must confirm before posting. API/storage
  names retain `obligation` for compatibility.
- **Rename** saves a private label on the selected direct relationship. It never
  changes the other participant's identity, their own labels, balances or limits.
  **Send message** is available even on zero-balance or reserved relationships.
  Outgoing text and its stable request ID are committed with the sender's durable
  outbox; authenticated neighbour HTTP delivers it into the recipient's own store.
  Retries and duplicate delivery preserve a single record on each side. Delivered
  means the recipient's node committed it, not that the person has read it.
- **View history** combines this peer's incoming/outgoing messages, value delivery
  records and completed loop clearings in date order. It filters by direct peer
  before paging 100 entries at a time; Load earlier retrieves older records.
  Aborted discovery attempts are omitted from this operational history, while
  protocol audit records remain available in the existing advanced activity view.
  Message text and private labels are rendered as text, with retained drafts and
  stable-ID retry/reconciliation if a send response is lost. Financial protocol
  envelopes take priority over chat in the worker's outgoing batch.
- Real cancellation and [comfort-zone headroom clearing](headroom_protocol.md),
  with local reservations, context-bound SHA-256 fulfillment and durable retries.
  Hosted clearing runs automatically in the background within bilateral comfort
  permissions; it never confirms new value deliveries. Discovery is opportunistic,
  not exhaustive, and sleeping peers can leave work durably pending. The hosted
  clearing view reports status without manual loop discovery or approval controls.
  Standalone research controls remain available in the original local demo.
  Hosted searches only originate where the existing strict origin surplus rule
  can be met locally (both positive and negative eligible exposure). Other nodes
  still forward, approve and recover admitted work. Repeated unsuccessful searches
  with unchanged balances/preferences back off to five minutes; own balance or
  exchanged preference changes restart fast attempts. Idle wakes do not publish
  new durable writes merely to move a clock deadline.
  Infrastructure polls only actor registry identity/version metadata every half second.
  Changed versions wake their actor promptly; unchanged actors wait for their
  own search/outbox retry deadline, with a bounded 60-second safety heartbeat.
  Registry metadata never supplies another actor's balances or a routing decision.

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

One Basic Heroku web dyno runs Gunicorn for the UI, accounts and local-node APIs
alongside a background worker that recovers outboxes and initiates explicitly
enabled local work. `hosted_single.py` supervises both process groups: either
service exiting fails the dyno, and termination stops both with bounded cleanup.
There is no separately billed worker dyno. PostgreSQL
is authoritative for accounts and every node. Hosted storage uses native tables
with a required `owner_node_id`, composite keys and forced row-level security.
Each actor locks its own small registry row while updating ledger records and
outgoing work in one PostgreSQL transaction. Hosted operations do not open,
deserialize or rewrite SQLite databases. Existing installations require the
explicit offline [snapshot migration](HOSTED_STORAGE.md) before this code starts.

Account/passkey and enrollment tables have separate infrastructure scopes. RLS
protects against omitted owner predicates, not hostile backend code or an
operator who controls database credentials and scope selection. The operator
can still access node data, keys
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
hashlock fulfillment. Browser tests cover persistent demo cookies, distinct browser
identities, named invitation links through signup and explicit acceptance, while
preserving standalone authentication. Legacy WebAuthn signatures remain tested. See [deployment runbook](HEROKU_DEPLOYMENT.md) for execution commands
and live checks required before calling the target deployed.

## Capacity and storage maintenance

Native row triggers mark actual inserts, deletes and changed updates; the actor
version advances once per changed outer transaction. Read-only operations,
identical updates and ignored inserts do not wake other workers. Protocol records
are not pruned merely to reduce database size. Monitor row/index growth and
PostgreSQL vacuum behavior as history grows.

Application connections bound statements to 30 seconds, lock
waits to five seconds and idle transactions to 30 seconds. Unused pool connections
expire after 30 seconds; the two web workers and background worker each cap their
pool at three, leaving headroom within the Essential-0 connection limit.
Successful outgoing acknowledgments are coalesced into one own-node commit per
batch; receiver deduplication still makes retry after a crash safe.

Legacy images remain retained and fenced after migration; they are not the live
store. Do not resume the old binary or restore stale images after native ledger
operations. See the migration runbook for the stop/import/verify/cutover boundary.
Test backups and recovery against peer-visible protocol state, not only database
integrity. Maintenance mode alone does not stop background work.
