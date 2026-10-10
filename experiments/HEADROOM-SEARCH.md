# Decrease-first Headroom search

Decrease-first ordering improves the cold-start Headroom prototype on the tested Sarafu 50k fixture: **12.20–12.35% cleared**, versus **9.88–9.89%** with its original ordering. This is an improvement to the bounded search heuristic, not evidence of optimality or a concurrent distributed settlement protocol.

## One local change

Original Headroom orders eligible residual arcs by capacity, then prefers a decrease when capacities tie. That can send searches along large restoration opportunities before smaller existing debts. The new `DecreaseFirstNode` orders by **decrease before restoration, then capacity**, retaining randomized exact ties. Search and settlement otherwise remain unchanged; the base `headroom.py` is frozen. Restorations remain eligible when decreasing alternatives have been explored.

Every choice uses the current node’s own balances or neighbour advertisements and the received token. Original caps, per-node signed net positions, and strictly positive total-debt reduction per accepted cycle remain mandatory. Participants may increase gross exposure within their original caps.

## Fixed comparison

All three methods use two rounds, search budget 64, maximum path length 64, the same input and seed, and one serialized search initiation per node per round. These are equal search-admission and hop limits, **not equal message counts or CPU budgets**. Message totals include initial neighbour advertisements and settlement traffic. The reduction-only ablation uses the original search with restoration capacity disabled.

The ordering was fixed before running training seeds 101/102. The sequence was two regression fixtures, sixteen static synthetic cases, then Sarafu seeds 0/1; no parameters were tuned between these phases. These are static graphs, not a streaming benchmark.

The Sarafu fixture had been examined in earlier research and helped motivate this hypothesis. Its new runs are a transfer evaluation, not a previously unseen holdout.

## Sarafu 50k

| Seed | Original capacity-first | Decrease-first | Reduction-only | Decrease-first messages |
| --- | ---: | ---: | ---: | ---: |
| 0 | 9.88262% | 12.35095% | 10.60890% | 705,318 |
| 1 | 9.88633% | 12.19991% | 10.34031% | 707,805 |

The independently computed bounded MCF reference is **18.92119%**. Decrease-first improves over original Headroom by 2.31–2.47 percentage points and over reduction-only by 1.74–1.86 points. Original Headroom used 717,288–717,303 messages; reduction-only used 684,367–684,962. Both rerun controls match the canonical `headroom.json` scores and every recorded message/search metric exactly.

This result does not establish a win over Numbat, Jerboa, or Jaribu. Their existing runs have different resource budgets and, for historical Jerboa/Jaribu, different coordination assumptions. The published Numbat pipeline result does not contain a reusable residual ledger, so this experiment skips Numbat postpasses rather than rerunning that costly initialization.

## All synthetic training results

Percent of original debt cleared:

| Graph | Seed | Capacity-first | Decrease-first | Reduction-only |
| --- | ---: | ---: | ---: | ---: |
| sparse-24 | 101 | 25.867% | 27.283% | 23.891% |
| sparse-24 | 102 | 35.565% | 35.565% | 31.796% |
| dense-24 | 101 | 49.725% | 62.459% | 60.090% |
| dense-24 | 102 | 48.048% | 53.208% | 51.848% |
| community-24 | 101 | 42.879% | 43.455% | 44.233% |
| community-24 | 102 | 38.190% | 39.884% | 28.558% |
| disconnected-24 | 101 | 37.583% | 38.421% | 35.487% |
| disconnected-24 | 102 | 35.865% | 35.865% | 27.094% |
| sparse-72 | 101 | 37.546% | 44.146% | 32.832% |
| sparse-72 | 102 | 42.653% | 49.609% | 40.889% |
| dense-72 | 101 | 34.328% | 56.116% | 59.432% |
| dense-72 | 102 | 32.839% | 53.641% | 55.541% |
| community-72 | 101 | 45.310% | 55.827% | 51.203% |
| community-72 | 102 | 39.117% | 41.326% | 39.087% |
| disconnected-72 | 101 | 45.186% | 52.519% | 43.391% |
| disconnected-72 | 102 | 46.539% | 58.168% | 50.497% |

Against capacity-first, decrease-first wins 14 cases and ties 2; its unweighted mean improvement is 6.89 percentage points. Against reduction-only it wins 13 and loses 3, with mean improvement 4.48 points. In particular, reduction-only still wins both dense 72-node cases and one community 24-node case. Restoration is useful, but this ordering is not universally best.

## Correctness and limitations

Both residual recovery fixtures reach their independently established optima: Alice’s example clears 72% versus the greedy 60%, and the shared-edge trap clears 66.67% versus 50%. Every experimental settlement passes independent signed-cycle replay: original caps hold, signed net positions are unchanged, actual debt reduction is strictly positive, and the final ledger matches the simulator.

Tests also execute the variant through a transport facade denying nodes access to the global graph and result snapshots. The simple-cycle result and message counts match the original algorithm. Four focused tests pass.

Independent review confirmed that the two search-method syntax trees differ only in the sort-key swap, verified all source/input/baseline hashes, and reproduced the reported win/tie/loss counts.

Serialization remains an explicit global scheduler assumption. Messages are reliable and participants honest; crashes and concurrent Headroom transactions are not supported. A bounded search may miss improving cycles, and repeated searches are not a certificate of optimality. The older prototype files and their benchmark artifacts were not changed.

## Reproduce

```sh
PYTHONPATH=.:experiments python experiments/headroom_search.py /path/to/animal-50k-debt.csv
PYTHONPATH=.:experiments python -m unittest experiments.test_headroom_search
```

Use the existing benchmark Python environment with OR-Tools installed. [Machine-readable results](results/headroom-search.json) include all controls, source and input hashes, MCF reference scores, independent audits, timing, and protocol metrics. The canonical baseline artifact is linked by its content hash.
