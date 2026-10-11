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

Launched after independent review at 2026-10-11T09:33:36.324545+00:00, coordinator PID
102617, execution session84912. Inspect
`results/research-campaign-episode-replication-state.json` and each child state
for actual progress. No completed seed-1 or seed-2 result is claimed at launch. Evaluate final debt, posted-debt
area, delayed-input U, staged-commit K, messages and pending work separately.
The same real fixture with extra seeds tests stochastic robustness, not broad
external validity across independent datasets.
