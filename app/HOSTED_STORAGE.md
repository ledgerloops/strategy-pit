# Durable hosted node storage

The alpha's `hosted_storage.py` adapter keeps each logical node's SQLite database
image in a separate PostgreSQL row. SQLite is used **in memory** as the existing
state machine's SQL engine. There is no authoritative database on a Heroku dyno's
ephemeral filesystem and no background backup interval during which accepted
settlements could disappear.

An outer `with db:` operation:

1. Borrows a PostgreSQL connection and starts a transaction.
2. Locks and reads only its assigned node row, including its version.
3. Loads that image into a fresh private in-memory SQLite connection.
4. Executes local ledger, consent, reservation and outbox changes together.
5. Serializes the committed SQLite image, updates the same PostgreSQL row and
   version, and commits PostgreSQL synchronously before returning success.

Any exception rolls back PostgreSQL and discards the in-memory state. If a network
failure makes commit success uncertain, the next operation reloads PostgreSQL;
the caller must retry using the protocol's stable idempotency identifiers.
It must not create a fresh operation identifier merely because a response was lost.
No messages should be delivered until their durable outbox transaction completes.

Each node has its own row lock. Different nodes can transact concurrently. There
is no shared lock around an entire clearing loop, and no SQL transaction applies
both endpoints' ledgers. A node learns its neighbour's outcome through protocol
messages, including ordinary retries and duplicate handling. Several worker
processes acting for the same node serialize only that node's local transactions.

## Provisioning and use

Infrastructure creates one `PgStoreFactory(DATABASE_URL)` per process, calls
`initialize()` during release/migration, and `create(key)` to provision a node.
The factory's `connection(key)` returns a fixed-key actor capability; it never
accepts a different key in an actor query. `list_nodes()` exists for infrastructure
scheduling only and must not be passed to search or acceptance logic. Account and
registry state use separate, explicitly named keys and are not node capabilities.

Initialize a new actor under an outer store transaction so its schema and protocol
metadata are created atomically:

```python
db = factory.connection(node_key)
with db:
    node = Node(config, ':memory:', connection=db)
```

The adapter supports `execute`, `executemany`, `executescript`, `row_factory`,
materialized SQLite-style cursors, nested contexts, and `close`. Queries outside
an explicit context run as individual transactions. Use the context for all
related reads and writes; do not use manual `commit()` calls. An exception in a
nested context makes the whole outer transaction rollback-only, even if the
caller catches that exception.

Only the assigned SQLite image is visible to actor SQL. Database attachment,
detachment and extension loading are denied. The privileged factory and its
connection pool belong to trusted hosting infrastructure. This is a software
capability boundary, **not** a sandbox against arbitrary Python execution or
confidentiality against the operator/database administrator. It must not be
described as database-role isolation between hostile hosted node processes.

## Alpha limits

This deliberately preserves existing SQLite semantics rather than translating
the protocol's SQL into PostgreSQL syntax. Each operation reads and serializes
O(node-state-size) bytes; each state-changing transaction writes that image.
The model is suitable for a small TEST alpha, not a claim of production scale.
Connection pools are bounded per process, but retained ledger history grows.
Measure database size, transaction latency and pool pressure before increasing
the participant count. A native node-scoped PostgreSQL schema remains future
scaling work. An old backup must never be restored as an active node while peers
continue on later state; normal database backups do not solve protocol rollback.

## Verification

The real PostgreSQL tests use a disposable database selected by
`LEDGERLOOPS_TEST_POSTGRES_DSN`. They create randomly named test rows and remove
only those rows afterward. Do not point the test runner at production.

```sh
python -m unittest discover -s app -p test_hosted_storage.py -v
```

Tests exercise independent OS processes with no lost updates, process death
before commit, ledger/outbox atomic rollback, restart and idempotent provisioning,
independent-node overlap, actor SQL isolation, and real private hashlock nodes
restarting after partial approval and completing from PostgreSQL alone.
