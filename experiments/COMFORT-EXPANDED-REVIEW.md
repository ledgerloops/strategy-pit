# Independent review of expanded comfort simulation

Reviewed the expanded simulator, inherited actor implementation, tests, saved
160-run artifact, and the expanded section of `COMFORT-SIMULATION.md`.

**Outcome:** no blocking defect found in the reported serialized experiment.
The focused suite passed all 16 tests. Independently rerunning `run()` and
normalizing through JSON produced exactly the saved result, including every
event, counter and fixture hash. All three recorded source hashes matched at
review time. This review applies to the source versions pinned in
[`comfort-simulation-expanded.json`](results/comfort-simulation-expanded.json).

## Checks

- Both policies receive identical initial fixtures and offered event streams,
  with the same per-service message allowance. Unused service allowance is
  discarded. Temporal acceptance can differ: the report correctly avoids
  treating final scores as matched-net-position comparisons.
- Missing and incompatible comfort ranges block comfort assistance; known
  hard grants still constrain external transfers. Undefined-range counts are
  retained, and an all-undefined score is not presented as satisfied preferences.
- Settlement audit replay independently checks stored balances, hard bounds,
  permissions, signed-net conservation, and policy-specific improvement. The
  offered-transfer accounting preserves rejected counts and values. The
  posted-stream reference is explicitly an accounting reference, not a feasible
  competing execution or an optimality bound.
- Actor decisions inspect direct-neighbour balances/preferences and local
  opaque-token state. Actors neither read a global graph nor receive the
  simulator's full settlement receipts. Global scheduling, atomic installation
  and offline scoring remain simulator responsibilities, as documented.
- Negative evidence agrees with saved results: comfort has worse aggregate
  static discomfort in all four families with defined zones. Cancellation can
  worsen individual preferences; its recorded worsening-update totals are
  48, 48, 23 and 29 for asymmetric, partial, tight and missing families.

## Limits of this review

These are fixed-preference, serialized, reliable unit-move experiments.
They do not test hashlock execution, concurrent reservations, sleeping nodes,
message loss, expiry, or recovery. Numeric opaque probe IDs and transport
metadata provide no anonymity guarantee. The inherited scheduler and atomic
adapter are not a deployed decentralized settlement protocol.

The audit validates recorded changes and arithmetic, not Byzantine evidence or
cryptographic participant uniqueness. Minimum-three membership is an honest
simple-graph property, not proof against colluding identities. No result here
establishes that comfort clearing beats other algorithms generally.

Reproduction command:

```sh
python3 -m unittest discover -s experiments -p 'test_comfort_simulation*.py' -v
python3 experiments/comfort_simulation_expanded.py --output /tmp/comfort-expanded-review.json
cmp experiments/results/comfort-simulation-expanded.json /tmp/comfort-expanded-review.json
```
