# Headroom Clearing experiments

[Issue 001](../docs/issues/001-headroom-clearing.md) · [Animal strategies](../README.md)

Headroom Clearing permits a debt to be restored after clearing, up to its original amount. Every original edge stays between zero and its epoch ceiling, and completed moves preserve signed net positions. A residual cycle may increase some debts if it decreases total debt overall. This gives greedy clearing a way to revise earlier choices.

The feasible final states are those of the original bounded MCF problem. Headroom can help a local search approach that optimum; it does not raise it. The tested implementation makes routing and consent decisions from local balances and neighbour messages, but **the simulator globally serializes initiators and settlements**. This is not yet a concurrent distributed Headroom protocol.

## Does the idea work?

Yes, on independently checked examples:

- Alice's completed example: after the first clearing, remaining debt falls from **10 to 7**, with her balances moving from `(7,0,0)` to `(4,3,0)`.
- A greedy trap: ordinary clearing leaves an acyclic positive-debt graph with **3** units remaining. A mixed restoration/reduction cycle takes it to **2**.

Both final values match exhaustive enumeration and MCF. The implementation checks peer bounds during preparation. Independent replay verifies every accepted cycle's actual debt reduction, per-node conservation and final ledger. Locality tests deny nodes access to global graph objects.

## Same 50k Sarafu fixture

Input: 13,831 edges, 6,908 accounts, total post-bilateral debt 7,434,585.295. MCF can clear 18.9212%. Two seeds, two Headroom rounds, 64 search steps per initiation; each round initiates one bounded search per node.

| Start and search policy | Final initial debt cleared | Interpretation |
| --- | ---: | --- |
| Original ledger → Headroom | 9.8826–9.8863% | Cold-start search is weak on this input |
| Original ledger → same search without restoration | 10.3403–10.6089% | Restoration hurts this cold-start heuristic |
| Local Numbat → Headroom | **14.1214–14.6822%** | Improves Numbat's 13.5000–13.6880% starting result |
| Local Numbat → same search without restoration | 13.5000–13.6880% | No improvement in either seed |
| Global Jaribu → Headroom | 16.8337–16.8542% | Diagnostic postpass; starts at 16.6145% |
| Historical Jerboa accepted output → Headroom | 16.0812–16.0879% | Diagnostic postpass; starts at 15.3732% |

The Numbat → Headroom pipeline uses approximately **2.30–2.33 million total messages**, including Numbat, Headroom setup advertisements and the postpass. Numbat alone with a larger budget previously reached 13.4923–13.8154% with 5.59–5.65 million messages across three seeds. These are finite runs with different scheduling; the result supports a useful second phase, not general dominance.

Disabling restoration in that same second phase produces no gain, supporting a specific contribution from Headroom rather than merely extra search time. Jaribu and historical Jerboa initializers are not wholly node-local pipelines, and their initialization costs are excluded from postpass-only counts. The Jerboa initializer rejects its five invalid proposals before use.

**Current assessment:** Numbat plus Headroom is our strongest measured local-decision combination on this particular fixture among these new runs. Headroom alone is worse. Numbat remains the tested concurrent search baseline; the Headroom phase still assumes global serialization. None is established as best across changing graphs, loss, sleep, or stricter channel policies.

## Channels and changing graphs

These static experiments retain communication across original relationships even when their current balance is zero. That allows the example's zero-balance Alice–Charlie relationship to be restored.

The newer temporal model closes zero-balance relationships to new economic search. Under that rule, a fully cleared link cannot support a later Headroom move until communication is re-established. Do not transfer these static results to that model without an explicit reopening policy. New transfers also require a policy for changing epoch ceilings. The [temporal research issue](../docs/issues/002-temporal-faults-and-turns.md) tracks these questions.

Other limitations: honest peers, reliable exactly-once delivery, static caps, no crashes, non-atomic in-flight updates, bounds as the default consent rule, and bounded search that does not prove optimality. Individual gross exposure may increase while remaining within agreed bounds.

## Reproduce

Use the OR-Tools Python environment documented in [README.md](README.md). From the repository root:

```sh
python experiments/headroom_benchmark.py --input /tmp/animal-50k-debt.csv
python experiments/headroom_numbat_pipeline.py /tmp/animal-50k-debt.csv
python -m unittest discover -s experiments -p 'test_*.py' -q
```

These write the default result files. Regenerate the temporary input using the instructions in [the animal comparison](ANIMAL-COMPARISON.md#reproduce). The global solver is only an external scoring reference; it does not guide node decisions.

[All Headroom runs](results/headroom.json) · [Numbat pipeline and control](results/headroom-numbat-pipeline.json) · [Implementation](headroom.py)
