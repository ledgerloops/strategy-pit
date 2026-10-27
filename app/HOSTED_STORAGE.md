# Native PostgreSQL hosted storage

The hosted runtime stores balances, contacts, proposals, reservations, obligations,
receipts, inbox/outbox records, chat and account metadata in PostgreSQL tables.
It does not deserialize, execute or serialize a SQLite database during normal
operation. Historical standalone demos may still use SQLite; the only hosted
snapshot reader is the explicitly invoked offline migration utility.

## Tables and peer isolation

`public.ledgerloops_nodes(node_id, version, updated_at)` is a small provisioning
and worker-wakeup registry. The domain tables live in `ledgerloops_data`.
Every domain row has a required `owner_node_id`, identifying the logical actor
whose state it belongs to. A `peer` field identifies that actor's counterparty;
it is not an isolation boundary. Composite keys include the owner, so unrelated
actors may use the same peer, proposal ID or message ID without colliding.
Balances and counters use PostgreSQL `BIGINT`; they are not limited to a 32-bit
SQL integer. Existing structured protocol payloads remain textual JSON records
inside their appropriate domain rows, rather than a whole-database binary image.

All scoped tables enable and force row-level security, with matching `USING` and
`WITH CHECK` policies. The fixed-node connection sets
`ledgerloops.owner_node_id` using transaction-local `set_config` inside each
transaction. Missing scope denies access. Scope is set on every checkout and
cannot leak to the next borrower of a pooled connection. RLS covers joins and
subqueries, so an omitted owner filter does not accidentally expose another
actor's rows. Auth accounts and enrollment keys have separate infrastructure
scopes and table capabilities; they are not available as actor decision inputs.

The authenticated account-to-node mapping and fixed-node connection are still
application authorization boundaries. Do not accept a caller-selected storage
scope from a browser or expose arbitrary SQL. A custom PostgreSQL setting is not
a credential: code with arbitrary SQL execution could select a different scope.
The host/database administrator retains access. Actor storage rejects database
roles with superuser status or `BYPASSRLS`; configure a restricted runtime role.
Prefer a separate migration owner and remove DDL/TRUNCATE privileges from the
runtime role. `FORCE ROW LEVEL SECURITY` subjects an ordinary table owner to the
policy, but that owner can alter it; superusers and `BYPASSRLS` roles still bypass
it. This is defense against accidental unscoped queries, not a sandbox against a
compromised hosting process or malicious database administrator.

## Transactions and delivery

An outer `with db:` operation:

1. Starts a PostgreSQL transaction and establishes its fixed owner scope.
2. Locks that actor's registry row with `SELECT ... FOR UPDATE`.
3. Executes local ledger, consent, reservation, inbox deduplication and outbound
   intent changes in native tables.
4. Bumps the registry version once if the operation changed domain data, and
   commits synchronously before returning success.

Queries outside a context run as individual scoped transactions. Related reads
and writes must share an outer context. Nested contexts share its transaction;
a nested exception makes the entire outer operation rollback-only even if an
intermediate caller catches it. Read-only operations and ignored conflict inserts
must not create worker wakeups. Different actors can transact concurrently; there
is no transaction settling both endpoints or an entire clearing loop.

Network delivery occurs after releasing the sending actor's transaction. The
receiver commits independently, and successful delivery acknowledgments are then
recorded in a separate local transaction. Failed or uncertain delivery retries
the same stable message IDs and payloads. A transport acknowledgment is not a
financial acceptance. If commit success is uncertain, reload current PostgreSQL
state and retry using the same business ID, not a newly minted operation.

## Migrating existing snapshot storage

The former `public.ledgerloops_node_snapshots` table held one serialized SQLite
image per scope. Native runtime access refuses an unmigrated legacy scope instead
of silently creating a new account, identity or ledger. Schema initialization
alone is not a migration and never resets existing records.

This is an **offline cutover**. Stop every old web and worker process before
migration, retain a verified backup and use the reviewed new source and its
installed dependencies in an administrative environment. Configure `DATABASE_URL`
through the normal secret mechanism without printing its value. Then run:

```sh
python app/migrate_postgres_snapshots.py --confirm-offline
```

`--scope STORAGE_SCOPE` can be repeated for a controlled subset. A complete
cutover must include accounts, enrollment and every node, not just balances.
Normal operation must not resume while required scopes remain unmigrated; the
native release readiness gate checks every legacy scope, not only accounts.

The utility validates each SQLite image and exports only allowlisted tables and
columns. It preserves balances, keys, sessions, credentials, hashes, reservations,
conditions, unreleased secrets, pending messages, processed IDs, history and row
ordering. Unknown tables, columns, views or triggers fail closed rather than
silently discarding state. Earlier invitation schemas can omit fields that have
native defaults. Native constraint failures roll back that scope's entire import.

Each scope's import and its completed source-version/SHA-256 marker commit
atomically. A repeat with the identical source is a no-op; changed source or a
nonempty native destination is rejected. A failed multi-scope run can be resumed;
already completed scopes are not imported twice. Original snapshot images remain
untouched for controlled review/recovery. A guard trigger rejects later writes
from an old snapshot runtime to migrated scopes, including accidental restarts.
Administrative imports explicitly filter destination checks by owner even if
their role bypasses RLS. A schema advisory lock serializes complete imports and
release/schema initialization, and each scope also locks its legacy/native rows.

Compare native records and protocol state with the retained source before
starting the native runtime. Do not log data values or export secrets during this
review. Deploy/restart the native version only after all required imports pass.
No live migration or deployment is performed merely by committing this code.

A rollback to the old implementation after native processing is **not** a code
rollback: original images are now stale. Do not remove the migration fence or
restore those images to release reservations. Stop writers and devise a state-
preserving recovery/cutover first. Before any new processing, a verified abort
of the cutover can be handled administratively; it must explicitly account for
the migration markers and old-writer fence rather than relying on automatic
fallback. Keep retained images until the agreed recovery/retention policy permits
removal.

## Verification

Use a disposable PostgreSQL database, configured without displaying its DSN:

```sh
python -m unittest discover -s app -p test_hosted_storage.py -v
python -m unittest discover -s app -p test_postgres_migration.py -v
```

Real database cases use `LEDGERLOOPS_TEST_POSTGRES_DSN`; they must never target the
live hosted database. The tests cover RLS scope isolation, pooled transactions,
concurrency and rollback, and lossless/idempotent migration with pending work,
old-writer fencing and incompatible-source refusal. Snapshot export unit tests
can run without PostgreSQL. These checks establish the behaviors tested, not a
claim of hostile-process isolation or a completed production deployment.
