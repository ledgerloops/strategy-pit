# Jerboa reproduction for the Numbat comparison

The historical 15.3% figure is reproduced by auditing the saved solution from
Jerboa commit `69c7b2cb3cf6946742e676b4c50ff17bebfec059` (2024-10-25).
Its solution file was last changed at `30dc2cc04e96b8eb66567828381f5af4cc22d215`.
This historical implementation uses a central semaphore to serialize probes.
The newer node-local revision `c09ef8f7cb7ce0485cddb55d801a8ebe9ef0a4d1`
(2025-06-06) is tested separately; its saved output cannot stand in for the old result.

## Dataset and scoring

Input: Jerboa `__tests__/fixtures/sarafu-50k.csv`, SHA-256
`785b8f57d3e7e485a678772727bf593aaa90594c833afb7abc3c4d5fb366eebb`.
It contains 30,726 STANDARD transfers between 7,154 participants. Strategy Pit's
`sarafu-to-debt.js` bilaterally nets these into 13,831 positive edges and 6,908
nonzero-balance participants, with total debt 7,434,585.295 Sarafu.

The saved historical solution contains 1,171 proposed cycles. Strict sequential
replay accepts 1,166 and rejects five. The accepted cycles clear 1,140,796.5 Sarafu,
**15.3444537218%** of initial debt, reproducing the README's rounded score.
This score uses the historical analyzer's skip-invalid policy; it does not imply
that every proposed settlement is valid. Every accepted cycle is checked against
current remaining balances and each participant's net position is preserved.

The five rejected cycles each overdraw one link by 0.3 Sarafu. One proposes 0.8
against 0.5; four propose 3,600 against 3,599.7. They advertise a combined
61,202.4 Sarafu of debt reduction, which is excluded from the score. The code
contains whole-unit rounding in `Jerboa.ts`'s returning scout handler, unlike its
other handlers' scaled rounding. We did not patch this or any protocol behavior.

The native challenge loads transfer records and queues their delivery before
search completion. This is not a benchmark of transfers scheduled over simulated
18-month wall time. All algorithms' scores here use the final bilaterally netted
static debt graph, not gross transfer volume.

## Reproduction

Use Node 20 (our run: v20.10.0), check out the exact Jerboa revision, and run:

```sh
npm ci --ignore-scripts
npm run build
NUM_WORKERS=20 timeout 600 node build/src/jerboaChallenge.js \
  __tests__/fixtures/sarafu-50k.csv /tmp/jerboa-oct-fresh.solution
```

The old program's own stopping rule is twelve seconds without a newly reported
loop. That is a progress heuristic, not a proof of exhaustion. The semaphore can
also impose a twenty-second timeout on a probe. `NUM_WORKERS=20` partitions node
ownership and changes message delivery interleaving; the simulator still runs in
one thread.

For the June revision, build the same way and run the same command with
`timeout 180` and a different output filename. Its own idle timeout is 300
seconds, so the external 180-second cap is a deliberately censored observation.
It starts probes with probability 0.0001 at eligible nodes' 5–10 second timers;
a short capped run is not a search-to-exhaustion result. No seed was forced.

Generate the scoring graph with Strategy Pit:

```sh
node build/src/sarafu-to-debt.js /path/to/jerboa/__tests__/fixtures/sarafu-50k.csv \
  /tmp/animal-50k-debt.csv /tmp/animal-50k-sources.csv /tmp/animal-50k-drains.csv 1000000
python experiments/compare_jerboa_audit.py /tmp/animal-50k-debt.csv \
  /tmp/jerboa-oct-fresh.solution
```

Native message counts count all Jerboa protocol sends, including initial transfer
messages. They are not automatically comparable with Numbat's search/settlement
message count. The complete native run reports sent and received totals; a killed
run may have unfinished messages and settlements and does not report final stats.
Neither wall time nor message budgets are matched by these native reproductions.

## Fresh historical result

The unmodified October program exited successfully after approximately 188.12
seconds (process lifetime measured to within 0.2 seconds). It reported 1,176
cycles; 1,171 pass strict replay and five are rejected. Accepted cycles clear
**15.3732381115%** (1,142,936.5 Sarafu). It reported 614 probes, 345,215 sent
and 345,214 received messages. Subtracting its 30,726 transfer messages gives
314,489 non-transfer sends. The one undelivered message at shutdown illustrates
that the idle stopping rule does not establish globally drained settlement.

The reported internal multilateral counter uses a different accounting basis and
is not our clearing score; the independent replay score above is the comparison.
Raw fresh/saved solutions and the native log are retained under
`results/animal-comparison/jerboa/`.

## Fresh June result

The unmodified semaphore-free June revision reached 297 proposed cycles before
an external 180-second timeout (exit 124; observed process lifetime 180.15 seconds).
296 cycles replay successfully, clearing **2.8421356621%** (211,301 Sarafu), and
one overdraw is rejected. This result is incomplete, is not an estimate of the
algorithm's eventual best score, and has no final native message count. It tests
the repository's very sparse default probe schedule rather than tuning Jerboa to
the available budget. Its raw output is retained as `june-fresh.solution` and
`june-fresh.log`; its incomplete status must accompany any comparison.
