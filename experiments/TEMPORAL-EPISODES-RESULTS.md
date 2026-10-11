# Strict communication episodes: matched fault comparison

This experiment compares unchanged random DFS and Numbat search policies on the
same strict communication episode substrate. A new search cannot use an ended
relationship. A quote also becomes stale after a balance revision within a live
episode; this admission rule is stricter than zero closure alone. An external
transfer may open a fresh episode. Control messages
for already admitted work retain a narrowly scoped grace path. This remains a
simulator with atomic bilateral posting and staged, non-atomic cycle commits.

The prospective matrix crosses loss probabilities 0%, 10%, and 30% independently
with no sleep / the existing seeded random sleep schedule. Both data and ACKs
have the stated drop probability. Input arrivals and sleep schedules match by
seed; algorithms send different packets, so this is not identical packet loss
traces. Algorithms use the same search/retry parameters and per-phase event
budget (2 million events before the common horizon and 2 million in draining).

Synthetic inputs cover sparse, community and burst graphs, 12 and 24 nodes,
seeds 0 and 1, with continuous transfers over 500 ticks and horizon 800. The
Sarafu matrix uses the first 5,000 chronological STANDARD transfers, uniformly
compresses their timestamp gaps to 1,000 ticks, and observes horizon 1,300.
There are 144 synthetic cases and 24 Sarafu cases. These previously used seeds
provide a regression comparison; they are not fresh held-out model selection.

Every completed run independently replays each edge commit and external posting,
checks directed capacities and final net positions, and verifies full arrival
application. Budget exhaustion is retained as an explicitly incomplete row.
Source hashes, fixture hashes, actual parameters and completion markers are in
the JSON artifacts. Outputs resume only when source/configuration hashes match.

Final debt is measured after draining all outstanding work. Posted-debt area is
measured only to the common horizon and excludes unposted input. Therefore we
also report U(H), the integral of requested but unposted transfer amounts, and
K(H), individually committed edge amounts waiting for the rest of their cycle.
K is bookkeeping exposure, not a claimed financial risk estimate. Neither
metric is combined into a fabricated overall score.

## Results

The synthetic matrix completed **144/144 runs**, with every ledger audit
passing and no unfinished transfers or settlements after drain. Across the 72
matched pairs, Numbat has lower final debt in 44, ties in 4, and higher debt in 24.
The following are ratios of summed quantities, not average per-case percentages.

| Synthetic measure | Random DFS | Numbat | Numbat change |
| --- | ---: | ---: | ---: |
| Final debt, scaled units | 80,027,000 | 77,392,000 | −3.29% |
| Posted-debt area, scaled amount-ticks | 54,732,911,000 | 53,497,749,000 | −2.26% |
| Unposted-request U(H), scaled amount-ticks | 870,458,000 | 865,770,000 | −0.54% |
| Staged-commit K(H), scaled amount-ticks | 301,616,000 | 356,600,000 | +18.23% |
| Wire attempts, data plus ACK | 227,371 | 226,080 | −0.57% |

Numbat lowers aggregate final debt in each of the six loss/sleep strata, by
1.94–4.56%. Its larger staged-commit exposure is a material tradeoff, rather
than evidence that it dominates random DFS. At the common horizon every
synthetic input has posted, but unfinished-cycle committed amounts sum to
217,000 scaled units for random DFS versus 504,000 for Numbat; these all
finish during drain. Stale episode/revision rejections
occurred 2,521 times for random DFS and 2,634 times for Numbat.

Artifact: [temporal-episode-synthetic.json](results/temporal-episode-synthetic.json).

For context, matching the same arrival hashes and concurrent-transport cases
in [the earlier permissive-channel matrix](results/temporal-synthetic.json),
strict admission raises aggregate final debt by 4.29% for random DFS and 2.56%
for Numbat. Wire attempts fall from 237,084 to 227,371 for random DFS and from
232,849 to 226,080 for Numbat. This comparison changes both episode closure and
within-episode revision admission, and consequent packet timing/random draws;
it does not isolate a single cause or justify reverting the user's channel rule.

The Sarafu 5,000-transfer matrix completed **24/24 runs**, all audited and fully
drained. The input file and frozen source hashes were rechecked at completion.
Random DFS wins 9 of 12 final-debt pairs; Numbat wins 3. Aggregate final debt
improvement against no clearing is **0.76351% for random DFS versus 0.73526%
for Numbat**. These small-prefix outcomes do not establish a full-prefix winner.

| Prefix measure | Random DFS | Numbat | Numbat change |
| --- | ---: | ---: | ---: |
| Final debt, scaled units | 13,920,812,000 | 13,924,774,000 | +0.02846% |
| Posted-debt area, scaled amount-ticks | 10,231,631,692,000 | 10,229,473,993,000 | −0.02109% |
| Unposted-request U(H), scaled amount-ticks | 34,748,645,000 | 35,377,790,000 | +1.81056% |
| Staged-commit K(H), scaled amount-ticks | 1,328,095,000 | 1,145,074,000 | −13.78072% |
| Wire attempts, data plus ACK | 4,627,837 | 4,664,856 | +0.79992% |

All requested transfers have posted by the common horizon in every case.
Unfinished-cycle committed amounts at that horizon sum to 60,000 scaled units
for random DFS and 170,000 for Numbat; all finish during drain. Thus neither
method dominates across final debt, time-integrated exposure and endpoint
exposure. Every run remains below 950,000 total events.

Artifact: [temporal-episode-sarafu5000.json](results/temporal-episode-sarafu5000.json).

| Seed | Loss | Sleep | Random final improvement | Numbat final improvement |
| --- | --- | --- | ---: | ---: |
| 0 | 0% | No | 0.8190% | 0.7271% |
| 0 | 0% | Yes | 0.7682% | 0.7467% |
| 0 | 10% | No | 0.7547% | 0.7858% |
| 0 | 10% | Yes | 0.7432% | 0.7116% |
| 0 | 30% | No | 0.7417% | 0.7167% |
| 0 | 30% | Yes | 0.7252% | 0.7037% |
| 1 | 0% | No | 0.7648% | 0.7840% |
| 1 | 0% | Yes | 0.7483% | 0.7417% |
| 1 | 10% | No | 0.8631% | 0.7501% |
| 1 | 10% | Yes | 0.8196% | 0.7219% |
| 1 | 30% | No | 0.7068% | 0.7284% |
| 1 | 30% | Yes | 0.7076% | 0.7053% |

This prefix offers little aggregate reduction: no-clearing final debt is
1,168,993 units, and the offline gross-arrival MCF relaxation gives a minimum
of 1,154,841, an optimistic maximum improvement of **1.21061%**. Its static
final-net MCF reference is **0.85715%**. The relaxation ignores chronology and
channel restrictions; it is not an attainable node-local optimum. Both verified
primal ledgers and solver/source/input versions are saved in
[the prefix reference](results/temporal-episode-sarafu5000-reference.json).
The calculation uses `min_residual(gross_graph(fixture.events[:5000]))` and
`min_residual(net_graph(fixture.events[:5000]))` from the frozen existing modules.

## Full-prefix follow-up

The prospective six-case follow-up uses all 30,726 STANDARD transfers, 2,000
arrival ticks, seed 0, and both methods under clean/no-sleep, 10% loss/sleep, and
30% loss/sleep. Each phase has a 10-million-event cap. The campaign manifest
limits the whole six-case job to one hour. It launched after all twelve seed-0 prefix cases completed successfully,
covering every loss/sleep combination, while seed-1 replication continued. This is a diagnostic seed, not broad statistical
validation. Its clean controls also use strict admission, unlike earlier full
Sarafu baselines.

```sh
python3 experiments/research_campaign.py experiments/research_campaign_episodes.json \
  --state experiments/results/research-campaign-episodes-state.json --max-seconds 3600
```

`temporal_episode_scale.py` checkpoints individual cases and can resume a
matching output when invoked directly. The campaign runner resumes completed
jobs by hash, but backs up a failed job's output before rerunning that job; it
does not automatically resume individual cases within a failed job. Check the
saved job status and live processes before any restart.

## Fast transport validation

A separately source-pinned fast adapter removes redundant simulator copies and
caches private envelope representation sizes. It changes no search policy. The
full random/clean case passed exact equality against the original for every
saved field except wall time, including all horizon metrics, ledger audit and
exposure. Fixture, selection and shared base source pins also match. Evidence:
[full clean equivalence](results/temporal-episode-gold-equivalence.json).
This complements the smaller full-trace/RNG/state equivalence tests; the original
full rows did not retain complete event traces or RNG states.

After both original clean controls finished, the original campaign was
intentionally stopped and its remaining fault cases replaced with separately
bounded fast cases. The original result remains `complete: false` with 2 of 6
rows and an explicit supersession reason, not a claimed budget failure. Its
runner state preserves the interruption evidence and marks `superseded`. During
validation, at most three fast workers ran beside the original worker. Each
fast case has a 1,200-second subprocess timeout and a unique output.
The four fault cases are 10%/30% loss with sleep for both methods; seed 0 and
2,000 arrival ticks match the original planned campaign. Concurrent wall times
are not suitable for throughput comparisons. All five fast case jobs completed
successfully, including the extra clean equivalence case. The joined report
requires all six intended cases and identical fast adapter/driver source pins
to the validated gold case.

## Full timestamped Sarafu results

The completed [six-case comparison](results/temporal-episode-full-comparison.json)
contains two original clean controls and four validated fast fault cases, with
explicit per-row source and result hashes. All six pass independent ledger
audits and finish every transfer and settlement during drain. Every requested
transfer has already posted by the common horizon. The largest run uses
7,415,769 total events, below the 10-million-event per-phase cap.

| Conditions, seed 0 | Random DFS final debt improvement | Numbat final debt improvement |
| --- | ---: | ---: |
| No loss, no sleep | 14.76991% | 13.13047% |
| 10% data/ACK loss, random sleep | 13.78407% | 12.75147% |
| 30% data/ACK loss, random sleep | 11.42300% | 10.97882% |

Random DFS has lower final debt in all three full-prefix conditions. This
supports keeping it as the full-Sarafu cancellation baseline. Numbat remains
stronger on aggregate small synthetic final debt, and can use fewer messages
under loss. These are one-seed full-prefix diagnostics, not a universal ranking.
The fault rows also introduce sleep; their difference from the clean row does
not isolate packet loss alone.

| Conditions | Numbat posted-debt area change | Wire attempts change | U(H) change | K(H) change |
| --- | ---: | ---: | ---: | ---: |
| Clean | +0.517% | +0.015% | −30.164% | −6.722% |
| 10% loss and sleep | +0.012% | −2.438% | +14.011% | −13.339% |
| 30% loss and sleep | −0.744% | −9.577% | −0.653% | +20.361% |

Each change compares Numbat with random DFS in the same condition. Lower is
better for these individual measures, but they are not a combined score. In
particular, Numbat's lower traffic at 30% loss accompanies higher staged-commit
exposure. At the common horizon some cycles remain partly committed despite
all external input having posted; draining to eventual completion does not
make settlement atomic. Raw endpoint exposures are retained in every row.

Rebuild the gold certificate and completed join without rerunning simulations:

```sh
python3 experiments/temporal_episode_gold.py \
  --legacy experiments/results/temporal-episode-full.json \
  --fast experiments/results/temporal-episode-fast-gold.json \
  --output experiments/results/temporal-episode-gold-equivalence.json
python3 experiments/temporal_episode_full_summary.py
```

For prefix runs or resuming their checkpoints, use the input-guarded wrapper:

```sh
python3 experiments/temporal_episode_benchmark_v2.py --suite sarafu \
  --csv ../jerboa-review/__tests__/fixtures/sarafu-50k.csv --limit 5000 \
  --arrival-ticks 1000 --event-budget 2000000 \
  --output experiments/results/temporal-episode-sarafu5000.json
```

It rejects a CSV changed at the same path before delegating to the frozen
original harness's source/configuration checks. The published prefix ran once
without resume and its fixture hash was independently rechecked at completion;
the original harness's weaker input-resume check did not affect those results.
The full-case drivers already verify fixture hashes before reusing outputs.
