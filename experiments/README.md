# DFS research: static clearing, local messages, and growing graphs

These are reproducible research experiments, separate from the existing TypeScript implementation. They test a simple DFS improvement and a distributed variant where each node makes decisions using its own outgoing obligations and messages from neighbors. They are **not production settlement software**.

## Numbat

The [Numbat study](NUMBAT.md) tests capacity-weighted node-local search and observed bottleneck proposals against the same 80 synthetic cases, with separate training seeds and independently audited results. It improves the larger cases but does not dominate the small ones.

## Headroom Clearing

[Headroom experiments](HEADROOM.md) test restoring previously cleared debt within original limits. They validate the model and improve a Numbat postpass on the 50k fixture, while exposing weak cold-start performance and the need for local concurrency and channel-reopening rules.

## Timestamped arrivals, loss and sleeping nodes

[Temporal results](TEMPORAL-RESULTS.md) compare continuous transfers with unreliable messages and state-retaining sleep, including actual [Sarafu timestamps](TEMPORAL-SARAFU.md). [Neighbour-turn experiments](TEMPORAL-TURNS.md) test genuine endpoint-local turn ownership separately from a centralized transport reference. These experiments use stricter zero-balance channel closure than the earlier streaming simulations below.

## Strict channel episodes and temporal Headroom

[Episode admission](TEMPORAL-EPISODES.md) rejects search and preparation messages from closed or revised relationships while allowing admitted settlement cleanup. The [matched fault study](TEMPORAL-EPISODES-RESULTS.md) includes delayed-input and staged-commit exposure. [Temporal Headroom](TEMPORAL-HEADROOM.md) first tests cap updates and zero closure under explicitly serialized scheduling; [Concurrent Headroom](CONCURRENT-HEADROOM.md) now implements signed residual discovery with endpoint-local pair locks, but its first matched comparison regresses in aggregate.

[Full-prefix seed replication](TEMPORAL-EPISODE-REPLICATION.md) repeats the fixed strict random DFS/Numbat comparison on seeds 1 and 2, using a bounded three-worker campaign and unchanged policies. Inspect the linked state before interpreting its progress.

The [backoff trial](TEMPORAL-BACKOFF-RESULTS.md) and [episode-only admission trial](TEMPORAL-EPISODE-ONLY-RESULTS.md) retain failed promotion decisions alongside their clearing gains and posting-delay costs. The latter is cancellation-only; it does not establish consent rules for restoration. [Rank-weighted Numbat](TEMPORAL-RANK-RESULTS.md) also failed its training gate, trading slightly more remaining debt for fewer messages.

## Signed trustline extension

The [trustline study](TRUSTLINES.md) adds bilateral balance limits, exact cycle moves that may increase some debts, an alternating-credit ratchet, and comparison with a global convex-flow optimum. This model is separate from the asynchronous distributed prototype below.

## Run it

Python 3.10+ is sufficient for the DFS and distributed simulations. The MCF reference additionally uses OR-Tools; the checked-in optional environment was tested with Python 3.12. From the repository root:

```sh
python3 -m venv experiments/.venv
experiments/.venv/bin/pip install -r experiments/requirements-mcf.txt
experiments/.venv/bin/python -m unittest discover -s experiments -p 'test_*.py' -v
experiments/.venv/bin/python experiments/dfs_benchmark.py --seeds 20 --mcf
experiments/.venv/bin/python experiments/simulate.py --mcf
```

Without the optional solver, omit `--mcf` and use your Python interpreter directly. The solver-specific unit check will then be reported as skipped. Static experiments read pinned fixtures from Git, so run them in a checkout containing commit `06c6a2fb5702c7066ded7cf14672ba07ed5098c4` (fetch full history if using a shallow clone).

Output defaults to `experiments/results/sarafu.json` and `experiments/results/distributed-synthetic.json`. These commands overwrite those result files. Use `--output /tmp/my-run.json` to preserve the checked-in results. Results record input/source hashes, seeds and configurations. Static output is marked incomplete until every requested run and baseline comparison finishes; do not treat interrupted output as a completed study.

The TypeScript baseline can also be rerun without its CLI's hard-coded long-loop debug check:

```sh
# Activate Node 20.10.0, as pinned in package.json, first.
npm ci
npm run build
node experiments/original-dfs.mjs debt.csv /tmp/original-dfs.csv
```

This wrapper invokes the unmodified `BirdsEyeWorm`. It does not remove its one-million-step limit; validate the resulting cycles and residual before interpreting another dataset. The legacy algorithm prunes search edges, so its final in-memory graph is not the residual obligation ledger.

## Static Sarafu experiment

Input: the historical, bilaterally netted graph at the pinned October 2024 commit: **94,223 edges**, total obligation weight **107,886,628.824**. This is the project's fictitious debt graph derived from real transfers, not a record of actual unpaid Sarafu debts. Amounts use integers scaled by 1,000.

A fresh execution of the original TypeScript implementation produced **the same entire cycle sequence** as the numeric-order Python baseline: 27,106 valid cycles and 60.346642% cleared. A fresh OR-Tools optimization reproduced the historical 67.3595% reference clearing. The optimizer can choose a different cycle decomposition with the same objective.

| Search policy | Debt cleared | Cycles | Total cycle hops |
| --- | ---: | ---: | ---: |
| Original numeric-order DFS | 60.3466% | 27,106 | 315,230 |
| Largest current outgoing balance first | **63.7765%** | **15,724** | **145,641** |
| Smallest current outgoing balance first | 60.6327% | 33,534 | 553,187 |
| Randomly relabeled DFS, mean of 20 seeds | 61.6390% | 28,354.55 | 374,686.55 |
| Largest first with random roots/ties, mean of 20 seeds | 63.7734% | 15,670.55 | 145,584.15 |
| Fresh MCF reference, decomposed into cycles | 67.3595% | 32,594 | 507,601 |

Largest-first gains **3.43 percentage points** over the original and reaches about **94.68% of the MCF clearing**. Its advantage survives the tested relabelings: 63.6980–63.8217%, compared with 61.1107–62.1935% for ordinary DFS under relabeling. This is evidence on one graph, not a general approximation guarantee. Root order, tie-breaking and capacities can affect results.

The improvement is deliberately small: at the current node choose the outgoing edge with the largest *remaining* capacity. On this graph it avoids many low-value cycle cancellations. The benchmark measures that outcome; it does not prove this explanation is the only cause or that the rule always helps.

Cycle-hop counts are sums of cycle lengths, **not measured network messages**. They omit discovery, failed searches, reservations, retries, and message payload. Fewer cycles/hops could reduce coordination work, but only the distributed experiments measure that work. MCF optimizes remaining edge-weight debt, not the number or length of cycles, so its decomposition's hop count is not a lower bound.

### Long loops still matter

For the original DFS, cycles of length at most 10 account for about **66.67% of cleared weight**; length at most 20 accounts for **87.13%**. Largest-first has almost identical shares (66.83% and 87.39%). Its longest cycle is **81**, compared with **70** for the original.

These distributions do **not** say a length-10-limited search would clear exactly two-thirds as much: changing the constraint changes which other loops remain available. A practical length cap needs its own search experiment. The distributed simulator supports a hop cap, and a test demonstrates that too-small a cap can leave a ring uncleared.

### Why MCF is the reference

`mcf_reference` minimizes retained flow on the original edges, with unit edge costs, original capacities, and exactly the original net positions. Subtracting that retained flow leaves a circulation. DFS decomposes that circulation into cycles and checks that it is completely exhausted. It does not improve the MCF optimum; it expresses the optimizer's result as executable cycle cancellations.

The harness checks this formulation against exhaustive enumeration on small integer graphs. Every reported solution is independently replayed, rejects absent edges/repeated nodes/nonpositive amounts/overdrafts, preserves every net position, and has its residual checked for cycles. An acyclic residual certifies **maximal** greedy clearing, not **maximum** total clearing.

The current repository's saved MCF CSV was changed after the published benchmark. The study therefore pins the historical graph and both historical solutions together instead of combining the README's 67% claim with today's mismatched artifacts.

## Distributed DFS model

`distributed.py` implements concurrent searches and settlement coordination. A node owns only its outgoing balances and reservations. It does not inspect another node or ask the simulator to find a cycle.

1. Local randomized timers start DFS tokens. Tokens carry a path and visited-node set. Forward steps follow positive local outgoing capacity; backtracking follows existing neighbor channels.
2. On closing a cycle, a prepare message visits its participants. Each reserves locally available capacity; later participants can reduce the proposed amount. A conflicting proposal fails immediately and releases earlier reservations.
3. Once all participants have prepared, a commit message travels around the cycle. Each node reduces its owned outgoing balance and releases its reservation. A completion message unwinds the original search path.
4. Nodes retry periodically. Old dead-end information is per-search, so newly added links can be discovered later. The protocol never deletes an obligation just because a search cannot use it.

Policies are randomized neighbor order and largest locally available outgoing capacity first with randomized ties. The scheduler delivers messages at seeded bounded delays, so searches interleave and messages from different searches can arrive in different orders. Scheduler access to all nodes is for delivery and instrumentation, not search/settlement decisions. A global cutoff stops new work for measurement; it is not a distributed termination detector.

### Assumptions and limits

- Honest nodes, **reliable exactly-once delivery**, finite bounded delays, no crashes or partitions. Duplicate/lost-message recovery is not implemented.
- An obligation creates a bidirectional acquaintance channel for control messages. That channel persists after the debt is cleared, allowing backtracking and commit completion.
- Only the debtor node owns the modeled edge balance. This is not yet replicated bilateral accounting with two independently signed ledgers.
- Reservations avoid capacity races under the model, but the commit lap is **not instantaneously atomic**. Individual net positions can change temporarily while a transaction is in flight. Safety reports compare completed settlements after draining; crash recovery or compensation would require another protocol layer.
- Tokens disclose paths and visited nodes. Payload grows with search history. Recorded node-ID counts are a payload-size proxy, not byte sizes or a privacy guarantee.
- Searches are bounded; retry windows are finite. There is no guarantee every possible loop will clear before a deadline, nor of maximum clearing.
- The simulator accepts reciprocal edges but does not clear 2-cycles. Generated comparisons use a fixed orientation per pair to avoid mixing bilateral netting into this experiment.

A tiny growing network can be run without OR-Tools:

```sh
PYTHONPATH=experiments python3 - <<'PY'
from distributed import DistributedDFS
sim = DistributedDFS(seed=7, max_delay=5)
sim.add_edge('a', 'b', 12, at=0)
sim.add_edge('b', 'c', 9, at=100)
sim.add_edge('c', 'a', 6, at=300)
sim.add_edge('c', 'a', 2, at=600)
sim.run(until=2000)
sim.stop_searches()
sim.drain()
print(sim.cycles)
print(sim.graph_snapshot())
print(dict(sim.metrics))
PY
```

## Streaming simulation methodology

`simulate.py` generates seeded **synthetic** streams on sparse, dense, community, and disconnected graphs. Each topology is tested with all-at-once, steady, and burst arrivals. Repeated arrivals increase existing obligations; first arrivals introduce new links and may introduce nodes. It is not a chronological replay of Sarafu transactions.

All methods receive exactly the same additions. Online centralized DFS runs every 50 ticks; distributed nodes see arrivals and messages locally. Hindsight DFS/MCF receive the whole accumulated graph and are explicitly labeled as hindsight references. They have information and synchronization unavailable to the distributed algorithms.

Discovery runs through the last arrival plus 1,500 quiet ticks. Distributed in-flight work is then drained; all debt-area calculations use a common later observation horizon. A long quiet suffix can conceal responsiveness during arrivals, so compare **integrated outstanding obligation weight over time** as well as final clearing. The normalized debt-area metric includes obligations still unpaid at the horizon; it is not the mean latency of the settled subset. Transaction duration measures proposal-to-completion, not time since the underlying obligation arrived.

Every case independently replays complete settlements against obligations that existed at the settlement time. It checks capacities, net positions, final simulator balances, and drained reservations. Message counts include failed attempts and retries. Cyclic residuals are reported as remaining opportunities, not silently treated as a finished maximal solution.

## Distributed and streaming results

The checked-in matrix contains **80 graph/arrival/scheduler cases**, with seven methods per case, including **160 distributed simulations**. The principal matrix has 24 nodes, 12 topology/arrival combinations, three seeds and delays of 1 or up to 7 ticks. Six cases scale to 72 nodes; two scale to 300. These are small, finite simulations, not evidence of Internet-scale operation.

The following table reports **clearing as a percentage of each case’s hindsight MCF clearing**, averaged across the 24-node cases in each arrival category. These percentages use a different denominator from the Sarafu table above.

| Arrivals | Distributed random | Distributed largest | Periodic centralized DFS | Periodic largest |
| --- | ---: | ---: | ---: | ---: |
| Static | 80.58% | 86.72% | 84.16% | 87.10% |
| Steady | 82.75% | 83.72% | 84.62% | 82.97% |
| Burst | 82.82% | 84.19% | 85.21% | 82.97% |

The static capacity-first improvement does **not** transfer uniformly to an online or distributed setting. Even the centralized periodic largest-first baseline underperforms ordinary periodic DFS on these steady/burst cases. Early cancellations change future opportunities.

Higher delay and larger graphs expose the prototype’s throughput limit. With 72 nodes and dense steady arrivals, random distributed search achieves 91.06% of hindsight MCF at one-tick delays, but only 48.85% when delays range up to 15 ticks. Largest-first reaches 86.08% and 31.58%, respectively. Under the same finite observation window, a longer message round trip gives searches fewer chances to finish.

| 300-node synthetic stream, delays up to 7 ticks | Distributed random | Distributed largest | Periodic DFS | Periodic largest |
| --- | ---: | ---: | ---: | ---: |
| Sparse steady: 3,004 links, 7,541 additions | 62.52% | 37.14% | 88.83% | 90.00% |
| Community bursts: 8,786 links, 21,994 additions | 38.18% | 19.50% | 92.18% | 94.34% |

All four 300-node distributed runs leave cyclic residuals: they have remaining clearing opportunities after their discovery cutoff. Each sends about 135,000–139,000 messages. Largest-first also has substantially more failed reservations (2,064 versus 1,019 on sparse steady; 2,181 versus 346 on community bursts). That is consistent with searches competing for the same high-capacity links; a controlled experiment is needed to separate contention from traversal choices and timing.

Every completed run passed independent arrival-time, capacity, conservation and final-state checks and drained its reservations. This means safe completion **under the simulator’s delivery assumptions**, not that the run reached maximum or even maximal clearing. The data retains acyclicity and remaining-opportunity metrics for that reason.

Reproduce the larger cases:

```sh
experiments/.venv/bin/python experiments/simulate.py --mcf --nodes 72 --seeds 0 \
  --scenarios sparse-steady dense-steady community-burst --delays 1 15 \
  --output experiments/results/distributed-scale.json
experiments/.venv/bin/python experiments/simulate.py --mcf --nodes 300 --seeds 0 \
  --scenarios sparse-steady community-burst --delays 7 \
  --output experiments/results/distributed-scale300.json
```

### What to investigate next

1. **Contention-aware exploration:** mix capacity preference with randomized alternatives and local backoff, rather than having every search prefer the same bottleneck. Measure completion rate and failed reservations at equal message/time budgets.
2. **Rate and delay sweeps:** vary arrival rate, retry interval, message delay and the quiet suffix separately. Current larger cases change graph size at fixed time budgets; they identify a limit but do not locate a stable throughput frontier.
3. **Bounded paths and token sizes:** compare useful clearing per transmitted node identifier and transaction completion time. Do not optimize only debt percentage.
4. **Real temporal replay:** obtain the original transaction sequence under its access conditions and specify how transactions become obligations. Synthetic streams cannot establish that the same behavior holds over historical Sarafu time.
5. **Protocol hardening:** replicated bilateral agreement, duplicate handling, recovery after crashes/partitions, and privacy need explicit designs before deployment. The current reservation/commit experiment is not a substitute for them.

## Files and validation

- `dfs_benchmark.py`: pinned static benchmark, strict independent replay, MCF reference and DFS variants.
- `original-dfs.mjs`: wrapper for rerunning the unmodified TypeScript baseline.
- `distributed.py`: local-state actors and neighbor-message scheduler.
- `simulate.py`: synthetic arrival streams, common comparison metrics and independent auditing.
- `test_*.py`: deterministic and randomized correctness/adversarial tests, including new links after dead ends, competing reservations, replenishment during settlement, partial commits and hop limits.
- `results/*.json`: full configurations, source/input hashes and measured outputs. Timings are single-machine observations and not comparable between the Python and TypeScript implementations.

The static tests also include a small graph where greedy cycle cancellation gets stuck below the exhaustive optimum. Safety, termination of a finite run, maximality, optimum clearing, privacy and fault tolerance are separate properties; passing one check does not establish the others.

[Temporal metric definitions](TEMPORAL-METRICS.md) explain gross cycle clearing
versus final debt improvement, deadline versus drained results, and proposed
amount-weighted posting and partial-settlement exposure measurements.
