# Preregistered cancellation admission experiment

Strict revision admission rejects a search after **any** change to its traversed
relationship, even when the economic channel stays open with the same direction.
The previous backoff training controls observed more stale episode/revision
prepare rejections than reservation conflicts. That motivates measuring the cost
of exact revision equality separately from the user's zero-channel rule.

Candidate: accept search and prepare messages within the same currently live
**episode**, ignoring its revision number. Reject closed, reversed or reopened
relationships identically to the strict baseline. Recheck current local outgoing
available debt during prepare and use the same reservation/commit protocol. This
is cancellation-only DFS/Numbat: no restoration, increased credit, preference
change, or Headroom cap authority. Search observations can be stale; settlement
uses the current amount, so the old quote is not authority to spend more.

Before training, tests and independent review must verify closed/reopened and
reversed channels remain rejected, same-episode stale revisions cannot overdraft,
local reservation conflicts still abort, and old commit control cannot acquire
new authority. No frozen baseline file may change.

Training is exactly 96 paired runs: synthetic sparse/community/bursts, 12/24
nodes, seeds 101/102, random/Numbat, strict versus episode-only, clean/no-sleep
and independent 10% data+ACK loss with seeded sleeps. Arrival duration 500,
horizon 800, retry interval 50, max delay 3, retransmit 20, max hops 64 and search
budget 64. Each run and drain has a separate two-million-event budget. Preserve
incomplete outcomes and source/input hashes; never increase a budget after seeing
which candidate fails.

For each method independently, promote only if all runs complete and audit,
aggregate final debt does not rise, physical data+ACK attempts fall at least 5%,
amount-weighted external posting delay and partial-commit exposure through drain
do not increase, and no more than six of 24 paired cases have higher final debt.
Also report horizon exposure, unposted input and unsettled work. Posted-debt area
alone can reward delayed posting and is not the gate.

Only a passing method proceeds unchanged to seeds 201/202 and the 5,000-transfer
Sarafu prefix. A failure remains a published result; no parameter sweep follows.
This conservative gate may reject a useful tradeoff. Results will describe that
tradeoff without changing the gate after observing it.
