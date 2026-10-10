# Research queue and checkpoints

[Strategy Pit](../README.md) · [Issues](issues/README.md)

## Objective

Find practical node-local clearing algorithms that perform well across static and changing credit graphs, with explicit costs and delivery/failure assumptions. Continue useful authorized work while the session is active; checkpoint before interruption. This document is not an external wake-up scheduler.

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

1. **Full temporal scale:** `temporal_scale_benchmark.py`, `results/temporal-sarafu-full-10m.json`; 30,726 transfers, three clean methods, ten-million-event budget. Owner: `temporal_sarafu`.
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

## Live finite replay campaign (2026-10-10 07:09 UTC)

The reviewed follow-up manifest is running with worker PID **43253**, execution
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

The separate full-prefix seed-0 job checkpoints each algorithm and can be resumed
with the identical command after verifying its original process has stopped:

```sh
python experiments/temporal_scale_benchmark.py \
  --csv /workspace/jerboa-review/__tests__/fixtures/sarafu-50k.csv \
  --output experiments/results/temporal-sarafu-full-10m.json
```

A running process is not a guarantee of survival after environment removal.
Completed result rows and explicit incomplete markers are the durable evidence.
