# LedgerLoops network app

A first runnable testnet implementation of the [product PRDs](../docs/product/README.md): a mobile-friendly web client, independent persistent nodes and neighbour HTTP messages. Uses **TEST units only**. This is an engineering testnet, not a service for real obligations.

**Architecture status:** this is an honest-peer infrastructure prototype. Its route lists and named approvals do not meet the original LedgerLoops neighbour-only knowledge requirement. [Issue 004](../docs/issues/004-neighbour-private-hashlock-settlement.md) tracks restoration of hashlock settlement without revealing remote participants or exact loop length; the current tests do not validate that protocol.

## What this milestone proves

The goal is to run the same flow against actual processes and separate databases: connect to your node, inspect your own peer balances, discover a clearing loop, review local changes, approve, and retrieve a durable receipt. Dropped connections and process restarts exercise recovery rather than an in-memory simulation.

The initial network is a known, preconfigured trading circle. Provisioning establishes bilateral test balances and trusted neighbour credentials. User enrollment, arbitrary imports, production identity/key recovery, hosted billing and public Internet deployment remain separate milestones.

## Trust and recovery limits

The protocol assumes trusted non-equivocating peers, persistent local storage and eventual network recovery. It does not tolerate an operator rewriting its database, restoring stale backups, stealing credentials or forging decisions as a compromised participant. Do not delete or restore an old database to unblock a reservation.

The proposal origin coordinates a durable decision. Coordinator or peer failure can block work indefinitely; a timeout does not make reserved capacity safe to reuse. Local durable application and confirmation that the whole cycle completed are distinct states. Read [the protocol](protocol.md) for the exact implemented transitions.

Each participant routes using its own neighbours. A route token can reveal traversed identities to participants; locality does not imply route privacy. The loopback development transport is HTTP. External deployment needs authenticated encrypted transport, proper identity/key management and a separate security review. Never expose the demo ports directly to the Internet or use real financial data.

The web client and node have separate lifetimes: closing the page does not roll back admitted work. Credentials entered in the client authorize operations on that test node; they are not a production cryptographic signing/recovery scheme.

## Implementation boundaries

The client uses node responses rather than simulated success. Approval, reservation, durable local application and completion are displayed separately. Amounts are exact integer TEST units. SQLite transactions retain decisions, deduplication and retry work across process restarts. No live mode or bank payment integration is provided.

Research implementations remain in `experiments/`; this app does not change their pinned sources. Product requirements not yet implemented stay requirements, not implicit guarantees. The network test report documents the fault cases actually exercised; it is not an exhaustive proof of the protocol.

## Run a private three-node network

Python 3.12 is the tested runtime. The service and network harness use the standard library; no database service or package installation is required.

```sh
python3 app/run_demo.py --data-dir /tmp/ledgerloops-demo --base-port 8761
```

Open Alice at `http://127.0.0.1:8761`, Bob at port `8762`, and Doris at port `8763` in separate tabs. Each node uses its own database. The launcher prints the location of its local configuration; use that node's `token` field to connect the browser. Those are newly generated development credentials: keep them private and never commit the runtime directory.

The fixture is Alice owing Bob 7 TEST, Bob owing Doris 3 TEST and Doris owing Alice 5 TEST. Discover an amount of 3 from Alice and inspect/approve the proposal at each node. Once completed, Alice owes Bob 4, Bob owes Doris 0, and Doris owes Alice 2. The signed net positions remain Alice −2, Bob +4 and Doris −2.

Stop the launcher with Ctrl-C; rerunning with the same directory resumes the same records. A fresh directory creates a separate new test network. Never mix old databases with regenerated identities/configuration. The localhost URLs refer to the machine running the launcher, not a publicly hosted service.

## Reproduce the network checks

```sh
python3 -m unittest discover -s app -p 'test_*.py' -v
```

Tests start temporary loopback processes and clean up their own directories. They need local socket/process permissions. Run them on a development machine or an execution environment that permits those operations. No public peers are contacted.

See [tested fault cases and browser reproduction](TESTING.md), [phone screenshot](screenshots/mobile.png), and [desktop screenshot](screenshots/desktop.png).
