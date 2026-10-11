# Reservation-triggered backoff: failed training gate

The fixed local policy in [the preregistration](TEMPORAL-CONTENTION.md) completed
all **96** strict-episode training runs with independent ledger audits. Neither
random DFS nor Numbat passed the gate. No held-out or Sarafu run was launched,
and no parameter sweep followed.

| Metric, aggregate across 24 matched cases per method | Random DFS + backoff | Numbat + backoff |
| --- | ---: | ---: |
| Final debt versus control | −1.27% | −1.88% |
| Physical data + ACK attempts | −2.78% | −4.11% |
| Amount-weighted external posting delay through drain | +3.44% | +13.79% |
| Committed-edge amount-time awaiting cycle completion | −5.70% | −12.10% |
| Individual cases with higher final debt | 7 / 24 | 6 / 24 |
| Gate passed | No | No |

Lower aggregate debt is encouraging but insufficient: both miss the required 5%
traffic saving and increase posting exposure. Random also exceeds the allowed
six worsened cases. Delay exposure must remain visible even when the clearing
score improves. All external transfers and settlements drained; no unfinished
work was silently discarded.

Local instrumentation separates preparation rejection reasons. Controls observed
199 reservation conflicts versus 461 stale episode/revision rejections for random,
and 252 versus 499 for Numbat. These are counts of failed prepare receptions;
a successful proposal visits multiple actors, so divide neither count by all
prepare receptions to claim a proposal-success probability. No depleted-only
rejection appeared: strict admission usually identifies the corresponding changed
ledger revision first. This is a property of these traces, not proof that such a
case is impossible.

Implementation detail: a commit lowers the level used for the **next** conflict
but does not cancel an already scheduled pause. Thus the preregistration phrase
“level zero imposes no pause” describes the initial state, not cancellation of an
existing `resume_at` deadline. The source was fixed before all training runs.

The adaptation suppressed 253 random and 257 Numbat wake events. Random's
reservation-conflict count actually rose to 222; Numbat's fell to 233. Suppressing
an actor's own initiations does not prevent remote tokens from competing at that
actor. The measured result supports keeping the ordinary initiation schedule as
the current baseline. A next hypothesis should address stale search information
or duplicate exploration, while preserving local admission and settlement safety.
It should not silently retune these backoff constants.

Artifacts:

- `results/temporal-backoff-training.json`: all rows, source hashes, exposure metrics,
  final completion markers and gate calculation.
- `temporal_backoff.py`: optional local adaptation plus identical instrumentation
  in controls; no global routing observations.
- `test_temporal_backoff.py`: six tests covering local failure classification,
  stale messages, capped pause, restricted simulator access, baseline equivalence
  with adaptation disabled, and accounting under loss.
- `temporal_backoff_benchmark.py`: fixed 96-run matrix and independent gate.

Reproduction (choose a new output path; existing results cannot be overwritten):

```sh
python experiments/temporal_backoff_benchmark.py \
  --output /tmp/temporal-backoff-training-reproduction.json
python -m unittest discover -s experiments -p test_temporal_backoff.py -q
```

The preregistration file is included in the saved source hashes and remains
unchanged after the run. This separate result report records the outcome.
