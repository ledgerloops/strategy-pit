# Concurrent Headroom: decrease-first search preregistration

The initial concurrent restoration experiment increased aggregate final debt by
0.94% and wire traffic by 30.69% against restoration-disabled search. Static
Headroom benefited from prioritizing debt decreases. Test exactly one local
candidate order: debt-decreasing arcs before restoration arcs, then descending
currently available residual capacity, retaining seeded shuffle for exact ties.
The concurrent baseline actually shuffles uniformly; this tests both directional
priority and capacity tie ordering together, not an isolated direction effect.
No settlement, admission, cap, retry or transport change is permitted.

Training: fresh seeds 201/202, 12 nodes, sparse/community/bursts, clean/no-sleep
and independent 30% data/ACK loss plus seeded sleeps. Three matched methods:
original restoration disabled, original restoration enabled, and decrease-first
restoration enabled. Exactly 36 runs, 500 arrival ticks, horizon 800, retry 50,
max delay 5, retransmit 20, max hops 32, search budget 96, two-million-event bound
separately for run and drain. No budget increase after observing failures.

Before training, verify local ordering, capacity/net invariants, zero closure and
loss settlement with the unchanged signed ledger audit. Pin sources and arrivals.
Report debt, data+ACK attempts, mixed cycles, unposted input count/amount at the
horizon, posting amount-time through drain, and signed partial-settlement exposure
(half-L1 per-transaction net imbalance). This signed exposure differs from the
older positive-only committed-edge exposure; do not directly compare them.

Promotion requires every run completes and audits, aggregate final debt no higher
than restoration-disabled control, aggregate physical attempts at most 110% of
control, and no additional unposted input at the horizon in aggregate count or
amount. Preserve per-case outcomes and exposure tradeoffs even on a passing gate.
Original restoration is a diagnostic comparison, not the gate reference.

If training passes, run the identical fixed matrix on held-out seeds 203/204 and
report the same gate independently. If training fails, do not run held-out tests
or tune this ordering. No Sarafu or universal superiority claim follows from this
small synthetic matrix.
