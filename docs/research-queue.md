# Research queue and checkpoints

[Strategy Pit](../README.md) · [Issues](issues/README.md)

## Objective

Find practical node-local clearing algorithms that perform well across static and changing credit graphs, with explicit costs and delivery/failure assumptions. Continue useful authorized work while the session is active; checkpoint before interruption. This document is not an external wake-up scheduler.

## Verified status — 2026-10-11

The finite replay campaign completed on 2026-10-10 at 07:34:43 UTC. All three jobs and nine follow-up runs completed; together with the original full-prefix run, all twelve runs pass their ledger audits. No benchmark worker was running when checked on October 11. The historical process identifiers below are not live-status claims.

Random local DFS has the lowest final debt in all four full-prefix clock/seed comparisons: 15.21–15.81% improvement from the no-clearing final debt, versus Numbat 13.75–14.21% and largest-first 12.35–13.09%. These are temporal results, not a comparison with static Jerboa/Jaribu. The fixed 50/50 exploration mixture failed its training gate. The exposure observer and gross-arrival reference are complete locally. All 134 tests pass. Completed artifacts were independently reviewed and published at `d8c7e0b`.

### Chosen next steps

1. Finish independent hash/report review and publish the completed campaign, negative exploration result, exposure measurements and temporal reference. Preserve the intentionally incomplete two-million-event run.
2. First implement and independently audit episode-aware admission after zero-channel closure across all baselines. Current in-flight search can continue after a traversed pair closes; distinguish this from already-admitted settlement control grace. Then use concurrent random local DFS as the temporal Sarafu baseline, retain Numbat as a synthetic competitor, and run matched loss/sleep comparisons with amount-weighted posting and partial-commit measurements. Start with a bounded prefix before full-scale runs.
3. Implement temporal Headroom in a separate prototype using issue 003's explicit pair episodes and strict zero-channel closure. Test local admission, cap updates, reversal and stale-message rejection before performance comparisons.
4. Investigate a locally observable contention/backoff policy only after measuring reservation failures and traffic costs. Do not promote the failed fixed mixture or default to turn waiting.

## Completed checkpoints

- Published the Numbat/Jerboa/Jaribu 50k comparison at `5602b07`; Numbat did not beat the earlier achieved-clearing scores. See [comparison](../experiments/ANIMAL-COMPARISON.md).
- Implemented static-cap Headroom search and independently tested Alice's example and a greedy trap. [Issue 001](issues/001-headroom-clearing.md) tracks this work.
- Ran cold-start Headroom, a restoration-disabled control, and diagnostic legacy postpasses. Local routing is implemented, but the harness serializes initiators globally. Results: `experiments/results/headroom.json`.

## Latest completed evidence

- Numbat + serialized Headroom reaches 14.12–14.68% static clearing in two seeds; the restoration-disabled postpass adds nothing. See [Headroom](../experiments/HEADROOM.md).
- Timestamped fixture, loss/sleep transport and independent per-edge settlement replay are implemented. Completed matrices: 432 synthetic, 18 Sarafu 1,000-transfer and 18 Sarafu 5,000-transfer runs. See [temporal results](../experiments/TEMPORAL-RESULTS.md). Numbat's aggregate advantage is modest and workload-dependent.
- Genuine neighbour turns are integrated. Completed synthetic and 1,000-transfer comparisons generally show extra cost, not an improvement. See [turn results](../experiments/TEMPORAL-TURNS.md).
- Full-prefix runs at a two-million-event budget were censored, not successful completions. Preserve these negative results.
- A finite resumable campaign runner saves state and validates hashes. It runs benchmark processes; it cannot wake an assistant session.

## Active work — verify files and completion before resuming

1. **Full temporal scale completed:** `results/temporal-sarafu-full-10m.json`; all three clean seed-0 methods pass audit for 30,726 transfers. Random DFS wins this clock (15.3393% final-debt improvement versus Numbat 14.0126%, largest-first 12.8083%). The separate finite clock/seed campaign below has completed. Owner: `temporal_sarafu`.
2. **Turns on 5,000 transfers completed:** all 36 runs audited; turns generally cost more. See `TEMPORAL-TURNS.md`.
3. **Headroom search ordering completed:** decrease-first reaches 12.20–12.35% cold clearing; see `HEADROOM-SEARCH.md`. Next: strict-zero-channel temporal semantics, owners `headroom_math` / `headroom_impl`.
4. **Local settlement priority completed:** 72 audited runs modestly improve FIFO turns but lose to concurrent Numbat; see `TEMPORAL-PRIORITY.md`. Next: versioned unposted-transfer and staged-commit exposure metrics, owners `temporal_protocol` / `jerboa_compare`.
5. Review the campaign manifest before launching followups; avoid duplicating live runs or repeating known insufficient event budgets. Save commands, hashes and incomplete markers.
6. Integrate Headroom into changing graphs only after specifying cap epochs and zero-channel reopening rules. Do not silently introduce unlimited trust or permanent channels.
7. Bound protocol memory safely; investigate crash recovery separately from state-retaining sleep.

Agents may activate an idle teammate with a concrete follow-up task and notify the primary agent. Keep file ownership explicit and avoid circular wake-up messages. Multiple useful tasks should run in parallel while the session remains active.

## Resume commands

From the repository root:

```sh
/workspace/tools/strategy-pit-python/bin/python -m unittest discover -s experiments -p 'test_*.py' -q
/workspace/tools/strategy-pit-python/bin/python experiments/headroom_benchmark.py --input /tmp/animal-50k-debt.csv
/workspace/tools/strategy-pit-python/bin/python experiments/headroom_numbat_pipeline.py /tmp/animal-50k-debt.csv
```

These benchmark commands overwrite their default result files. Inspect existing JSON and processes first. The temporary debt fixture can be regenerated using the pinned Jerboa 50k input and the command in [the comparison report](../experiments/ANIMAL-COMPARISON.md#reproduce). Live processes may not survive a cloud snapshot; saved files and commands are the checkpoint.

## Historical campaign launch (2026-10-10 07:09 UTC)

The reviewed follow-up manifest was launched with worker PID **43253**, execution
session **48953**, a 5,400-second total wall-clock bound and 1,800 seconds per job.
It tests full-prefix clean transport at 500 ticks (10M events), 4,000 ticks (20M),
and 2,000 ticks with seed 1 (10M), each with all three algorithms. It does not
repeat the separate seed-0 2,000-tick run in session **88817**. Source files are
frozen for these jobs; inspect the saved heartbeat and process state before
attempting a resume.

State: `experiments/results/temporal-followup-campaign-state.json`.
Per-job logs are saved beside that file. Exact resume command:

```sh
python experiments/research_campaign.py experiments/research_campaign_followups.json \
  --state experiments/results/temporal-followup-campaign-state.json \
  --resume --max-seconds 5400
```

The separate full-prefix seed-0 job is complete (all three algorithms). Its
identical resume command verifies and reuses those rows without rerunning:

```sh
python experiments/temporal_scale_benchmark.py \
  --csv /workspace/jerboa-review/__tests__/fixtures/sarafu-50k.csv \
  --output experiments/results/temporal-sarafu-full-10m.json
```

A running process is not a guarantee of survival after environment removal.
Completed result rows and explicit incomplete markers are the durable evidence.

Campaign progress at 2026-10-10 07:14 UTC: the 500-tick full-prefix job is
complete and audited for all three algorithms. Random DFS again has the lowest
final debt (6,304,111.295), ahead of Numbat (6,412,139.295) and largest-first
(6,516,782.295). The 4,000-tick job is running; the second-seed job is pending.
This status is a checkpoint, not a replacement for inspecting the live state JSON.

## Work activated October 11

- `episode_protocol`: separate strict channel-episode protocol and targeted tests; preserve frozen baseline sources.
- `episode_review`: independent stale-message, zero/reopen and settlement-grace review.
- `fault_matrix`: matched random/Numbat comparisons after the episode API freezes; include exposure metrics.
- `temporal_headroom`: small prototype and comparisons under issue 003; label serialization explicitly.
- `contention_study`: measure abort costs and test one preregistered local backoff policy if justified.

These are assignments, not a guarantee that agents remain active after session interruption. Inspect actual status and artifacts when resuming.

## October 11 next-stage checkpoint

Published strict episode admission and the serial temporal Headroom milestone at `fd59e59`; synthetic fault/backoff evidence at `f55ef75`. The 144 strict synthetic fault runs completed and audited: Numbat final debt -3.29% relative to random, but staged-commit exposure +18.23%. The 24-case Sarafu5000 batch remains in progress; inspect `results/temporal-episode-sarafu5000.json` before any resume. No full-prefix strict fault run was launched at this checkpoint.

Two 96-run training experiments completed: reservation-triggered backoff and cancellation-only episode admission. Both failed their declared promotion gates. Episode-only admission improves final debt but increases posting exposure; retain it as a measured tradeoff, not a default replacement.

Concurrent signed Headroom source is frozen at SHA256 `0f3f2d7b2a476c3b16c986b4cc1a0ac5c3edc8b38a6e3121aa04ea2d41ba6f49`; ten focused/independent tests cover restoration, zero closure, loss/sleep/reordering and locality. A bounded comparative matrix is being prepared; no concurrent performance claim yet. The latest whole-repository test run passed 182 tests.

## Completed prefix and concurrent evaluations

All 24 strict Sarafu5000 fault runs completed and audited; random wins 9/12 final-debt pairs, aggregate improvement 0.76351% versus Numbat 0.73526%. The prefix gross-arrival reference permits at most 1.21061% improvement, ignoring chronology. The full strict six-case fault campaign is now running through the finite campaign runner (state `results/research-campaign-episodes-state.json`, total limit 3600 seconds); inspect completion before restarting.

Concurrent Headroom is published at `72298e5`. All 24 matched runs audit, but restoration leaves 0.94% more final debt and uses 30.69% more wire attempts. The separate decrease-first variant passed training then failed held-out evaluation: 1.92% more debt and 26.88% more attempts. Retain both negative outcomes; no promotion. Latest full suite: 185 passing tests.
