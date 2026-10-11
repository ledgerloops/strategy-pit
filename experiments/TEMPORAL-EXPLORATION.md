# Temporal Numbat: uniform exploration mixture

The fixed 50/50 mixture **did not pass its prospective training gate**. No held-out or Sarafu runs were performed, and the original Numbat policy remains unchanged.

At each search step, a local coin chooses either uniform neighbour ordering or the original power-four capacity ordering. Path capacity hints, loop discovery, reservations, settlement, reliable transport and external posting retain the existing behavior. This was one predefined policy, not a parameter sweep.

## Training design

Twelve matched cases use seeds 101/102, 24-node sparse/community/burst transfer streams, clean transport or 30% packet loss plus retained-state sleep, and three methods: original Numbat, mixture, and uniform random DFS. Every method receives the same arrivals and sleep schedule, an 800-tick horizon, hop limit 32, search budget 96, retry interval 50, delay bound 5 and retransmit interval 20, followed by drain.

Shared seeds do not imply identical packet-loss realizations when the algorithms generate different traffic. These comparisons share horizons and resource rules, not exact message budgets. All outcomes pass independent chronological per-edge ledger replay; cutoff backlog and eventual drain costs remain visible.

Before training, the advancement rule required lower aggregate posted-ledger debt area, no increase in final debt, no more than 110% of Numbat wire attempts, and no increase in cutoff unposted inputs. Held-out seeds 0/1 were to run only if all four conditions passed.

## Aggregate results

| Metric | Numbat | 50/50 mixture | Uniform random |
| --- | ---: | ---: | ---: |
| Posted debt amount × ticks | 10,947,906,000 | 10,943,028,000 | 11,175,426,000 |
| Final debt, scaled units | 14,304,000 | 14,444,000 | 14,753,000 |
| Data + ACK attempts | 61,351 | 60,645 | 61,651 |
| Unposted transfers at cutoff | 0 | 2 | 3 |
| Total posting-delay ticks | 11,896 | 16,255 | 15,580 |

The mixture changes debt area by -0.0446%, final debt by +0.9787%, and wire attempts by -1.1508%. Its tiny area improvement comes with higher posting delay and two unposted transfers at cutoff versus none for Numbat. Delaying input must not be mistaken for clearing debt. The final-debt and backlog conditions fail.

## Every training case

Final debt in scaled units; lower is better:

| Topology | Seed | Loss / sleep | Numbat | Mixture | Random |
| --- | ---: | --- | ---: | ---: | ---: |
| sparse | 101 | 0% / no | 922,000 | 920,000 | 920,000 |
| sparse | 101 | 30% / yes | 934,000 | 917,000 | 893,000 |
| community | 101 | 0% / no | 819,000 | 838,000 | 862,000 |
| community | 101 | 30% / yes | 989,000 | 981,000 | 1,037,000 |
| bursts | 101 | 0% / no | 1,041,000 | 1,079,000 | 1,131,000 |
| bursts | 101 | 30% / yes | 1,531,000 | 1,628,000 | 1,687,000 |
| sparse | 102 | 0% / no | 1,259,000 | 1,259,000 | 1,264,000 |
| sparse | 102 | 30% / yes | 1,272,000 | 1,263,000 | 1,276,000 |
| community | 102 | 0% / no | 1,386,000 | 1,374,000 | 1,439,000 |
| community | 102 | 30% / yes | 1,485,000 | 1,464,000 | 1,469,000 |
| bursts | 102 | 0% / no | 1,156,000 | 1,151,000 | 1,153,000 |
| bursts | 102 | 30% / yes | 1,510,000 | 1,570,000 | 1,622,000 |

The mixture beats Numbat in several sparse/community cases but regresses on both lossy burst cases. Pure random also loses on this aggregate despite its stronger result in an earlier large Sarafu run. These small synthetic cases do not establish which policy is best across topology, scale, and timing regimes.

## Scope and reproducibility

Node-level tests deny access to the global graph and other-node state, exercise both mixture branches, and verify capacity hints, one-hop finish behavior, and loss/retry accounting. Four focused tests pass. External posting still uses the existing bilateral adapter. Sleep preserves state; crashes and malicious peers are excluded. Existing control-channel grace remains in force; this experiment does not implement the strict episode-admission proposal in issue 003.

```sh
PYTHONPATH=.:experiments python experiments/temporal_exploration_benchmark.py
PYTHONPATH=.:experiments python -m unittest experiments.test_temporal_exploration
```

[Complete results](results/temporal-exploration.json) retain all 36 training runs, source and arrival hashes, full metrics, audits, the declared gate, and the reason held-out evaluation was skipped. No baseline source or benchmark artifact was changed.
