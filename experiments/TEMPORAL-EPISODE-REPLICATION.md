# Full-prefix strict-episode seed replication

This prospective follow-up repeats the completed seed-0 random DFS/Numbat
comparison on fixed seeds **1 and 2**, without retuning a policy or parameter.
It reuses the frozen fast case driver, which already accepts `--seed`, and runs
12 separately checkpointed cases: two methods, two seeds, and clean/no-sleep,
10% data-and-ACK loss/random-sleep, and 30% loss/random-sleep conditions.

All cases replay the same 30,726 chronological STANDARD Sarafu transfers over
2,000 arrival ticks, use horizon 2,300, and retain the 10-million-event cap for
each of the run and drain phases. Search/admission/transport behavior is
unchanged. Matching seeds share arrivals and sleep schedules; packet-loss draws
depend on activity. Fault conditions also include sleep, so the clean/fault
contrast does not isolate loss alone.

Before launch, six small seed-0 cases (both methods × three fault conditions)
matched the original adapter for every saved field except wall time, including
nontrivial cycles, exact ledger audits and all exposure metrics. This complements
the prior full seed-0 clean equality and trace/RNG tests. Evidence:
[replication gate](results/temporal-episode-replication-gate.json).

The prospective manifest is [research_campaign_episode_replication.json](research_campaign_episode_replication.json).
The new parallel wrapper runs at most three existing campaign workers; each case
has a 1,200-second wall cap and the campaign has a 7,200-second cap. Each worker
uses the existing source/input/output hash checks and independent state/log
files. Failed or incomplete cases remain visible. Interrupt cleanup is tested
for both an active child ignoring SIGTERM and a child launched after the initial
stop request. No worker is an assistant wake-up service.

```sh
python3 experiments/research_campaign_parallel.py \
  experiments/research_campaign_episode_replication.json \
  --state experiments/results/research-campaign-episode-replication-state.json \
  --max-workers 3 --max-seconds 7200
```

To resume, first inspect the state and live processes, then append `--resume`
to that command. A live coordinator holds an exclusive state lock. Completed
jobs are reused only when their source/input/output hashes still match. A failed
job's old output is backed up before rerunning that job; individual partial
cases are not silently promoted or spliced together.

## Results

All 12 cases completed and passed source/input/output certification and independent
ledger audits. The coordinator ran from 2026-10-11 09:33:36 to 09:47:39 UTC.
All 30,726 transfers posted by the horizon in every case; all messages,
reservations and transfers drained. All cases had some partially committed cycle
work at the horizon, so final drain results do not imply atomic settlement.
The largest total event count was 7,385,667; no case reached a budget limit.

Final debt reduction relative to the same no-clearing final ledger:

| Seed | Condition | Random local DFS | Numbat |
|---|---|---:|---:|
| 1 | Clean | 15.18653% | 13.20969% |
| 1 | 10% loss + sleep | 14.22635% | 12.12354% |
| 1 | 30% loss + sleep | 11.46285% | 10.48629% |
| 2 | Clean | 14.96794% | 12.77166% |
| 2 | 10% loss + sleep | 13.91508% | 12.35067% |
| 2 | 30% loss + sleep | 11.90184% | 11.11919% |

Random clears more in all six new pairs, and in all nine pairs including the
[prior seed-0 comparison](TEMPORAL-EPISODES-RESULTS.md). It remains the stronger
final-debt baseline for this temporal Sarafu exercise. This does not overturn
Numbat's small synthetic advantage or establish a universal best algorithm.

Costs differ. The table below sums each metric over seeds 1 and 2 within a
condition, then reports Numbat's percentage change relative to random; negative
means less. Posted-debt area, U and K run to the common horizon; wire attempts
include drain. U measures requested money awaiting posting; K measures committed
edge amounts awaiting the rest of their cycle, not financial loss or risk.

| Condition | Final debt | Posted-debt area | U | K | Wire attempts |
|---|---:|---:|---:|---:|---:|
| Clean | +2.457% | +0.534% | -28.995% | -4.911% | -1.157% |
| 10% loss + sleep | +2.134% | +0.395% | +19.554% | -2.012% | -2.422% |
| 30% loss + sleep | +0.996% | +0.324% | +61.374% | +4.935% | -10.868% |

Numbat uses fewer wire attempts here, but clears less debt. Its posting and staged
commit exposures vary with the fault condition. These are separate tradeoffs;
there is no combined score. Concurrent wall timings are not a speed comparison.
The same real fixture with extra seeds tests stochastic robustness, not external
validity across independent datasets. Strict admission checks both channel
episodes and balance revisions; the result is not an isolated zero-closure test.

Evidence: [certified summary](results/temporal-episode-replication-summary.json),
[coordinator state](results/research-campaign-episode-replication-state.json).
The summary retains every raw case's source and artifact hashes and requires a
completed coordinator job, completed child certification, matching output digest,
valid audit and empty final pending work before scoring a pair. Regenerate with:

```sh
python3 experiments/temporal_episode_replication_summary.py
```
