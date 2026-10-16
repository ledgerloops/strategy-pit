# Research queue and checkpoints

[Strategy Pit](../README.md) · [Issues](issues/README.md)

## Objective

Find practical node-local clearing algorithms that perform well across static and changing credit graphs, with explicit costs and delivery/failure assumptions. Continue useful authorized work while the session is active; checkpoint before interruption. This document is not an external wake-up scheduler.

## Verified status — 2026-10-11

The fixed strict-episode seed replication completed at 2026-10-11 09:47:39 UTC:
12/12 cases certified, audited and drained, with no budget-limited cases. Random
local DFS clears more than Numbat in all six seed-1/2 pairs and all nine matched
full-prefix pairs including seed 0. Numbat uses fewer wire attempts in the new
replication, with mixed posting and partial-commit exposure. See the
[replication report](../experiments/TEMPORAL-EPISODE-REPLICATION.md).
This is stochastic robustness on one fixture, not universal superiority.
Historical launch identifiers and snapshots below are not current worker claims.

### Chosen next steps

1. Retain concurrent random local DFS as the temporal Sarafu final-debt baseline;
   preserve Numbat's synthetic advantages and separate exposure/traffic tradeoffs.
2. Evaluate a separately specified smallest-unit channel-retention preference
   before implementing it: net-position coupling means its cost is not bounded
   by simply counting retained edges. Do not change the completed strict protocol.
3. Any next candidate needs prospective training and held-out conditions, the
   same source/input certification, exact ledger audit and finite work budgets.
   Keep the failed backoff, exploration, admission and Headroom variants visible.

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

## Full strict fault comparison completed

`results/temporal-episode-full-comparison.json` joins six complete independently audited full-prefix cases. Final debt improvements random/Numbat: clean 14.76991%/13.13047%; 10% loss plus sleep 13.78407%/12.75147%; 30% loss plus sleep 11.42300%/10.97882%. All inputs posted by the horizon; all settlements drain. This is one seed. Random clears more in each tested condition; Numbat uses fewer messages under faults and has mixed exposure tradeoffs.

Original clean controls use the frozen episode implementation; four fault cases use a trace-tested optimized adapter. Full random-clean saved observations match exactly except wall time (`temporal-episode-gold-equivalence.json`). The join verifies full fast-source pins against that evidence. The original sequential campaign was intentionally superseded after its two clean controls, not failed on a budget. Do not resume that superseded campaign. All five fast case campaigns finished successfully.

A separate safe prefix resume entrypoint, `temporal_episode_benchmark_v2.py`, now rejects changed CSV contents at the same path before delegating to the frozen harness. Use it for future prefix resumptions. Rank-weighted Numbat also failed its fixed training gate; no held-out runs followed.

Next authorized followup: replicate the full strict comparison on fixed seeds 1 and 2 with the same algorithms, clocks, faults and budgets, using at most three workers and a two-hour campaign limit. No parameters will be retuned. The `fault_matrix` agent is preparing the separate driver and checkpoints; verify actual launch state before calling it running.


## Seed replication launched October 11

After independent runner/manifest review and the six-case small seed-0 equivalence
gate, the fixed 12-case seed-1/2 replication launched at 2026-10-11T09:33:36.324545+00:00.
Coordinator PID **102617**, execution session **84912**. The new
parallel wrapper permits at most three case workers, 1,200 seconds per case and
7,200 seconds for the campaign. Source and input files are frozen for this job.

State: `experiments/results/research-campaign-episode-replication-state.json`.
Each child has a separate state/log and result file beside it. The coordinator
state updates on case completion; child states provide frequent heartbeats.
Inspect these and live processes before calling the campaign active or resuming.

Exact resume command (only after confirming the previous coordinator stopped):

```sh
python3 experiments/research_campaign_parallel.py \
  experiments/research_campaign_episode_replication.json \
  --state experiments/results/research-campaign-episode-replication-state.json \
  --max-workers 3 --max-seconds 7200 --resume
```

Methods, admission, timing, fault conditions and budgets match the seed-0 full
comparison; only fixed seeds change. No retuning. The [replication report](../experiments/TEMPORAL-EPISODE-REPLICATION.md)
records the prospective scope and will report all completed or censored cases.
This finite benchmark worker does not wake an inactive assistant session.

## Seed replication completed October 11

The campaign above finished at 09:47:39 UTC with all 12 jobs certified complete.
The completed summary is `experiments/results/temporal-episode-replication-summary.json`;
all raw cases and child states are retained. No case was censored or retuned.
Random beats Numbat in every seed-1/2 final-debt pair. Aggregate across these
12 cases, Numbat has 1.852% more final debt, 0.416% more posted-debt area,
37.705% more unposted-transfer exposure U, 0.722% more staged-commit exposure K,
and 4.193% fewer wire attempts. Keep these costs separate.
The launch and resume commands above are historical/reproducibility instructions,
not a pending campaign.

## Runnable app checkpoint

Implemented `app/` as a TEST-only three-node HTTP/SQLite network with a responsive client. Twenty-four app tests pass, including loss of commit acknowledgement, durable prepare/restart, duplicate delivery, decline, and recovery while paused. Three-browser end-to-end clearing and receipt export pass. See `app/README.md`, `app/TESTING.md` and `app/network-test-results.json`. Discovery is a deliberately limited single-path neighbour walk, not the benchmark DFS implementation. Next product work: versioned bilateral transactions and onboarding, stronger identity/transport, broader crash exploration and replaceable discovery. Never infer production readiness from the testnet.

## Neighbour-private hashlock architecture gap

Recorded [issue 004](issues/004-neighbour-private-hashlock-settlement.md). The owner requires direct-neighbour knowledge only, with no remote identities or exact loop length, and a minimum of three participants. The app currently violates this through explicit paths and origin vote lists; label it an honest-peer infrastructure prototype. Hashlock patching alone is insufficient. Investigate discovery, conditional bilateral consent, fulfillment, evidence and durable safe cancellation together. Implementation was paused before changes; current app state/protocol remains untouched. No in-place migration is authorized by this issue-recording task.

## Private hashlock v2 implementation

The owner subsequently authorized implementation. `app/private_node.py` and `run_private_demo.py` now implement opaque, local predecessor/successor routing, conditional bilateral consent and context-bound SHA-256 fulfillment without a participant list or hop count. Fixed-amount search rejects reflections and revisits; a failed-subcycle cleanup defect found during review is covered by regression tests. Separate SQLite databases, durable inbox/outbox and local-only receipts support selected crash/replay recovery. Legacy/v2 runtimes reject each other’s databases; no old state was migrated. See `app/private_protocol.md` and `app/PRIVATE_TESTING.md` for evidence and honest-peer/metadata/permanent-loss limits. Issue004 remains in progress for production security and operational gates.

## Comfort-zone address book and simulation

Implemented per-contact credit grants, own preferred min/max, received peer preferences, mirrored/clipped shared zones and explicit empty overlap. Settings persist and synchronize to direct peers with revisions; reserved edges defer edits. The saved assistance checkbox is not active authority in manual cancellation-only v2. Sixty-three app tests and browser contact flows pass. The separate 32-run comfort simulation passes 10 tests and preserves hard limits and net positions; discomfort improves 10.4% static / 11.3% with arriving transfers versus cancellation, with 51.2% more static discovery messages. Illustrative debt 2→4 / discomfort 2→0. See app/COMFORT.md, experiments/COMFORT-SIMULATION.md and issue 005. Next work: versioned bilateral admission for actual comfort-assisted hashlocks, asymmetric/partial-opt-in tighter-limit fixtures, then faults/concurrency.

## Contact controls and history

Replaced numeric preference inputs with aligned draggable dots, keyboard steps, scale controls and a live shared-zone preview. Each contact links to its filtered recent clearing history and local receipt export; exports disclose that both local edges are included. Browser tests cover pointer/keyboard editing, preserved drafts, mirrored preference synchronization, mobile layouts, offline guards and a real three-node hashlock receipt. See app/COMFORT.md and updated screenshots. Settlement and automatic-adjustment policy are unchanged.

## Comfort-assisted hashlock integration

Explicit comfort mode now connects synchronized preferences to manually approved private hashlocks. Both signed directions, zero-balance helpers, pinned bilateral revisions, local edge quotes and policy-bound receipt verification are implemented. Full app suite: 90 tests; focused simulation suite: 16 tests. Independent review fixed a signed-direction receipt-verification gap. Real HTTP coverage includes 3/5-node identity-local audits, loss, restart, stale admission and overlapping discovery; both conflicting searches may abort safely. Expanded 160-run simulation preserves negative results and blocked-transfer denominators; earlier aggregate improvements do not generalize. See app/comfort_protocol.md, app/COMFORT_REVIEW.md, app/comfort-settlement-test-results.json and experiments/COMFORT-EXPANDED-REVIEW.md. Reproduce using app/run_comfort_demo.py with a fresh directory. Next unresolved product gates: external bilateral transfer admission, bounded operational recovery, identity/backups and an explicit unattended-consent policy. No public deployment or production claim.

## Headroom retention drafts published as research

Published the four previously local one-unit retention files as a documented baseline: analysis, offline MCF reference, pinned Sarafu ledgers and three focused tests. All three tests pass; regeneration reproduces the saved JSON byte for byte. The note distinguishes these fixed-cap debt-reduction experiments from the app’s comfort objective, preserves the 120-unit retention counterexample, and makes no node-local or dynamic-execution claim for the oracle. No retention behavior was added to the app.

## Linked comfort controls and automatic preference saving

The browser now keeps personal comfort endpoints within the user's own credit maximum: extending the comfort maximum pulls the credit arrow along, and lowering that arrow pulls back both endpoints as needed. Preferences save automatically after range release or a brief pause in keyboard edits; the assistance checkbox also saves without a Save button. Per-contact status distinguishes local persistence and queued peer delivery from pending/failed writes. Failed drafts are retained, and a committed write with a lost response is reconciled against refreshed preferences rather than blindly submitted twice. Pointer drags survive background rerenders; stale GET responses cannot restore old preference revisions. Legacy out-of-limit zones are fitted only in the editable draft until the user changes a control.

Validation: `test_comfort_browser.cjs` passes with real local HTTP nodes and Chromium, covering one write on drag release, linked bounds, keyboard focus, reload persistence, rejected-write retry, lost-response reconciliation, independent-contact focus, mirrored zones, mobile layouts and offline controls. `test_comfort_settlement_browser.cjs` also passes: the real three-node comfort settlement still requires all manual approvals and conserves each signed net position. No backend settlement or unattended-consent policy changed.

## Bilateral obligation entry and history

Implemented private-v2 TEST obligation proposal, exact counterparty approval/decline, and persistent per-contact listing. New obligations use authenticated direct-peer offer/accept/commit/settled messages, exact mirrored balance/preference snapshots, existing per-edge reservations, and atomic SQLite decision/balance/outbox writes. Proposal IDs deduplicate retried client requests and message replay; stale proposals abort with retained history. Unresolved proposals remain visible alongside 100 recent terminal entries. The UI lists obligations, integrates them into Activity/contact history, preserves proposal drafts and unconfirmed IDs, and shows local-posting versus peer-completion status. Submission reserves the edge and records proposer consent; there is no proposer withdrawal or timeout unlock.

Added `run_obligations_demo.py`, a seed-once zero-balance triangle with 10 TEST credit grants; restarts preserve balances, preferences, decisions and reservations. The browser enters Alice→Bob→Doris→Alice obligations, obtains each peer approval, and clears the actual resulting balances to zero, preserving obligations and clearing history. No real assets or account enrollment added.

Validation on October 16: the full 105-test app snapshot passed, then six subsequently added tests passed separately (111 current Python tests covered). This includes 13 focused obligation unit tests, four real-HTTP network tests and four launcher lifecycle tests. The new real-browser flow passed proposal/approval/decline, mirrored balances, limit rejection, description escaping, reload/history, manual clearing, responsive layouts, offline guard and delayed-request disconnect/reconnect. The existing contact/autosave browser regression also passed; its lost-response check now waits for the injected 503 response before asserting stable recovery. Independent protocol/UI review corrected unresolved-list visibility, stale-session busy state and recovered-proposal notices. See app/OBLIGATIONS.md for API, demo and honest-peer/recovery limits.
