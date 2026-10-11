# An optimistic bound for temporal final debt

The public 50k-line Sarafu fixture has an offline **23.485073% upper bound on final
debt improvement** when both directions of the original transfer totals remain
available to the optimizer. This is a relaxation of the temporal problem, not an
attainable temporal optimum or a node-local algorithm. Its minimum remaining debt
is **5,688,567.495 Sarafu**.

The familiar **18.921189%** MCF result solves a different problem: cancellation
only on the final, bilaterally netted graph. Chronological clearing can use links
that disappear in that final graph, so that percentage is not a general bound on
online results. The new reference retains these possibilities while ignoring
whether their timing permits them.

## Optimization and bound proof

Let `G_ab` be the gross sum of external arrivals from node `a` to node `b`, before
bilateral netting. Keep both directions as separate directed arcs. Solve:

```text
minimize    sum R_ab
subject to  0 <= R_ab <= G_ab
            outgoing(R) - incoming(R) = outgoing(G) - incoming(G) at every node
```

`R` is retained debt. Every arc has unit cost. The removed flow `F = G - R` is a
nonnegative circulation, whose cycle decomposition may include two-cycles. In this
offline representation a two-cycle means bilateral netting; it does not require
a separate two-party clearing protocol.

To see why this bounds a completed temporal run, let `Q_ab` be the cumulative
amount removed in direction `a -> b` by bilateral netting and `C_ab` the total
committed cycle clearing in that direction. For each pair, `Q_ab = Q_ba`. Starting
with an empty ledger, every directed unit of an arrival is either still present,
removed bilaterally, or removed by a cycle, so:

```text
G_ab = R_ab + Q_ab + C_ab
```

All terms are nonnegative. `Q` is a sum of symmetric two-cycles. After settlement
has drained, `C` is a sum of complete cycles, even if their legs committed at
different times. Thus `F = Q + C` is a circulation bounded by `G`, and every valid
completed temporal result is feasible for this optimizer. Its minimum `L` is
therefore a lower bound on temporal final debt. If baseline debt without clearing
is `D0`, then `(D0 - L) / D0` is an upper bound on final debt improvement.

This argument assumes cancellation-only cycle commits and bilaterally netted
external posting, the rules used by the temporal simulator. It does not cover
extra credit creation or arbitrary trustline debt restoration beyond gross arrival
capacities. The bound is on final debt, not gross cumulative cycle clearing,
posted-debt area, or clearing speed.

The relaxation ignores arrival order, forced early bilateral netting, discovery,
message delivery, reservations, sleeping nodes, and computational budgets. It can
choose clearing opportunities that were never simultaneously available. No claim
of attaining this bound follows from the solver returning `OPTIMAL`.

## A triangle separating the two references

Suppose all amounts are one:

```text
time 1: A -> B
time 2: B -> C
time 3: C -> A
         clear A -> B -> C -> A
time 4: B -> A
```

The online result contains only `B -> A`, so final debt is one. The final-batch
bilaterally netted graph instead contains `B -> C` and `C -> A`: debt two and no
cycle. Static cancellation cannot improve it. On the gross graph, MCF retains
only `B -> A` and removes the three-cycle, attaining the relaxed lower bound one.

Now change the arrival order to `A -> B`, `B -> A`, `B -> C`, `C -> A` and require
immediate bilateral posting. The first two transfers cancel before the other
links appear. No cycle ever exists and final debt stays two. The gross graph and
its lower bound one are unchanged. This demonstrates that gross optimization
ignores chronology; it does not prove attainability for a specified posting
schedule. A model permitting arbitrary postponement of external transfers would
be a further, different scheduling problem.

## Public-prefix result

[temporal-reference.json](results/temporal-reference.json) records the exact
integer-valued optimization results, solver version, source and input hashes,
and complete residual-flow certificates. It uses the same 30,726 STANDARD
transfers and peer numbering as the temporal replays. The no-clearing final debt
is **7,434,585.295 Sarafu**, while gross transfer volume is **11,647,216.905**.

| Result or reference | Final debt | Improvement from no-clearing final debt |
| --- | ---: | ---: |
| Gross-arrival MCF relaxation: optimistic bound | 5,688,567.495 | 23.485073% |
| Final-batch MCF: static optimum | 6,027,873.395 | 18.921189% |
| Temporal random local DFS, clean seed 0 | 6,294,172.695 | 15.339290% |
| Temporal Numbat, clean seed 0 | 6,392,808.295 | 14.012577% |
| Temporal largest-first local DFS, clean seed 0 | 6,482,338.295 | 12.808341% |

The algorithm rows come from completed, independently audited runs in
[temporal-sarafu-full-10m.json](results/temporal-sarafu-full-10m.json), with arrivals
compressed to 2,000 ticks, search deadline 2,300, and subsequent drain. Random
local DFS leads this particular temporal run. The MCF rows are offline references
with different feasible sets, not competing protocols with matched resource
budgets. Neither establishes a universal ranking or the optimum for this exact
chronological replay.

For every solver result, the program checks residual arc capacities, original net
positions, circulation conservation of removed amounts, and equality between the
reconstructed objective and the solver's reported optimum. A positive-cost optimum
must not retain opposing arcs; that is checked too. OR-Tools supplies the optimal
status; these primal checks do not constitute a separate dual optimality proof.
Four small tests include exhaustive enumeration of integer feasible residuals and
the chronology examples above.

## Reproduce

```sh
python experiments/temporal_reference.py \
  --csv /path/to/jerboa/__tests__/fixtures/sarafu-50k.csv \
  --output /tmp/temporal-reference.json
python -m unittest discover -s experiments -p 'test_temporal_reference.py' -v
```

Install the optional solver using `experiments/requirements-mcf.txt`. This run used
OR-Tools 9.14.6206 with Python 3.12.14. The input SHA-256 is
`785b8f57d3e7e485a678772727bf593aaa90594c833afb7abc3c4d5fb366eebb`.
The reference is graph-wide measurement only; none of its results feed back into
node-local routing or settlement decisions.
