# Episode-only cancellation admission: useful clearing tradeoff, failed gate

Allowing cancellation searches to survive balance changes within the **same live
channel episode** reduced aggregate final debt by 6.14% for random DFS and 4.22%
for Numbat on the preregistered synthetic training matrix. It also increased
amount-weighted posting delays. Neither method passed the full gate, so this
experiment does not replace the strict baseline and did not advance to held-out
or Sarafu evaluation.

All **96 runs** completed and passed independent ledger audits, with source
hashes verified. Eight unit/adversarial tests pass. Independent review additionally
ran 15 randomized algorithm/loss/sleep cases behind a restricted simulator facade.
The tests check current-capacity reservation after same-episode balance changes,
rejection after zero/reversal/reopening, and absence of authority for unknown
commit control messages.

| Aggregate metric, 24 paired cases per algorithm | Random episode-only versus strict | Numbat episode-only versus strict |
| --- | ---: | ---: |
| Final debt | −6.14% | −4.22% |
| Physical data + ACK attempts | +4.35% | −0.73% |
| Amount-weighted external posting delay through drain | +7.07% | +3.81% |
| Committed-edge amount-time awaiting cycle completion | +18.11% | −7.49% |
| Cases with higher final debt | 6 / 24 | 10 / 24 |
| Gate passed | No | No |

Random fails the traffic, posting and staged-exposure gates. Numbat fails the
traffic, posting and individual-case gates. All pending transfers and settlements
drained; the output retains the common-horizon pending counts and exposures.

Stale episode/revision rejections fell from 868 to 271 for random and 959 to 285
for Numbat. These counters include both search and prepare rejection and should
not be interpreted as preparation abort rates. Completed cycles rose from 586 to
670 and 507 to 605 respectively. The remaining episode rejections still protect
closed/reopened/reversed relationships. The lower rejection count confirms that
strict revision equality has a measurable clearing cost on these workloads;
more admitted work also has communication and delay costs.

This changes only cancellation admission. It does not reopen zero relationships,
restore cleared balances, extend credit or alter Headroom consent limits. Current
local balances and reservations still constrain every prepared amount. Stale
Numbat capacity observations may lower a proposed amount; they cannot override
current capacity. Both variants retain the same staged, non-atomic commit and
state-retaining sleep assumptions.

Artifacts:

- [Preregistration](TEMPORAL-EPISODE-ONLY-PLAN.md), unchanged after training and
  included in saved source hashes.
- `results/temporal-episode-only-training.json`: all 96 paired runs, independent
  audits, exposure metrics, complete markers and gate calculations.
- `temporal_episode_only.py`: separate actor and simulator adapter, no frozen
  baseline changes.
- `test_temporal_episode_only.py` and
  `test_temporal_episode_only_adversarial.py`: direct and independent tests.

Reproduce with a fresh output path:

```sh
python experiments/temporal_episode_only_benchmark.py \
  --output /tmp/temporal-episode-only-training-reproduction.json
python -m unittest discover -s experiments -p 'test_temporal_episode_only*.py' -q
```

This is evidence of a tradeoff, not a universal algorithm win. Any future
multi-objective preference for lower debt at higher delay must be specified
explicitly rather than retroactively changing this experiment's gate.
