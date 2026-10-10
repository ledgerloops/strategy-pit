# Numbat versus Jerboa and Jaribu

This comparison uses Jerboa's historical **50k Sarafu fixture**, not the full Sarafu graph used for the 67.36% MCF result. The question is whether the frozen Numbat prototype improves on the earlier animals. Numbat's exponent remains four; we did not tune it on this input.

## Shared input and scoring

The CSV contains 30,726 standard transfers among 7,154 participants. The unchanged Strategy Pit converter aggregates and bilaterally nets those transfers into **13,831 positive edges among 6,908 accounts**, with total obligation weight **7,434,585.295**. All percentages below are reductions in this post-bilateral debt weight. They exclude the bilateral netting already performed in constructing the input.

The native Jerboa loader buffers transfers before starting clearing. This is a batch-input comparison, not chronological transaction replay. Jaribu and Numbat receive the corresponding derived debt graph. Fresh centralized references on that graph give **16.614541%** for ordinary DFS, **16.483140%** for largest-first DFS and **18.921189%** for MCF.

Every exported settlement is independently replayed using integer milli-units. Jaribu and Numbat settlements must all pass capacity and net-position checks. Jerboa output is additionally scored using the historical convention of rejecting invalid proposals; its valid-subset scores are explicitly distinguished from a valid complete solution.

## Result: Numbat does not beat the earlier benchmarks here

| Algorithm/run | Initial debt cleared | Communication or completion notes |
| --- | ---: | --- |
| Numbat, one-million-message admission cutoff, three seeds | 13.4741–13.6880% | 1.58–1.65 million actual sends after draining |
| Numbat, five-million-message admission cutoff, three seeds | **13.4923–13.8154%** | 5.59–5.65 million actual sends after draining |
| Historical Jerboa, fresh native run | **15.3732%** | Valid subset of proposals; 345,215 sends including 30,726 input-transfer messages |
| Jaribu, 10ms launches, two seeds | **16.6145%** | All exported cycles valid; residual acyclic; upstream termination exception |
| Offline MCF optimum | **18.9212%** | Global information; reference only |

Even Numbat's best long run falls below both earlier results. Raising its admission cutoff from one to five million messages yields little additional clearing. All six Numbat runs complete independent ledger and conservation checks, but retain cyclic residuals: they are not proofs that no further improvement is possible. This is a negative result for the current frozen design on this fixture, despite its earlier gains on larger synthetic graphs.

Fresh historical Jerboa emits 1,176 proposed cycles. Five overdraw a link and are rejected by the independent auditor, leaving 1,171 accepted cycles and the score above. This reproduces the historical scoring convention rather than certifying the complete native settlement protocol. The saved historical solution similarly scores 15.3445% after rejecting five proposals. See [the Jerboa reproduction](compare_jerboa.md) for exact versions, rounding problems and message accounting.

The semaphore-free June Jerboa scores 2.8421% in its separate 180-second capped run. Numbat exceeds that observed score, but Jerboa's extremely sparse default probe timers and its unfinished run make it inappropriate to claim general superiority. Neither this result nor Jaribu's shared-graph score settles which fully node-local protocol is best under matched resources.

The next useful experiment is to reduce repeated unproductive exploration, especially revisiting dead ends. Any cached search information must be invalidated when links or balances change; permanently pruning debt would make a growing-network protocol incorrect. This is a proposed follow-up, not an implemented improvement or an established explanation for every loss.

## What was run

- **Numbat:** frozen `capacity_power=4`, observed bottleneck hints enabled, seeds 0/1/2. Delays up to five abstract ticks, retry interval 50, maximum path length 100 and search budget 256. Short runs stop admitting searches at one million messages or 2,000 ticks; long runs at five million messages or 15,000 ticks. Admitted work drains afterward, so actual message totals exceed these thresholds. Message checkpoints count completed cycles only, not partial commits.
- **Historical Jerboa:** README-era commit `69c7b2cb3cf6946742e676b4c50ff17bebfec059`, native challenge runner and 20 workers under Node 20.10.0. This revision uses a central semaphore. It does not inspect a global credit graph to choose routes, but its coordination is not wholly node-local.
- **Later Jerboa:** semaphore-free HEAD `c09ef8f7cb7ce0485cddb55d801a8ebe9ef0a4d1`, separately bounded at 180 seconds. Its very low probe-start probability means that a short score cannot characterize its eventual clearing.
- **Jaribu:** commit `06311d3c542f2f051a0690cc8d1706e62ae122ce`, unchanged algorithm under Node 22.12.0. A wrapper supplies the input and seeds random choices. Two seeds and three worm-launch intervals (1,000/100/10 ms) are reported, including incomplete runs. This version uses a shared global graph and ownership table: it is a quality reference, not an eligible node-local protocol.

Jaribu's best observed result in both seeds is **16.614541%**, matching ordinary DFS on this input. Its 1,312 completed cycles are all valid, and independent inspection finds an acyclic residual. Upstream then throws when trying to start another worm on the empty search graph. The termination error is retained in the logs; removed search edges are never counted as cleared debt. The slower launch intervals leave cycles after the built-in 90-second cutoff.

These implementations use different schedulers and stopping conditions. The experiment compares achieved clearing and reports resource usage; it does **not** establish equal-bandwidth or equal-walltime rankings. Jaribu's scheduler phases are not network messages. Several native runs occurred concurrently, so their walltimes are not a speed benchmark.

## Reproduce

Obtain Jerboa's fixture at the pinned version, build Strategy Pit with its pinned Node version, and run from the repository root:

```sh
node build/src/sarafu-to-debt.js /path/to/jerboa/__tests__/fixtures/sarafu-50k.csv /tmp/animal-50k-debt.csv /tmp/animal-50k-sources.csv /tmp/animal-50k-drains.csv 1000000
python experiments/compare_numbat.py /tmp/animal-50k-debt.csv --output /tmp/numbat-short.json
python experiments/compare_numbat.py /tmp/animal-50k-debt.csv --cutoff 5000000 --horizon 15000 --output /tmp/numbat-long.json
```

Use the Python environment with OR-Tools described in [the research README](README.md). It computes the offline reference only; Numbat never calls it for decisions. Source hashes, inputs, budgets and per-seed checkpoints are in the [short](results/animal-comparison-numbat.json) and [long](results/animal-comparison-numbat-long.json) result files. [Jaribu's reproduction notes](results/animal-comparison/jaribu/README.md) include its wrapper, raw cycles, logs and independent audit.
