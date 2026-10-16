# LedgerLoops hashlock network app

The app now runs a separate **neighbour-private hashlock v2 testnet**: a responsive client, local consent, context-bound SHA-256 fulfillment, durable SQLite state and real neighbour HTTP messages. Participants keep only their incoming/outgoing neighbours for a proposal; no participant list or exact loop length is sent. This implements the honest-peer experimental scope of [issue 004](../docs/issues/004-neighbour-private-hashlock-settlement.md), not a production or Byzantine-safe payment system.

## Run the private network

Python 3.12 is the tested runtime. The service uses only the standard library.

```sh
python3 app/run_private_demo.py --data-dir /tmp/ledgerloops-private-demo --base-port 8861
```

Open Alice at `http://127.0.0.1:8861`, Bob at `http://127.0.0.1:8862`, and Doris at `http://127.0.0.1:8863`. The launcher prints each local config path; use its `token` field to connect the corresponding browser tab. Tokens are randomly generated development credentials. Do not publish configs or use real obligations.

1. From Alice, request exactly **3 TEST** in Clearing.
2. Review and approve your own changes in each of the three tabs. A participant can decline before approval; approval cannot later be revoked.
3. Wait for each local receipt. The browser independently verifies the context-bound fulfillment; it does not claim cryptographic proof of the whole loop's completion.
4. Download a receipt and check it independently:

```sh
python3 app/verify_private_receipt.py downloaded-receipt.json
```

The example clears Alice→Bob 7, Bob→Doris 3, Doris→Alice 5 to **4 / 0 / 2**, preserving each participant's signed net position. The app's discovery uses a single local path and a fixed amount; it can miss other paths or smaller opportunities. It is not the benchmark DFS/Numbat implementation.

Ctrl-C stops the launcher and its nodes. Restart with the same directory to retain state. A fresh directory creates an entirely separate test network. Never delete pending state or restore an old database to free reserved balances.

## Authentication and restarts

Reuse the same `--data-dir` and browser address when updating or restarting a demo. Existing JSON configs retain their client tokens and peer keys; launching a fresh data directory creates a different test network with different credentials. Keep configs and databases together. The browser stores its token per tab and origin, so closing the tab or changing between `localhost`, `127.0.0.1` or ports can require entering the same token again.

If the UI reports a rejected token, use the `token` field from the matching node JSON config in the data directory printed by the running launcher. Alice, Bob and Doris have different tokens. The connection flow ignores delayed authentication responses from an earlier login attempt, so an old rejection cannot clear a newly entered valid token. No token rotation is needed to recover from an incorrect cached credential.

## Contacts and comfort zones

The [address book](COMFORT.md) now supports your own credit grant, personal comfort minimum/maximum and a saved assistance preference. Peer settings synchronize directly; the shared range reflects both perspectives. [The simulation](../experiments/COMFORT-SIMULATION.md) evaluates comfort-assisted moves separately. The app now supports explicit, manually approved [comfort-assisted hashlock settlement](comfort_protocol.md), including helping through zero-balance links. The checkbox grants assistance eligibility; it does not enable unattended execution.

Try the dedicated example with `python3 app/run_comfort_demo.py --data-dir /tmp/ledgerloops-comfort-settlement`. At Alice select **Move toward shared comfort**, request **2 TEST**, and review/approve at each of the three nodes. This clears Alice–Bob while creating two comfortable helper balances: gross debt rises from 2 to 4 while discomfort falls to zero. See [browser instructions](COMFORT.md#network-comfort-browser-exercise).

## Enter new obligations

Open **06 / Obligations** to propose a TEST obligation to a direct peer, review and approve incoming proposals, and list pending/completed/declined entries. Both people must agree before balances change. Obligations appear in Activity and contact history alongside clearing receipts. Proposing reserves the relationship until its outcome is known; there is no proposer withdrawal yet.

For a fresh zero-balance demo with 10 TEST credit grants:

```sh
python3 app/run_obligations_demo.py --data-dir /tmp/ledgerloops-obligations-demo --base-port 8991
```

Enter Alice→Bob, Bob→Doris and Doris→Alice obligations of 3 TEST, obtain each counterparty's approval, then clear 3 TEST through the existing clearing flow. See [obligation instructions, API and recovery limits](OBLIGATIONS.md).

## What hashlocks establish here

Each approval binds a locally stored quote and condition. The origin releases a fresh cryptographically random secret only after readiness has traversed consenting nodes. Every node checks its own consent, reservations and the context-bound secret before applying its own changes. Decisions and forwarding work persist atomically, so retries and crashes do not apply a fulfillment twice.

No node stores an enumerated route, remote origin identity, named vote collection or total-hop count. Under honest, stable, non-aliased node identities, excluding immediate reflection and rejecting repeated non-origin visits establishes the minimum-three requirement. This does not provide Sybil resistance or hide timing, traffic, shared-condition correlations or colluding peers' observations.

Read the exact [private protocol](private_protocol.md), [validation scope](PRIVATE_TESTING.md), and [phone](screenshots/private/mobile.png)/[desktop](screenshots/private/desktop.png) screenshots. Receipts verify the hash relation and local accounting consistency; they are not public signatures or independently authenticated proof that balances were actually applied elsewhere.

## Recovery and deployment boundaries

This is **TEST units only**, with honest peers, retained databases and eventual network recovery. There are no timelocks or unsafe timeout unlocks. An unavailable origin or peer can leave capacity reserved indefinitely. Decline produces an evidenced abort before release; after conditional consent, the participant must await the outcome. Local application can occur at different times across peers.

Only preconfigured direct neighbours are supported. Private v2 nodes can now propose and approve new bilateral TEST obligations within synchronized credit grants. Account enrollment, live assets, public identity/key management, TLS deployment, stale-backup recovery, bounded retention and hostile-peer protection remain product work. Plain HTTP and bearer credentials are for loopback/isolated development only. Localhost URLs refer to the machine running the nodes; no public SaaS has been deployed.

## Versions and tests

V1 remains in `node.py` and `run_demo.py` as a route-visible infrastructure prototype. It is not a validation of the original private protocol. [Its protocol](protocol.md), [historical tests](TESTING.md) and result pins remain available. V1 and v2 refuse each other's databases; there is **no in-place migration of pending work**. Finish or retain legacy work using its original runtime, and provision v2 separately.

```sh
python3 -m unittest discover -s app -p 'test_*.py' -v
```

This runs actual local socket/process tests plus state-machine and receipt checks. Browser tests additionally require Playwright and Chromium; start a fresh private demo first:

```sh
APP_DEMO_DIR=/tmp/ledgerloops-private-demo APP_BASE_PORT=8861 \
  APP_PROTOCOL=private-hashlock-v2 node app/test_browser.cjs
```

Set `CHROMIUM_PATH` if needed. The browser test clears the fixture and leaves Alice paused; use a fresh network directory for repeated complete runs. [Private validation evidence](PRIVATE_TESTING.md) states exactly which failures and privacy checks were exercised.
