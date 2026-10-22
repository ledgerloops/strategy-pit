# ledgerloops.com hosted alpha — design discussion

22 October 2026. Initial design discussion, subsequently authorized for
implementation and deployment by the user. The canonical target is now
`app.ledgerloops.com`. See the [implemented hosting architecture](../../app/HOSTED_ALPHA.md)
and [deployment runbook](../../app/HEROKU_DEPLOYMENT.md) for current implementation
status. This note retains the agreed constraints and original design rationale.

## Agreed constraints

- Host the demo/alpha at `app.ledgerloops.com`; shared hosting is acceptable.
- Disclose that the operator can access hosted node data and controls the runtime.
- Preserve neighbour-private algorithm messages and coordinator-free clearing.
- Never use cross-node visibility to choose probes, routes, amounts, approvals,
  progress decisions, reversals or winning loops. Hosting is infrastructure only.
- The user subsequently authorized implementation and deployment; do not treat
  this earlier discussion as an approval gate.

## Proposed product scope

A hosted TEST network where people create an account, establish a mutually agreed
trustline, set comfort zones, propose/approve obligations and observe real private
hashlock clearing and its history. This proposal makes the existing working test
features available to alpha users; it does not turn them into live financial
obligations or claim complete clearing. It extends the earlier read-only-alpha
proposal, and remains a scope proposal for review.

One account controls one stable logical node initially. Display names, app user
identity, node identity and peer credentials remain separate. The browser can
sleep or close while its hosted node delivers and recovers messages. Approval
requirements and any explicit automatic-consent policy must be visible to the user;
creating an account does not authorize unattended settlement.

## Hosting must not change the protocol's powers

| Component | Permitted responsibility | Excluded responsibility |
| --- | --- | --- |
| Website and authentication | Authenticate people; send their commands to their own node; show their local state | Calculate global clearing routes or approve for other nodes |
| Node runtime | Own balances, preferences, reservations, local search memory and direct-neighbour messages | Read another node's database, query a shared credit graph, or receive a global optimizer's answer |
| Message transport | Authenticate and deliver addressed protocol envelopes, including retries and ACKs | Select economically preferable loops or synthesize consensus/completion |
| Worker infrastructure | Fairly schedule independent local work and recover crashed workers | Serialize the entire clearing network to make an otherwise failing protocol work |
| Observer | Read-only authorized diagnostics and synthetic-demo graphs | Feed graph-wide findings back into discovery, acceptance or settlement |

Use the same node state machine behind hosted and separately deployable storage/
transport adapters. Participants receive a capability to their own durable store
and an addressed send interface. Do not pass other node objects, a database
administrator connection, a membership roster or a graph accessor to node code.

Every balance decision, reservation and outbox write is a **local** durable
transaction. A shared database must not perform a cross-node SQL transaction that
silently settles a whole loop. Another node learns the result only through an
actual protocol envelope. Partial fulfillment, stale quotes, duplicate delivery,
loss and recovery remain possible and visible.

One physical machine or managed database can serve multiple logical nodes. Use
node-scoped permissions, process boundaries where useful, and concurrent workers;
one paid dyno per person is not a requirement. Within one node, a local single-writer
lease is compatible with the actor model. A network-wide settlement lock is not.

The host still has administrative power, so this is an honest hosted execution
model, not confidentiality or tamper resistance against the operator. Read-only
graph instrumentation in synthetic demos must be visibly separate; real account
records should not appear in a public graph by default.

In the proposed first TEST alpha, node protocol credentials and hashlock secrets
would reside in the hosted runtime. Passkey private keys stay with users'
authenticators, but passkey login does not remove trust in the operator running
the node or authorize automatic clearing. That custody model must be stated
plainly during enrollment.

## Proposed accounts: passkeys plus sessions

- Persist a server-side account/node identity independently of browser storage.
- A passkey authenticates the account; an opaque session cookie keeps that browser
  signed in. Use Secure, HttpOnly and appropriate SameSite/CSRF controls. Clearing
  a cookie signs out the browser; it does not delete or recreate its node.
- An optional guest preview can show the demo. Require account enrollment before
  creating persistent user obligations, rather than making a cookie the only
  recovery mechanism.
- Allow a second passkey and define recovery before launch. Synced passkeys help
  with devices, but are not a complete recovery policy. Consider one-use recovery
  codes; login recovery must not rewrite ledger history or rotate node identities.
- Choose the canonical HTTPS origin and passkey RP ID for `ledgerloops.com`
  before enrollment. Do not register the alpha's lasting credentials against a
  temporary `herokuapp.com` domain. Stage/test credentials remain separate.
- Passkey login is not itself a signature authorizing an arbitrary settlement;
  proposal approval and the node's hashlock evidence remain separate operations.

Server verification must bind each authentication to a fresh challenge, the
expected origin/RP ID and required verification flags, using a maintained WebAuthn
library. See the [passkey server authentication guidance](https://developers.google.com/identity/passkeys/developer-guides/server-authentication).

## Heroku is a viable proposal, not a completed deployment

A plausible small managed setup is:

1. A web process serving the app, authentication and authenticated local-node APIs.
2. Background worker processes running independent node state machines and durable
   message delivery, separately from HTTP request lifetimes.
3. Durable PostgreSQL storage for accounts, local ledgers, reservations and outboxes,
   with node-scoped access. A queue may manage delivery scheduling; it is not the
   authority for financial state or completion.
4. The custom HTTPS domain, backups and a tested restart/recovery procedure.

The current app uses per-node SQLite files. Heroku's dyno filesystem is ephemeral:
writes disappear on dyno restart. Therefore those files cannot be deployed there
as the sole durable ledger. A PostgreSQL storage adapter/migration is substantive
work, including preservation of local transactional semantics. Do not copy the
existing launcher onto a dyno and assume its persistence guarantees survive.

Sources: [Heroku filesystem semantics](https://devcenter.heroku.com/articles/dynos#ephemeral-filesystem)
and [worker processes and queueing](https://devcenter.heroku.com/articles/background-jobs-queueing).
No hosting price, capacity or production availability promise is made here.

## What must be demonstrated before calling it a realistic hosted alpha

- The same protocol scenarios work with separately isolated nodes; removing
  observer/admin access cannot change clearing decisions.
- Cross-node store access and whole-loop database transactions are denied.
- Concurrent requests, delayed/lost/reordered messages, duplicate delivery and
  worker restarts preserve local accounting and honest pending states.
- Joining/accepting a peer is a bilateral operation; dynamic peers and accounts
  replace the current manually preconfigured demo topology without global discovery.
- Passkey enrollment, sign-in, logout, second-device access and recovery preserve
  the account's node and outstanding protocol work.
- The UI distinguishes TEST units, local fulfillment, pending peer completion,
  operator access, and the algorithm's incomplete convergence guarantees.

The [convergence analysis](../../experiments/PRIVATE-CONVERGENCE.md) is independent
of this hosting choice. Global variables used in a mathematical proof or offline
checker are not runtime capabilities granted to participants.
