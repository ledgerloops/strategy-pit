# Comfort-assisted hashlock network tests

`test_comfort_settlement_network.py` runs independent Python node processes, each
with its own SQLite database, over loopback HTTP through instrumented forwarding
proxies. The harness alone knows the generated graph. Participants receive their
own balances, direct-neighbour keys and preferences; protocol messages do not
receive the harness's full graph.

Run from the repository root:

```sh
python3 -m unittest discover -s app -p 'test_comfort_settlement_network.py' -v
```

The fixtures give one relationship a balance of two TEST units outside a shared
comfort interval of `[0,0]`. The remaining relationships start at zero with
shared comfort `[-4,4]`, hard limits `[-10,10]`, and both endpoints opting into
assistance. Discovery requests amount two explicitly in comfort mode. Every
participant still approves the specific locally displayed proposal manually.

The completed three-node example clears the uncomfortable balance but creates
two balances of two units inside their respective comfort zones. Gross internal
debt increases from two to four: this is assistance according to the agreed
comfort objective, not evidence of greater debt cancellation.

Coverage:

- Three- and five-node zero-balance helper rings, opposite signed directions,
  strict origin improvement, and no economic changes before the last approval.
- Conservation of every participant's net balance, antisymmetric bilateral
  balances, exactly one receipt per settlement, and released reservations.
- Captured messages, node databases and API state inspected for identities
  outside the node's own direct neighbours. The five-node fixture makes this
  check non-vacuous. Existing wire audit also rejects path, participant-list,
  length and hop-count fields.
- Delivered fulfillment with a lost HTTP acknowledgment, causing durable replay
  without a second balance application.
- An approved helper crashing and restarting while peers continue, preserving
  its proposal digest, pinned changes and consent.
- Origin crash after irreversible preimage release with a sleeping recipient;
  eventual delivery completes the original settlement after restart.
- Two origins starting overlapping discovery behind a transport barrier, then
  racing to reserve shared edges. Either one proposal survives or both abort;
  the test requires drained protocol traffic, no partial economic change, and
  no leaked reservation after resolution. This permits safe loss of progress,
  not an unconditional concurrent liveness claim.
- A second discovery and preference edit rejected while an already prepared
  proposal holds its edge reservations.
- A preference revision changed between discovery and preparation aborting the
  stale proposal without economic changes or stranded reservations.
- A helper with no uncomfortable balance cannot initiate neutral churn.

These are deterministic fault injections, not a statistical availability study.
They cover honest peers and crash/replay transport behavior. They do not prove
Byzantine atomicity, fairness under indefinite partitions, cryptographic
anonymity, absence of timing metadata, or production suitability. No wall-clock
expiry is introduced to release already approved obligations. Refer to
[the private protocol](private_protocol.md) for cancellation and recovery limits.

The parent integration run records the exact test count and source hashes; this
document describes executable coverage, not a substitute for that result.
