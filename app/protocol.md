# Neighbour clearing testnet protocol

This app exchanges real HTTP messages between separate processes, with each node owning its own SQLite database. It is an **honest-peer, crash-and-restart testnet using integer TEST units only**. It cannot manage money. No account registration, real assets, external transfers, interest, or new credit are implemented.

## Local ledger and discovery

A positive local balance means that peer owes this node; a negative balance means this node owes its peer. The launcher installs mutually consistent bilateral fixtures. A node stores only its own peer balances and neighbour URLs/credentials; startup does not independently prove the fixture matches its peers. Each completed cycle preserves every node's signed net position and decreases all involved absolute balances without creating new debt.

Discovery chooses the first unreserved outgoing debt neighbour in local identifier order. Subsequent nodes choose one outgoing positive-debt channel, cap the amount to local capacity, and carry a bounded path token. Returning to the origin closes a cycle of at least three nodes. This is a **greedy single-path search**, not exhaustive DFS or the benchmark Numbat algorithm. It can miss available cycles. Search state reports `searching`, `cycle_found`, or `no_cycle_on_path`. Offline peers keep searches pending until delivery resumes. There is no economic optimality claim.

New discovery cannot traverse zero balances. Previously admitted control messages retain the configured neighbour channel to finish settlement after balances become zero. A node learns the discovered cycle's participants, not the whole network graph.

## Durable settlement

1. The origin prepares its local two incident balances and sends a prepare token around the discovered ring. Each participant validates its incoming and outgoing balances, reserves both edges, records immutable local before/after changes, and forwards the token. Reservations prevent simultaneous proposals modifying those edges.
2. Participants manually approve their local proposal, or decline before approval. A decline durably disables approval locally and routes rejection to the coordinator for ABORT; it cannot revoke an existing approval. The API requires the SHA-256 digest of the exact displayed immutable proposal. Approvals become durable local records; votes travel via adjacent ring neighbours to the origin.
3. Only after the prepare token returns and every participant's vote arrives does the origin record COMMIT. A failed prepare instead routes a rejection to the origin, which decides ABORT. Participants never release reservations merely because time passes.
4. COMMIT/ABORT moves around the ring. Each participant atomically records the decision, applies its own balance changes at most once, releases reservations and records a local receipt, with its forwarded message in the same transaction. Unknown aborts create durable tombstones; duplicates cannot resurrect a proposal.
5. The returning decision confirms every node has applied it. The origin sends a completion notice around the ring. A receipt's `cycle_complete:false` means only the local decision/application is known; `true` records receipt of whole-ring acknowledgement evidence.

Each inbound message ID is deduplicated in the same SQLite transaction as the state change and forwarding outbox. Acknowledgement loss therefore causes harmless replay. New transport retries reuse the same message ID. The outbox persists across restarts and retries neighbour delivery. SQLite uses WAL and FULL synchronous mode. Pausing rejects fresh discovery/preparation/approval while existing commit/abort delivery continues.

Participants bind subsequent messages to their stored path and amount. Direct peers use separate bilateral bearer credentials; UI requests use a distinct per-node bearer credential, JSON content type and same-origin writes. Keys are never returned by the state API. Local server defaults to loopback. The demo's plain HTTP is appropriate only on loopback/trusted isolated test networks; TLS, credential rotation and hardened serving are not provided.

## Failure and deployment limits

A coordinator outage can leave reservations blocked until its original durable database returns. No timeout cancellation, coordinator election, permanent-node-loss recovery or backup rollback is implemented. Do not restore an old snapshot, delete a database, or start multiple processes on one logical node's database to escape pending work. Keep test databases and credentials together. Reset a demo only by stopping all nodes and creating an entirely new testnet.

This is staged application, not simultaneous visibility: during delivery, bilateral views can temporarily differ. Receipts explicitly distinguish local commitment from whole-cycle completion. The protocol assumes honest participants and authenticated transport: a malicious peer can forge votes or lie about remote forwarding, and this is not Byzantine-safe. Credentials authenticate links, not legal identities. There is no public signature evidence, production consent policy, security audit, durable-consensus service or live ledger reconciliation.

There are no balance revisions or external transaction APIs in this slice because fixture balances can change only through locally reserved proposals. Adding payments, transfers, trustline changes, currencies or headroom requires explicit bilateral versioning and new protocol validation. Tables retain inbox IDs, proposals, receipts and abort tombstones indefinitely. The server and worker are deliberately small; admission quotas, backpressure, scalable retries, metrics and bounded retention remain product work.
