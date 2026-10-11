# Concurrent decrease-first Headroom: training gain did not hold up

The fixed decrease-first ordering passed its preregistered training gate, then
**failed unchanged on held-out seeds**. It should not replace the restoration-
disabled baseline. All 72 runs completed and passed the independent signed ledger
audit; source hashes match. All external transfers posted by the observation
horizon in every run.

| Aggregate metric versus restoration-disabled control | Training seeds 201/202 | Held-out seeds 203/204 |
| --- | ---: | ---: |
| Final debt | −5.58% | +1.92% |
| Physical data + ACK attempts | +9.70% | +26.88% |
| Amount-weighted external posting delay through drain | +2.22% | −1.56% |
| Partial-settlement exposure area through horizon | +15.76% | +19.85% |
| Configurations with lower final debt | 8 / 12 | 7 / 12 |
| Gate passed | Yes | No |

The gate required no higher aggregate debt, at most 10% more traffic, and no extra
unposted inputs. Training narrowly satisfied the traffic limit; held-out results
fail both debt and traffic. Majority per-case wins do not override the aggregate
regression. Posting and settlement exposures were reported tradeoffs, not newly
introduced gate conditions.

Three methods ran under identical arrival and sleep fixtures and fixed event
budgets:

| Aggregate final debt, scaled integer units | Training | Held-out |
| --- | ---: | ---: |
| Restoration disabled | 6,394,000 | 8,056,000 |
| Original concurrent restoration | 6,946,000 | 8,443,000 |
| Decrease-first restoration | 6,037,000 | 8,211,000 |

Decrease-first improves over original concurrent restoration in aggregate on both
splits, but the held-out control still does better. It completed 54 mixed cycles
in training and 64 held-out. The mechanism works; this ordering does not make its
extra search work consistently pay off.

The variant changes only local search order: decreases first, then descending
local residual capacity, with the original seeded shuffle breaking exact ties.
The concurrent original shuffles uniformly, so this is a **joint directional and
capacity ordering change**, not a clean estimate of directional priority alone.
Independent AST review confirmed that removing the single added sort recovers
the original search method exactly. Current-capacity checks, strict episode and
revision admission, two-incident-pair locks, staged commit, and loss transport
are inherited unchanged.

Signed partial-settlement exposure is the sum over transactions of half the L1
net-position imbalance, integrated through horizon 800. It differs from the older
positive-only committed-edge exposure; compare it only within this matched
experiment. Posting exposure is requested amount times actual posting delay.
Final debt is measured after drain; it is not a same-horizon clearing score.

Artifacts:

- [Preregistration](CONCURRENT-DECREASE-FIRST-PLAN.md), unchanged after training.
- `concurrent_decrease_first.py` and `test_concurrent_decrease_first.py`.
- `concurrent_decrease_first_benchmark.py` with conditional held-out gate.
- `results/concurrent-decrease-first-training.json` and
  `results/concurrent-decrease-first-heldout.json`: all rows, source hashes,
  pending input measurements and signed audits.

Reproduction uses fresh output paths:

```sh
python experiments/concurrent_decrease_first_benchmark.py \
  --output /tmp/concurrent-decrease-training.json
python experiments/concurrent_decrease_first_benchmark.py \
  --heldout-after /tmp/concurrent-decrease-training.json \
  --output /tmp/concurrent-decrease-heldout.json
```

No parameters changed between splits. No additional search-order sweep or Sarafu
run followed this failure. The next hypothesis should explain the held-out
traffic growth and variation rather than treating the favorable training result
as a new best algorithm.
