# Rank-weighted Numbat: one preregistered hypothesis

Numbat's fourth-power amount weighting can concentrate almost all exploration on
large balances when local debt amounts are highly unequal. Test one bounded
alternative: assign each eligible neighbor the **dense ascending rank** of its
currently available balance (smallest distinct balance rank 1); equal balances
receive equal rank. Select weighted random order without replacement using these
ranks. For balances 1, 1, 100 the weights are 1, 1, 2, not 1, 1, 100^4. This is
one specified policy, not a sweep over powers, mixtures, rank definitions or caps.

Only local available balances determine ranks. Keep Numbat's observed path capacity
hints, strict episode/revision admission, capacity rechecks, reservations and
staged settlement unchanged. Search candidate eligibility is unchanged.

Training uses fresh seeds 301/302, 24/72 nodes, sparse/community/bursts, and clean
transport/no sleep or independent 30% data+ACK loss with seeded sleeps. Compare
random DFS, unchanged Numbat, and rank-weighted Numbat: exactly 72 runs. Arrival
window 500, horizon 800, retry interval 50, max delay 5, retransmit 20, max hops 32,
search budget 96; two-million-event bound separately for run and drain. Pin
sources/arrivals and report failures without enlarging their budgets.

Gate: all runs complete and independently audit; candidate aggregate final debt
must be strictly lower than **both** controls; physical data+ACK attempts must be
at most 110% of the control having lower aggregate final debt; and horizon
unposted transfer count and amount must not exceed that control's aggregates.
Report per-case wins/losses, posting delay amount-time and partial-commit exposure
rather than combining them into an invented score. More settlement can increase
staged exposure; a passing gate does not imply every metric improves.

If training passes, evaluate the unchanged policy on seeds 303/304 with the same
matrix and gate. If training fails, do not run held-out or Sarafu tests or retune
parameters. A passing small synthetic result would still not demonstrate an
advantage on heavy-tailed Sarafu; that is the motivating hypothesis, not evidence.
