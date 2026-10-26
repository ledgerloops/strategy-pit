# Atomic ledger engine

This crate starts the agreed Atomic backend replacement for LedgerLoops. It is
an implementation foundation, not the backend running at app.ledgerloops.com.
The hosted Python app still uses the separately reviewed native PostgreSQL
storage in [PR #47](https://github.com/ledgerloops/strategy-pit/pull/47).

The new design stores typed application state in actual Atomic Resources and
uses Atomic's Loro document, signed commit, indexing and storage paths. It does
not translate existing SQL queries into Resource operations. PostgreSQL remains
the durable storage medium for Atomic's individual resource/index keys, rather
than storing database images or relying on a Heroku dyno's ephemeral disk.

## Boundaries implemented here

- `model`: versioned signed messages, exact integer amounts, sender sequence and
  hash chains, idempotency checks, gross directional reservations and bilateral
  checkpoint signatures. The integer JSON signing format is specified in code;
  it is not advertised as RFC 8785.
- `bilateral`: a pure reducer for explicit-consent obligations using
  offer → accept → commit → settled. The proposer retains its reservation until
  settlement confirmation. A reducer call alone is not a durable transaction.
- `actor_store`: one private Resource holds an actor's state, request receipts
  and durable outgoing intents. A local log projection can resume after a crash,
  appending each signed message with Atomic's native Loro list operation.
  Projection completion means the local Resource exists; it does **not** mean
  another peer acknowledged receipt or settlement.
- `postgres_store`: an actual `atomic_lib::KvStore` implementation with atomic
  batches, byte ordering, forced namespace RLS, verified TLS and an exclusive
  connection-lifetime writer lease. Fixed-size key digests avoid PostgreSQL's
  B-tree key-size limit; a digest conflict fails rather than overwriting a key.

Atomic is pinned to the immutable constructor change in
[ontola/atomic-server#2371](https://github.com/ontola/atomic-server/pull/2371).
The adapter currently uses some `Db` operations documented as internal. Those
calls are isolated here; this is first-party integration work, not a promise
that those operations form a stable external API.

## State and trust

Each trustline has two sender-authored log Resources. Each message additionally
has its own Ed25519 signature and channel/incarnation context. An Atomic commit
authenticates a Resource edit; the inner message signature authenticates a
protocol assertion even when the application service publishes the Resource.
Neither signature turns a CRDT merge into financial consent.

Private actor state lives under the service signing agent's private drive.
It must not be synced to participants as public channel data. RLS selects the
Atomic backend namespace, not an authenticated browser's peer identity. The
future service must authenticate a session and authorize its actor separately.
RLS is defense against omitted scope filters, not a sandbox against the trusted
backend or a database administrator.

Run one authoritative Atomic node per PostgreSQL namespace. Its session lease
rejects a second independently opened writer. Clone the existing node/store
inside the process. Actor-store wrappers over cloned nodes share a lock registry,
and lock keys normalize equivalent Resource identifiers. Do not change the default
signing agent per request. Each sender log must have one canonical actor owner;
stable actor lookup and authorized log creation remain service responsibilities.
Buffered batches are a backend initialization facility, not concurrent actor
transactions or a rollback API.

Ordinary obligations currently require the resulting balance inside fixed
bilateral bounds. Clearing, changes to preferences during pending transactions,
and reductions of grandfathered debt outside lowered limits need explicit
protocol handling before cutover. Prepared or approved reservations never
silently expire while a counterparty may still commit.

## Reproduce

Use Rust 1.98.1, OpenSSL headers and pkg-config. The lockfile pins dependencies.

```sh
cd atomic-ledger
cargo test --locked
cargo clippy --locked --all-targets -- -D warnings
```

Database tests require a **disposable** PostgreSQL database and an ordinary role
with neither SUPERUSER nor BYPASSRLS. The role must own/create the test tables.
They create isolated namespaces and inject test failures. Never point this suite
at a hosted or personal database.

```sh
LEDGERLOOPS_TEST_POSTGRES_DSN=postgresql://local_test_owner@localhost/atomic_test \
  cargo test --locked -- --ignored
```

Plaintext connections are available only through the explicit `connect_no_tls`
test API. Deployment connections use `connect` with certificate and hostname
verification. Native database errors are sanitized to avoid exposing payloads
or credentials. Range scans currently filter and sort full keys per namespace
and tree; no production performance claim has been established.

The PostgreSQL client lives on its own database thread, including construction
and destruction, so it works inside both Tokio runtime flavors. The synchronous
KV trait still blocks callers while awaiting a database result.

## Complete replacement before cutover

The owner chose a coordinated overhaul because LedgerLoops has no production
users. This branch does not deploy a transitional dual-authority backend.

Remaining work is to provide authenticated typed service commands, persist the
service and per-peer signing identities without rotation, import all existing
accounts and peer protocol state, port clearing and preference changes, and
connect browser-local Atomic storage and subscriptions to the service. Log
creation needs participant ACLs, public ontology publication and reconciliation
over a real transport. The existing HTTP actions and polling UI have not switched.

Cutover requires migration and crash/reconnect tests proving preservation of
account sessions, keys, balances, pending locks, unreleased secrets, historical
receipts and outbound work. A prepared, approved or partially applied transfer
must resume under its original terms; importing just current balances is unsafe.
Deploy only after those gates pass and a source-pinned cutover has been reviewed.
