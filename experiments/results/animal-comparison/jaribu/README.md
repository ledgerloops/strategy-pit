# Jaribu historical reproduction

Upstream commit: `06311d3c542f2f051a0690cc8d1706e62ae122ce`.

The pinned Node 22.12.0 trials use the unmodified `src/BirdsEyeWorm.ts` and
`src/BirdsEyeGraph.ts`. These two dependency-free files are transpiled with
TypeScript's `transpileModule` rather than running upstream lint/build. This
is not a claim that the upstream full build or test suite passes.

The supplied `benchmark.mjs` replaces only the old `dfs.ts` executable: it
accepts a debt-file path and output prefix, bypasses that executable's
hardcoded long-cycle precheck, controls `Math.random` with a seed, and saves
exit summaries. Probe IDs still use upstream `crypto.randomBytes`. Input
order is unchanged. The LCG uses `state=(1664525*state+1013904223) mod 2^32`.
Seed controls node choices, but timer/event-loop scheduling makes exact
reproduction nondeterministic. Seed 2 runs also count calls to work1/work2
using transparent wrappers; these are scheduler phases, not network messages.

Upstream itself starts new worms at a wall-clock interval, allows up to 100
runners and forces process exit at 90 seconds. The runs use intervals of
1000ms (upstream's last example invocation), 100ms and 10ms. Several jobs ran
concurrently: elapsed time is a run boundary, not a fair throughput comparison.

Jaribu keeps a shared graph and shared node-ownership table. It is not a
node-local implementation, and its steps cannot be compared with Numbat's
neighbour messages. It also removes dead-end edges from its search graph:
that is search pruning, not settled debt. `validate.py` independently replays
only exported closed simple cycles against the original graph, verifies all
capacities, and verifies exact conservation of every node's net balance.
Amounts use integer milli-units, matching upstream's LEDGER_SCALE=1000.

Run from a clone of Jaribu at the pinned commit, with the supplied scripts
copied to its root. `compile.mjs` currently references the installed Strategy
Pit TypeScript package at `/workspace/strategy-pit/node_modules/typescript`:

```sh
node compile.mjs
node benchmark.mjs 1000 /tmp/animal-50k-debt.csv /tmp/jaribu-run 1
python validate.py /tmp/animal-50k-debt.csv /tmp/jaribu-run
```

Files named `node22` are the primary trials. Other files are preliminary
Node24.19 runs and must not be mixed silently with the pinned-runtime results.
`code:0` denotes the upstream 90s forced exit, not proven completion.
`code:1` denotes an upstream exception; its completed exported cycles are
still validated and retained. Logs preserve the actual exception.
