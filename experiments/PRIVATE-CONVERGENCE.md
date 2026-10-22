# Convergence of private headroom clearing

Research analysis, 22 October 2026. This is a conditional mathematical result,
not a convergence claim for the current implementation. Hosting all nodes does
not give the algorithm access to the global objects used in this proof.

## The precise optimization problem

Take a finite fixed graph with one bilateral trustline per unordered node pair.
Choose an arbitrary orientation for each edge. Its signed integer balance is
`x_e`, its fixed allowed interval is `[l_e, u_e]`, and `A x = b` fixes every
participant's signed net position. Minimize gross debt:

`F(x) = sum_e |x_e|`, subject to `A x = b` and `l <= x <= u`.

Assume a feasible starting ledger, fixed integer bounds, no further external
transactions, and permission to execute any cycle adjustment within those
bounds that strictly lowers total gross debt. In particular, some participants
may increase their local absolute exposure within their agreed intervals.

These assumptions are stronger than unchanged comfort settings. Shared comfort
intervals can supply the bounds if the initial ledger is inside them and the
consent policy permits all required adjustments. Per-step non-increasing
discomfort, local nonexpansion, missing opt-in and fresh approval refusals are
additional restrictions. Existing balances outside a comfort interval require
a separately specified feasible-set model; do not silently treat them as inside.

## 1. Eventual discovery and completion

The useful progress statement is: if the settled ledger remains nonoptimal,
an improving admissible operation eventually completes. A particular historical
loop need not be found: another settlement may remove it first.

A distributed exhaustive search can retain its predecessor, current branch and
tried direct neighbours at each participant. No complete route, remote identity
list or hop count needs to travel with the probe. For headroom search, eligibility
depends on the incoming edge and active path, so backtracking must restore the
appropriate search context. Ordinary directed-cycle detection and exhaustive
search for admissible headroom cycles are different search problems.

A protocol proof must establish all of the following:

- Continuing initiation covers every relevant component and branch fairly.
- Delivery eventually succeeds and local processing continues.
- Competing searches cannot cause permanent starvation or abandoned locks.
- Candidate quotes are revalidated, and admitted hashlock operations eventually
  fulfill or safely abort; no timeout fabricates an abort after possible release.
- Consent covers the economic moves assumed by the optimization model.

For randomized attempts, a sufficient condition is a uniform conditional
success bound `P(success on attempt k | past failures) >= q > 0`. Then the
probability of failing for `k` attempts is at most `(1-q)^k`, which tends to zero.
Independence is not needed for that bound. Merely having some positive success
probability on each attempt is insufficient if it shrinks too quickly.
Almost-sure eventual success is not a finite worst-case message or runtime bound.

The current production search chooses a single branch; the measured private
research searches randomize that choice and also stop at a finite discovery
cutoff. None implements or proves the exhaustive, continuously fair protocol
above. Increasing only the message cap does not remove the time cutoff.

## 2. What can be reversed

If a feasible cycle move takes `x` to `x+c`, its immediate inverse returns to the
feasible state `x`. After other operations, that exact inverse may exceed a bound.
Feasibility alone does not authorize a debt-increasing inverse under an
improvement-only policy; Section 3 instead uses net-improving compensating cycles.
However, any two feasible integer states with the same net positions are connected
by feasible cycle moves: decompose their difference into cycles oriented toward
the target. Each coordinate moves between its two feasible endpoint values, so
it stays within the fixed interval.

This is economic rerouting through **new compensating settlements**, with fresh
hashlocks and the required consent. It does not delete a receipt, revoke a
fulfilled hashlock, reuse its authorization or roll back history.

Unchanged comfort settings alone do not establish this property. For example,
with the fixed comfort zone `{0}`, reducing a balance from -3 to -2 decreases
discomfort, but restoring -3 increases it and is rejected by `comfort_move`.
Within broad zones the edge move can be allowed, while the research policy still
rejects any participant whose two-edge absolute exposure increases.

## 3. Strict improvements suffice to reach the optimum

At a feasible integer ledger `x`, the residual graph has an arc for each unit
increase or decrease permitted by the fixed interval bounds, with respective costs:

`c_e(+) = |x_e+1| - |x_e|` and `c_e(-) = |x_e-1| - |x_e|`.

**Theorem.** A feasible ledger is globally optimal for the fixed problem above
if and only if its residual graph has no negative-cost directed cycle.

**Proof.** A negative cycle immediately gives a feasible unit circulation that
preserves `A x`, respects bounds and strictly decreases `F`.

Conversely, suppose a better feasible ledger `y` exists. Its difference `d=y-x`
is an integer circulation. For each edge, put `|d_e|` units in the residual
direction pointing from `x_e` toward `y_e`. Discrete convexity of absolute value
gives:

`sum_e |d_e| c_e(sign(d_e)) <= F(y) - F(x) < 0`.

Decompose this balanced directed multigraph into cycles. Their costs sum to a
negative number, so at least one simple cycle has negative initial marginal cost.
A one-unit move along that cycle is feasible at `x` and strictly improves `F`.
This proves the criterion.

Repeated successful unit improvements must terminate at an optimum: `F` is a
nonnegative integer and each completed improvement reduces it by at least one.
There are at most `F(x_initial)-F(optimum)` successful improvements. This bounds
settlement steps, not discovery messages or elapsed time. In the simple bilateral
graph, a two-arc cycle would use opposite directions of the same edge; convexity
makes its cost nonnegative. Negative simple cycles therefore have at least three
participants, consistent with the protocol's minimum-three requirement.

A negative residual cycle can recreate some earlier-cleared balances while
removing more debt elsewhere. No completed step that increases total gross debt
is needed. Finding arbitrary cycles, or exhausting ordinary positive-debt cycles,
does not suffice: the search must find improving cycles in the signed residual
graph. Intermediate local fulfillment can leave endpoint mirrors temporarily
unequal; the theorem's iterates are fully applied, consistent ledgers.

The circulation/cycle argument is the standard foundation of
[negative-cycle cancellation](https://courses.csail.mit.edu/6.854/21/Notes/n10-mincostflow.html).
The marginal-cost inequality above supplies the extension to our signed absolute
debt objective.

## A competing-loop counterexample to the current acceptance rule

All arrows below represent one unit of debt, with broad fixed comfort zones,
fixed hard bounds and assistance opt-in. There are six nodes and seven trustlines:

```text
Shared path:   A -> B -> C
Short return:  C -> D -> A
Long return:   C -> E -> F -> A
```

Initial gross debt is 7. Clearing the four-edge short loop leaves the three-edge
long return, gross debt 3. Clearing the five-edge long loop instead leaves the
two-edge short return, gross debt 2. Two is optimal: the remaining net obligation
is one unit from C to A, and the shortest physical C-to-A path has two edges.

From the short-first result, an improving residual loop can clear the three
remaining debt edges and recreate two previously cleared edges, saving one unit.
There are two such simple improving cycles, using the path through B or through D.
Both require the middle helper to increase its local absolute exposure by two.
The present `private-local-nonexpansion-v1` policy rejects both. No ordinary debt
cycle remains. Thus even unlimited fair search cannot repair this choice under
that policy, although all comfort settings remain fixed.

There is also a sequence-wide invariant: after the short loop clears, B and D
both have zero total incident absolute exposure. Local nonexpansion keeps that
exposure zero forever during subsequent clearing. Every optimal ledger must use
one of these two intermediaries, so no allowed sequence of moves, of any amount,
can reach the optimum from this state. New external transactions would change
this argument; the convergence claim concerns fixed net positions and clearing.

The independent offline checker
[`mdg2/check_convergence_counterexample.py`](mdg2/check_convergence_counterexample.py)
enumerates all `3^7` ledgers with edge bounds `[-1,1]` and the same net positions,
and all simple unit residual cycles at the trapped state. It is a mathematical
diagnostic, never an input to node decisions.

## Remaining protocol obligations

The theorem requires aggregate-improving moves even when a helper's local exposure
increases. The current local nonexpansion rule must therefore be replaced or the
claimed optimum restricted; simply renaming it does not solve the counterexample.
Permission to move within limits and actual authorization must be specified.

The nodes must establish aggregate benefit without requiring remote identities,
a route, membership size or recoverable exact loop length. Sending a plain sum
of marginal costs can expose length in special cases, so the theorem is not a
privacy protocol. A privately verified improvement predicate, complete local
search and fair conflict resolution remain design/proof work. Hashlocks enforce
conditional fulfillment; they do not by themselves establish those properties.

Concurrent completed operations must be economically serializable for the proof
to apply to settled states. Discovery may overlap; revalidation and reservations
must prevent invalidated cycle quotes from being used. There is no requirement
for a network-wide scheduler or a globally informed participant.

With continuing external transactions, `b` changes and a fixed terminal optimum
need not exist. Convergence after arrivals stop, and tracking performance while
they continue, are separate claims. Proving eventual global optimality also does
not automatically give each node a certificate that the entire network is done.
