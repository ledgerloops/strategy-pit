# Rank-weighted Numbat: failed training gate

Rank-weighted exploration reduced traffic and exposure relative to Numbat, but
left **0.73% more aggregate final debt** and two additional transfers unposted at
the common horizon. It failed the preregistered gate; no held-out or Sarafu run
followed. All **72 training runs** completed and passed independent ledger audits,
and saved source hashes match.

| Metric across 24 matched cases per method | Rank versus Numbat | Rank versus random DFS |
| --- | ---: | ---: |
| Final debt after drain | +0.73% | −4.80% |
| Physical data + ACK attempts | −3.94% | −2.72% |
| Amount-weighted posting delay through drain | −2.85% | +4.34% |
| Partial-commit exposure through drain | −5.55% | +33.06% |
| Cases with lower final debt | 10 / 24 (one tie) | 17 / 24 |

Numbat was the control with lower aggregate final debt: 76,006,000 scaled units,
versus rank 76,558,000 and random 80,420,000. Rank had two horizon-unposted transfers
totaling 21,000 scaled units, compared with none for either control. These later
posted during drain; no inputs were dropped. The gate required strictly lower
debt than both controls and no additional unposted input, so traffic savings do
not qualify this policy for promotion.

The fixed hypothesis replaces amount-to-the-fourth-power weights with dense
ascending ranks of current local available balances. Equal balances have equal
ranks: 1, 1, 100 maps to weights 1, 1, 2. It makes very large balances less dominant
without removing the preference for larger local capacity. Three focused tests
pass, and independent review verified equal-weight ties, exclusion of unavailable
neighbors under reservations, preservation of physical capacity hints, and
restricted actor access to simulator state. Strict episode/revision admission
and settlement remain unchanged.

This was one specified rank policy, not a rank-definition or exponent sweep.
Synthetic results neither establish nor rule out a Sarafu advantage; the failed
training gate means the prescribed experiment stops here. Numbat remains the
stronger aggregate debt control for this synthetic matrix, while earlier full
Sarafu results favored random DFS under their stated conditions.

Artifacts:

- [Preregistration](TEMPORAL-RANK-PLAN.md), frozen before the run.
- `temporal_rank.py`, `test_temporal_rank.py`, `temporal_rank_benchmark.py`.
- `results/temporal-rank-training.json`: all rows, source/input hashes, pending
  work, independent audits, exposures and explicit gate calculation.

Reproduce with a fresh output path:

```sh
nice -n 10 python experiments/temporal_rank_benchmark.py \
  --output /tmp/temporal-rank-training-reproduction.json
python -m unittest discover -s experiments -p test_temporal_rank.py -q
```
