# Shared comfort zones: first local-routing experiment

This experiment tests economic preferences and neighbour-local discovery. It is
**a serialized, reliable simulator**, not a production hashlock settlement
protocol or a fault-tolerance benchmark. The app's existing cancellation-only
private settlement does not automatically execute these new assistance moves.

## Model

A positive balance means the peer owes the current node. Each endpoint specifies
its hard credit grant, personal minimum and maximum, and assistance permission.
The shared zone intersects the local range, the reflected peer range, and the
bilateral hard limits. The simulator imports the app's actual `shared_comfort`
model. An empty intersection disables comfort-assisted routing; it is counted
separately, not treated as zero dissatisfaction.

Discomfort is the distance of a balance from its shared zone, counted once per
relationship. The comfort policy requires every changed edge's discomfort to
stay constant or fall, and the initiating edge's discomfort to fall strictly.
A neutral-discomfort move or an increase in absolute exposure requires both
assistance opt-ins. A strictly discomfort-reducing debt decrease uses the
baseline cancellation-consent assumption; the simulator does not model an
interactive approval UI.
Thus local approval establishes improvement without querying a global score.
The simulator verifies the total improvement afterward for auditing only.
Movement toward a zone from outside it is allowed; newly increased discomfort
is not. Both endpoints validate their own side of each proposed change.

The comparison policy permits only reductions in absolute balances, ignoring
comfort. Neither policy is optimal. Comfort can deliberately preserve debt that
both endpoints want to retain. Fixtures contain only zones including zero,
start inside hard bounds, and hold preferences fixed; this experiment does not
exercise lowered limits below existing debt or preference-update races.

Explore the [interactive synthetic example](comfort-demo.html) (download/open the HTML, or serve this directory locally). [Screenshot](results/comfort-demo.png). The example visualizes the recorded unit moves; it does not connect to a real node.

## Illustrative result: more debt, less discomfort

A owes B 2, with a shared preferred balance of zero. B–C and C–A each start at
zero and permit balances between −2 and +2, with both peers opting in.
Cancellation-only finds no cycle of existing debts. Comfort assistance completes
two unit moves: A–B becomes zero and each other relationship has absolute balance
2. **Total debt rises from 2 to 4 while discomfort falls from 2 to 0.** Every
node's signed net position stays identical. This is preference improvement, not
an assertion that more debt was cancelled.

## Reproducible first comparison

Eight fixed seeds, twelve nodes, a ring plus independently sampled additional
edges, integer initial balances −6…6, independent endpoint comfort half-widths
0, 2 or 4, and generous hard limits of 100. Both policies receive identical
starting inputs and external transfer sequences. All assistance is opted in.
Static runs allow at most 10,250 probe/rejection messages. Temporal runs allow
250 initially and 250 after each of 40 arriving signed transfers, without a
final drain. Unused per-arrival service allowance is discarded. The temporal
fixture updates pre-established links, including zero-balance links; it does
not yet add previously unknown contacts.

Aggregates across eight seeds per row:

| Fixture | Policy | Final debt | Final discomfort | Delivered discovery messages | Moves | Assisted moves |
|---|---|---:|---:|---:|---:|---:|
| Static | Cancellation | 422 | 308 | 1,513 | 22 | 0 |
| Static | Comfort | 414 | 276 | 2,287 | 39 | 23 |
| Arriving transfers | Cancellation | 465 | 337 | 39,661 | 35 | 0 |
| Arriving transfers | Comfort | 449 | 299 | 38,060 | 76 | 55 |

Comfort reduced aggregate discomfort by **10.4% static** and **11.3% temporal**
relative to cancellation. These small synthetic examples are initial evidence,
not a general ranking or Sarafu result. Static discovery cost increased by
51.2%; temporal discovery cost fell by 4.0%. No transfer was rejected by either
policy. Debt and discomfort are reported separately and no denominator uses a
static MCF result.

## Locality and limitations

An actor stores only its direct links, local preferences and an opaque probe's
predecessor/successor and remaining local candidates. Messages carry the opaque
probe token and kind; sender/recipient are direct peers. No route list, remote
identity or hop count is sent. Excluding the incoming edge prevents a two-node
return in this simple graph; a returning token closes at its initiating node.
Visited local token state rejects other revisits. This is an honest-node search
property, not adversarial anonymous proof of minimum membership. Timing,
repeated tokens, collusion and transport metadata can leak information.

The simulator schedules roots round-robin and atomically installs the accepted
local successor changes, then records a full offline audit receipt. Actors never
receive that receipt. The adapter supplies serialization and is not a deployed
membership-enumerating coordinator. Messages count only delivered search and
rejection messages, excluding settlement, ACKs, bytes and retries. There are no
losses, sleeping nodes, concurrent proposals, crashes or replicated recovery.
Assisted routing over zero balances is an explicit alternative to the older
zero-closes-channel policy. Keep it separate from existing hashlock safety claims.

Run from the repository root:

```sh
python3 experiments/comfort_simulation.py
python3 -m unittest discover -s experiments -p test_comfort_simulation.py -v
```

[Saved results](results/comfort-simulation.json) include full configuration,
algorithm/model source hashes and per-run receipt hashes. Ten tests cover
mirrored ranges, empty intersections, permissions, hard bounds, two-node
rejection, receiver-side approval, external transfers, independent receipt
replay and conservation. Next experiments should add asymmetric zones excluding
zero, partial opt-in, tighter capacities, new contacts, revisions and actual
concurrent hashlock execution before drawing deployment conclusions.
