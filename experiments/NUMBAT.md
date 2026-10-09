# Numbat: capacity-weighted neighbour search

[Back to the animals](../README.md#numbat)

Numbat is an endangered Australian marsupial, and here a node-local clearing prototype. Each participant chooses using only its outgoing balances, reservations and received messages. Every message travels to a direct neighbour. The simulator has a complete graph for delivery and auditing; the algorithm does not inspect it or call an optimizer.

## What the prototype does

1. Local timers start bounded DFS searches. A node samples eligible outgoing links without replacement, weighting each by its currently available capacity raised to the fourth power. Large links are favoured, but alternatives remain possible.
2. The search token carries its path, visited nodes and capacities observed at each step. When it closes a cycle, those observations provide an initial bottleneck estimate.
3. A prepare message visits the participants, each of which checks its current capacity and reserves an amount. Stale observations never authorize an overdraft. Starting with the observed bottleneck reduces unnecessary provisional reservations on larger edges.
4. A commit lap clears the agreed amount. Local retries start fresh searches, including after new links and transfers arrive.

The implementation is [numbat.py](numbat.py), layered on [distributed.py](distributed.py). It inherits reliable exactly-once delivery, honest nodes and no crashes. Commit is not instantaneously atomic: conservation is checked after in-flight settlements finish. It models debtor-owned outgoing obligations, not replicated bilateral ledgers. Tokens disclose paths and capacities; this is not a privacy protocol. Signed trustline moves are a separate experiment and are not implemented here.

The capacity exponent of four was selected using training seeds **101 and 102**, then frozen before evaluating seeds **0, 1 and 2**. [Training records](results/numbat-training.json) retain the explored configurations. This is an empirical heuristic with no optimality or finite-time completeness guarantee.

## Held-out synthetic results

We reused the existing 80 graph/arrival/delay cases, verifying baseline source and input hashes. Every Numbat result was independently replayed against arrivals, checked for balance and net-position conservation, and compared with the drained simulator ledger. The same search and observation horizons apply to all methods.

Scores below are **mean percentages of each case's hindsight MCF clearing**, not percentages of initial debt. Hindsight MCF has access to the entire stream and is only a scoring reference.

| Graph size | Cases | Local random DFS | Local largest-first DFS | Numbat |
| --- | ---: | ---: | ---: | ---: |
| 24 nodes | 72 | 82.05% | **84.87%** | 82.69% |
| 72 nodes | 6 | 76.95% | 71.28% | **83.39%** |
| 300 nodes | 2 | 50.35% | 28.32% | **72.19%** |

Numbat improves the larger cases, where competing searches were a particular weakness. It does not dominate: largest-first is better on average in the small cases. Two 300-node cases are promising evidence, not a broad scalability claim.

| 300-node case | Random / largest / Numbat score | Random / largest / Numbat messages |
| --- | --- | --- |
| Sparse, steady arrivals | 62.52% / 37.14% / **72.62%** | 136,174 / 135,100 / 138,018 |
| Community, burst arrivals | 38.18% / 19.50% / **71.77%** | 138,888 / 135,950 / 137,238 |

Numbat also reduces integrated outstanding debt in both of those cases. Its payload includes additional capacity observations, so similar message counts do not imply identical bandwidth. The results report transmitted node identifiers and capacity-value counts separately; neither is an encoded byte measurement.

A second comparison stops admitting new searches when each method reaches a common message threshold, then drains in-flight work. Actual totals can exceed the threshold by different amounts. These are admission cutoffs, **not strict equal-message budgets**. The group scores are essentially unchanged, and the JSON reports each overshoot explicitly.

## Reproduce and inspect

From the repository root, using the optional OR-Tools environment described in the [research README](README.md):

```sh
python3 -m unittest discover -s experiments -p 'test_*.py' -v
python3 experiments/numbat_benchmark.py --output /tmp/numbat-heldout.json
```

The second command reuses checked-in baseline scores only when their source and regenerated input hashes match. It needs no optimizer during algorithm execution. [Held-out results](results/numbat-heldout.json) contain the full 80-case matrix, configuration, source hashes and audit metrics. Independent locality tests run nodes behind a facade that denies access to other nodes and the global graph. Adversarial tests cover competing reservations, replenishment, newly arriving neighbours and hop-limit failures.

## Comparison with Jerboa

We have not established that Numbat beats Jerboa. Jerboa's README reports 15.3% clearing against 16.6% centralized DFS and an 18.9% MCF optimum on its historical 50k Sarafu fixture. Those percentages use a different input and denominator from the table above. A direct comparison requires pinned implementations, identical obligations and declared time/message budgets.

Numbat's useful contribution so far is a measured improvement on several larger synthetic cases while keeping decisions node-local. It remains greedy: earlier settlements can block better later choices, and finite searches may leave discoverable cycles.
