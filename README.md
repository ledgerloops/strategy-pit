# LedgerLoops Strategy Pit

**Animal strategies for neighbour-to-neighbour clearing.**

Can we find loops of debt and clear them by talking to our neighbours? This is our workbench: small creatures, awkward graphs, messages crossing in flight, and experiments we can learn from together.

The rule for a **node-local algorithm** is simple: each node makes decisions from its own balances and state, plus messages exchanged with its direct neighbours. No participant gets a bird’s-eye view of the credit graph. Finding a loop, agreeing how much to clear, and completing the settlement are separate problems.

## Research issues

The [issue tracker in `docs/issues/`](docs/issues/README.md) records proposals, experiments and open questions. Start with [Headroom Clearing](docs/issues/001-headroom-clearing.md): reusing cleared capacity without exceeding the original debt on any link.

## From research to real use

The [product roadmap](docs/product-roadmap.md) proposes a community clearing assistant, a durable peer protocol, and staged pilots with explicit release gates. The next milestone is a three-node crash-recovery testnet alongside a read-only user demo.

The [component PRDs and interactive wireframes](docs/product/README.md) turn that roadmap into draft requirements and phone/desktop flows.

## Run the network app

The [runnable testnet app](app/README.md) connects a responsive web client to three independent SQLite-backed peer nodes. Try manual clearing approvals, receipts and restart recovery using fabricated TEST units. See [network validation](app/TESTING.md) and the [phone screenshot](app/screenshots/mobile.png).

## Meet the animals

These are research prototypes from several generations. Early animals explored loop discovery and message ordering; later ones attempted negotiation and settlement. Their descriptions explain what we learned, rather than establish a performance ranking. The historical source links point to the last snapshot before the older implementations were removed.

| Animal | What it explores |
| --- | --- |
| <img src="img/salmon.png" width="100" alt="Salmon illustration"> | <a id="salmon"></a>**[Salmon](https://github.com/ledgerloops/strategy-pit/blob/e36c0ed/src/salmon.ts)** floods probes and recognises a returning probe as evidence of a loop. A starting point that exposes the trouble with overlapping loops and notifications escaping into unrelated branches. |
| <img src="img/pelican.png" width="100" alt="Pelican illustration"> | <a id="pelican"></a>**[Pelican](https://github.com/ledgerloops/strategy-pit/blob/e36c0ed/src/pelican.ts)** gives branching discoveries separate identities. Suppressing old probes can still hide opportunities when a new neighbour arrives. |
| <img src="img/petrogale.png" width="100" alt="Petrogale illustration"> | <a id="petrogale"></a>**[Petrogale](https://github.com/ledgerloops/strategy-pit/blob/e36c0ed/src/petrogale.ts)** replays existing probes to new neighbours. A useful lesson for growing networks, at the cost of more duplicate discoveries and messages. |
| <img src="img/stingray.png" width="100" alt="Stingray illustration"> | <a id="stingray"></a>**[Stingray](https://github.com/ledgerloops/strategy-pit/blob/e36c0ed/src/stingray.ts)** remembers probe routes and traces backwards to reconstruct loops. Additional pinned probes help where paths meet; crossing messages still make ordering difficult. |
| <img src="img/jackal.png" width="100" alt="Jackal illustration"> | <a id="jackal"></a>**[Jackal](https://github.com/ledgerloops/strategy-pit/blob/e36c0ed/src/jackal.ts)** pauses a neighbour’s responses while sending a batch of probes. It tackles discovery races, but depends on ordered messages and successful pause/resume operation. |
| <img src="img/squid.png" width="100" alt="Squid illustration"> | <a id="squid"></a>**[Squid](https://github.com/ledgerloops/strategy-pit/blob/e36c0ed/src/squid.ts)** alternates which neighbour may send. Local turn-taking makes coordination more systematic, while introducing its own liveness questions. |
| <img src="img/butterfly.png" width="100" alt="Butterfly illustration"> | <a id="butterfly"></a>**[Butterfly](https://github.com/ledgerloops/strategy-pit/blob/e36c0ed/src/butterfly.ts)** combines probe-exchange handshakes, pinned probes and reverse traces. It explores concurrent discovery with more explicit bookkeeping; some trace handling still assumes restrictive path structures. |
| <img src="img/giraffe.png" width="100" alt="Giraffe illustration"> | <a id="giraffe"></a>**[Giraffe](https://github.com/ledgerloops/strategy-pit/blob/e36c0ed/src/giraffe.ts)** handles harder cycle shapes with multi-leg traces, then adds exchange rates and proposal/commit negotiation. Separating discovery from settlement is a lasting contribution; the financial accounting remains preliminary. |
| <img src="img/saiga.png" width="100" alt="Saiga illustration"> | <a id="saiga"></a>**[Saiga](https://github.com/ledgerloops/strategy-pit/blob/e36c0ed/src/saiga.ts)** fixes exchange rates at one and removes Giraffe’s intermediary profit haircut. It fits a common-unit model, but still needs an explicit debt-reduction objective and full settlement accounting. |
| <img src="img/badger.png" width="100" alt="Badger illustration"> | <a id="badger"></a>**[Badger](https://github.com/ledgerloops/strategy-pit/blob/e36c0ed/src/badger.ts)** proposed majority-based, all-or-nothing finality. That direction remained unfinished: in this snapshot its implementation matches Saiga apart from the class name. |

The [historical README](https://github.com/ledgerloops/strategy-pit/blob/e36c0ed/README.md), [discovery protocol notes](https://github.com/ledgerloops/strategy-pit/blob/e36c0ed/DLD.md) and [lift-resolution notes](https://github.com/ledgerloops/strategy-pit/blob/e36c0ed/Lift-Resolution.md) preserve the longer explanations, including early ideas about trustlines and participant preferences.

### Jerboa

[Jerboa has its own repository](https://github.com/ledgerloops/jerboa). It brings neighbour messaging, probe/backtrack discovery, amount scouting and hashlock proposal/commit messages together with actual balance updates. It is an important settlement prototype. Its historical **50k Sarafu fixture** results report **15.3%** clearing, against **16.6%** for DFS and **18.9%** for MCF. These are a different input from the full Sarafu benchmark. June 2025 code removed the central semaphore still described in the README; those older measurements do not establish the revised concurrency design’s guarantees.

### Jaribu

[Jaribu also has its own repository](https://github.com/ledgerloops/jaribu). Multiple search worms claim visited nodes and stop on collisions. It is a useful experiment in contention; the implementation uses a shared global graph and controller, so it does not yet meet the node-local rule above.

### Numbat

[Numbat](experiments/numbat.py) is a new node-local experiment: sample outgoing links with a bias towards available capacity, carry observed bottlenecks along the search path, then recheck and reserve capacity before clearing a loop. Local retries let it revisit a changing network. It inherits the [distributed simulator’s assumptions and limits](experiments/README.md#assumptions-and-limits), including reliable delivery and no crashes.

[Held-out results and reproduction instructions](experiments/NUMBAT.md) show gains over our earlier node-local DFS variants in the larger synthetic cases, while largest-first remains stronger on average in the small cases. On the [shared 50k Sarafu comparison](experiments/ANIMAL-COMPARISON.md), it trails historical Jerboa and Jaribu in achieved clearing. Numbat remains provisional and does not guarantee optimal clearing.

New [timestamped experiments](experiments/TEMPORAL-RESULTS.md) add dropped messages and sleeping peers; [local turn-taking](experiments/TEMPORAL-TURNS.md) has generally added cost in the tested workloads. A [Headroom postpass](experiments/HEADROOM.md) improves static Numbat clearing, but currently requires serialized initiation and retained zero-balance channels. These models have different assumptions and do not establish one universal winner.

## Try the experiments

- [DFS, neighbour-message protocols and continuously growing graphs](experiments/README.md): reproducible runs, measured results and independent settlement checks.
- [Trustlines and moving debt](experiments/TRUSTLINES.md): signed balances, credit limits, loop adjustments and optimization references.
- [The bird’s-eye worm and Sarafu benchmarks](docs/worm-and-benchmarks.md): centralized DFS, minimum-cost flow, dataset construction and solution formats.

The worm and MCF are useful reference points for measuring our animals. Their graph-wide access is part of the benchmark, not something a node-local contestant may use.

## Older benchmark links

The detailed benchmark documentation has moved. These anchors keep links from earlier discussions useful.

<a id="reproducible-dfs-and-streaming-experiments"></a>
[Reproducible DFS and streaming experiments](experiments/README.md)

<a id="sarafu-based-netting-challenge"></a>
[Sarafu-Based Netting Challenge](docs/worm-and-benchmarks.md#sarafu-based-netting-challenge)

<a id="full-run"></a>
[Full Run](docs/worm-and-benchmarks.md#full-run)

<a id="input-data"></a>
[Input data](docs/worm-and-benchmarks.md#input-data)

<a id="debt-graph-construction"></a>
[Debt Graph Construction](docs/worm-and-benchmarks.md#debt-graph-construction)

<a id="initial-analysis"></a>
[Initial analysis](docs/worm-and-benchmarks.md#initial-analysis)

<a id="solution-format"></a>
[Solution Format](docs/worm-and-benchmarks.md#solution-format)

<a id="solution-analysis"></a>
[Solution Analysis](docs/worm-and-benchmarks.md#solution-analysis)

<a id="contestants"></a>
[Centralized reference contestants](docs/worm-and-benchmarks.md#centralized-reference-algorithms)

<a id="depth-first-search-dfs"></a>
[Depth First Search ('DFS')](docs/worm-and-benchmarks.md#depth-first-search-dfs)

<a id="mcfdfs"></a>
[MCF+DFS](docs/worm-and-benchmarks.md#mcfdfs)

<a id="one-loop-check"></a>
[One-loop check](docs/worm-and-benchmarks.md#historical-one-loop-debugging)
