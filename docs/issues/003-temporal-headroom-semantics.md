# 003 — Temporal Headroom: consent ends when a channel closes

**Status:** In progress · **Opened:** 2026-10-10

[Issue tracker](README.md) · [Fixed-cap Headroom](001-headroom-clearing.md) · [Temporal protocol work](002-temporal-faults-and-turns.md)

## Scope and constraint

Specify Headroom Clearing when new transfers arrive, balances reverse and channels disappear. This is a design proposal, not an implemented or benchmarked temporal Headroom protocol. Existing Headroom results retain original relationships at zero; they cannot establish performance under the rule below.

**A zero bilateral balance closes the economic channel.** Old headroom does not authorize reopening it. Only an accepted external transfer that leaves a nonzero balance can open a new episode. Completion and acknowledgement of already-started work may use control grace restricted to those admitted operations; that grace cannot carry fresh searches or restoration proposals across a closed relationship. Restricting its purpose does not guarantee finite cleanup under unbounded loss.

A channel episode is local to a pair of peers. It is not a network-wide batch or a synchronized clearing epoch.

## Proposed local state and consent

For each live episode, the two peers agree on:

- A pair identifier, a fresh episode identifier, and a monotonic revision.
- The current debtor and creditor, current debt `x > 0`, and ceiling `B >= x` in one common unit.
- The policy permitting restoration up to `B` during this episode, including the transfer update rule below.
- Outstanding reservations and the identifiers needed to complete or reject old work safely.

The current creditor authorizes the maximum exposure; both peers authorize settlement changes. Agreement to a ceiling is permission to consider a proposal, not proof that every proposal will be accepted. A preference callback may veto a redistribution. Initial experiments should use the same explicit eligibility policy for all peers and record vetoes separately if preferences are added.

Neither endpoint needs any other pair's balances or limits. Messages may carry a traversed path and its aggregate cost/capacity. Authentication and durable bilateral agreement remain protocol work; this specification does not turn the current simulator's single-owner ledger into a replicated settlement system.

## Canonical cap update: preserve headroom within a live episode

Represent a newly accepted external transfer by signed amount `d` in the episode's current direction: positive adds debt from its current debtor to creditor, negative offsets it. Compute `y = x + d` only after earlier reserved work on this pair is resolved.

| Event | New balance and ceiling | Episode |
| --- | --- | --- |
| First transfer on a closed pair, nonzero resulting debt | `x = B = abs(transfer)`; debtor follows its sign | Open a fresh episode |
| External transfer with `y > 0` | `x' = x + d`, `B' = B + d` | Keep direction and episode; increment revision |
| External transfer with `y = 0` | Zero balance; discard all unused headroom | Close the episode |
| External transfer with `y < 0` | Reverse direction; `x' = B' = -y` | Close the old episode and open a fresh opposite episode |
| Clearing changes debt, leaving `x' > 0` | Keep `B`; validate `x' <= B` | Keep episode; increment revision |
| Clearing reduces debt to zero | Discard `B` as future permission | Close the episode |

For a nonzero same-direction episode, the transfer rule preserves unused headroom:

`B' - x' = (B + d) - (x + d) = B - x`.

For example, if `x = 4`, `B = 10`, an additional debt of 3 produces `x = 7`, `B = 13`. An offsetting transfer of 2 instead produces `x = 2`, `B = 8`. Both retain six units of previously agreed headroom. This follows the episode's agreed update policy; do not infer a raised ceiling from an unaccepted transfer message.

An offset of 4 closes that episode and destroys the unused six units. An offset of 9 reverses the original `x = 4`: close the old episode, then open the opposite direction at `x = B = 5`. Its initial headroom is zero. No old-direction ceiling survives that reversal.

A clearing move never raises the ceiling. A restoration consumes headroom; a reduction creates it only while the channel remains nonzero. Resetting `B` after every clearing would eliminate the very permission being tested. Conversely, restoring `B` from an old contact record after closure would silently violate the zero-close rule.

A creditor may separately request revocation of unused headroom, reducing `B` to a value at least `x`. Apply such policy changes only after resolving affected reservations, record them as consent events, and benchmark them as a separate treatment. Revocation cannot erase existing debt.

## Which residual moves remain available?

On a live original-direction edge, local residual actions are:

- Reduce debt: capacity `x`, cost -1 per unit; using all `x` closes the episode.
- Restore debt: capacity `B - x`, cost +1 per unit; available only while `x > 0` and both peers still consent.

Accept only a cycle with strictly negative total cost. Recheck all capacities and episode identifiers during preparation. Every completed cycle preserves signed net positions and strictly reduces total debt, although a participant's gross exposure may increase within its accepted ceilings.

A closed edge contributes **neither** residual action. A search cannot reach its former peer by treating dormant headroom as a live reverse edge. After a genuine external reopening, the new episode begins with zero headroom; later partial clearing can create new headroom.

The fixed-cap proof that absence of a negative residual cycle implies the original MCF optimum does not transfer unchanged. Closing an edge irreversibly removes an action that could have helped later. Search order, closure order, transfer timing and new consent now affect the attainable outcomes. A bounded search's failure to find a cycle still provides no optimality certificate.

## Hand-worked examples

### The original Alice example is blocked after full clearing

Start with debts `Alice->Bob 7`, `Alice->Charlie 5`, `Doris->Alice 5`, `Charlie->Doris 5`, `Bob->Charlie 3`. Total debt is 25.

Clearing the five-unit Alice–Charlie–Doris loop leaves `Alice->Bob 7` and `Bob->Charlie 3`, total 10. The Alice–Charlie channel has closed. The former Headroom move restoring three units on it is now forbidden, even though its old ceiling was five. An existing control connection or stale token must not change that result.

A later external `Alice->Charlie 2` may open a new episode with ceiling two. It does not revive the old five-unit ceiling or immediately supply restoration headroom.

### Nonzero restoration still works

Change only the starting Alice–Charlie debt to **6**; the five initial debts now total 26. The first five-unit loop leaves:

- `Alice->Bob 7`
- `Alice->Charlie 1`, still live with ceiling 6
- `Bob->Charlie 3`

Total debt is 11. The residual cycle Charlie→Alice→Bob→Charlie can restore Alice–Charlie by 3 and reduce the other two debts by 3 each. The final debts are `Alice->Bob 4` and `Alice->Charlie 4`, total 8. Alice keeps signed net debt eight throughout both cycles. The Bob–Charlie channel closes at the end; Alice–Charlie never closed.

Thus strict closure blocks restoration from **zero**, not restoration from every balance that has previously decreased.

### Stale messages cannot reopen an episode

Suppose a proposal quotes episode 12 at `x = 1`, `B = 6`. Another completed clearing closes it. An external transfer then opens episode 13 at `x = B = 2`. A delayed prepare or advertisement for episode 12 must be rejected as stale, even if its amount happens to fit episode 13's current balance. Matching peer identities alone is insufficient authorization.

## Reservations, posting order and control grace

1. Quotes and search steps carry episode and revision identifiers. On delivery of a search step, the receiver checks that the traversed pair episode is still live. If it has closed, cancel or restart that discovery rather than using control grace to continue it. Closure of an earlier remote path segment may remain unknown until validation; preparation must recheck the candidate route locally, not assume token observations are current. Preparation checks current local state and obtains consent from both incidences of each participant.
2. Serialize economic writes on an individual pair. A transfer waits while an earlier prepared settlement owns that pair; a new preparation waits or fails if an earlier transfer is being posted. Use a stated endpoint-local ordering/turn mechanism, not a graph-wide scheduler. Tests must cover opposing simultaneous requests and starvation.
3. Do not change balance, cap, direction or episode in the middle of a prepared pair update. Commit or abort releases its reservation. Different pairs may proceed concurrently; this does not make an entire cycle atomic while its commit messages are in flight.
4. As soon as a committed local balance reaches zero, stop admitting economic work on that episode. Completion traffic may finish only the already-admitted transaction or cancel stale searches; it must not forward fresh discovery through the zero edge.
5. A proposed first temporal implementation may retain a tombstone and reliable-delivery receipts until existing work is acknowledged. Any bounded grace timeout leaves unresolved work explicitly pending or failed according to a stated recovery protocol; timeout alone does not safely undo a possibly committed change.
6. Old packets must remain unable to revive old authority after cleanup. A duplicate of a previously applied commit may receive its stored receipt, but must never apply again; an unknown stale commit cannot authorize a new write. Use durable episode freshness and transaction identifiers. Bounded memory under unbounded packet delay, permanent loss and crash recovery is a separate open requirement, not a property supplied by a timeout.

Keep an ordered ledger-event log. With interleaved transfers and staged commits, check net positions after completed/drained settlement accounting and against the posted external transfer history; do not invent atomic cycle completion at a later timestamp to replay earlier inputs.

## Fair epoch and algorithm comparisons

Use the same timestamped transfers, unit scale, message timing, loss/sleep schedules, posting-order policy and event-budget rules. Episode boundaries follow each run's actual zero crossings; they cannot be forced to match across algorithms without changing the model. Report those differences rather than silently retaining channels for one algorithm.

The current temporal prototype allows some already-started search steps to continue after their traversed pair closes. Apply the stricter episode-aware admission check above to every comparison baseline before treating it as this specification; existing transport-grace results are not yet evidence for that stronger rule.

Run at least these declared treatments:

1. Cancellation-only baseline under strict zero closure.
2. Temporal Headroom using the same transport, concurrency rules and strict closure, with the cap updates above.
3. A labelled sensitivity control that sets `B = x` after every accepted external transfer, discarding old headroom. This tests whether retaining headroom across transfers matters; it is not the canonical rule.
4. If desired, a retained-zero-channel reference. Label its additional permission and transport availability; do not rank it as equivalent to the strict-close model.

Do not reset caps at a global reporting-window boundary. Windows are for observation, not new consent. If an experiment deliberately renews consent periodically, specify that as another policy and count renewal messages. Reuse the same frozen input and seed list; distinguish exploratory tuning from evaluation.

Report completed cycle debt reduction separately from external bilateral netting. Include outstanding-debt area, posting delay and unposted input at cutoff, messages/bytes/retries, restored volume, mixed cycles, closures/reopenings, stale-episode rejections, consent revocations and unfinished settlements. Compare only final ledgers reconciled to their actually posted inputs; do not count waiting transfers as cleared debt.

Offline MCF may be an explicitly optimistic reference on a frozen snapshot with its stated bounds and retained edges. It sees more than the online protocol and ignores future closure/consent restrictions unless those are separately modeled. It must not choose local routes, epochs or cap updates, and its percentage is not a proof of an attainable temporal optimum.

## Acceptance criteria

- [ ] Implement the cap/episode state machine using only endpoint-local state.
- [ ] Verify same-direction transfer shifts preserve headroom; reversals and zero crossings expire it.
- [ ] Reject the original Alice restoration after closure; accept the nonzero variant above.
- [ ] Show that reopening starts a fresh ceiling and rejects stale economic authority from old prepares, advertisements and commits; duplicate applied commits only receive their existing receipt.
- [ ] Test transfer/prepare races, duplicates, reordered receipts, sleep and dropped acknowledgements without double posting or double settlement.
- [ ] Independently replay per-pair caps and episodes, current debt, external posting and all settled cycle actions.
- [ ] Compare temporal Headroom and cancellation-only under the same strict channel rule and declared budgets.
- [ ] Publish incomplete runs and regressions; do not transfer static Headroom performance claims to this model.

Open choice: a fully concurrent reservation protocol must avoid pair-order deadlocks and starvation. The fixed-cap prototype's global serialization does not solve that requirement in a node-local deployment.

## October 11 implementation checkpoints

- [Episode admission](../../experiments/TEMPORAL-EPISODES.md) implements strict episode and revision checks for cancellation-only random DFS/Numbat. Independent tests cover closure/reopening, stale prepares, local actor access, loss, sleep and transfer/reservation races. Bilateral state installation remains simulator-provided.
- [Serial temporal Headroom](../../experiments/TEMPORAL-HEADROOM.md) validates cap updates and useful nonzero restoration across 12 audited exploratory runs. It is not a concurrent fault-tolerant protocol.
- Concurrent signed residual settlement is in development and requires its own replay and fault tests before comparative claims.
