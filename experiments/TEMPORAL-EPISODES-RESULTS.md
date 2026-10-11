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
1.94–4.55%. Its larger staged-commit exposure is a material tradeoff, rather
than evidence that it dominates random DFS. At the common horizon every
synthetic input has posted, but unfinished-cycle committed amounts sum to
217,000 scaled units for random DFS versus 504,000 for Numbat; these all
finish during drain. Stale episode/revision rejections
occurred 2,521 times for random DFS and 2,634 times for Numbat.

Artifact: [temporal-episode-synthetic.json](results/temporal-episode-synthetic.json).

Sarafu 5,000-transfer matrix remains in progress; no real-fixture winner claimed.
