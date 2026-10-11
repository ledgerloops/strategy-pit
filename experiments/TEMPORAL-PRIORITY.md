# Settlement-priority turn queues

This prospective variant makes a small improvement to genuine neighbour turn
queues, but does **not** beat concurrent Numbat on the tested circumstances.

`temporal_priority.py` replaces each endpoint's unsent FIFO outbox with two local
queues. Prepare, commit, abort and finish traffic precede exploratory `step`
messages, with a maximum of four urgent messages before a waiting exploration
message. Messages already assigned wire sequence numbers retain their ordering;
turn requests/grants, ACKs and retransmissions remain untouched. The decision
reads only that endpoint's own queue. No graph lookup or global priority arbiter
is involved.

The hypothesis was that finishing settlements sooner releases reservations and
reduces contention. It helps somewhat, but cannot remove turn negotiation and
head-of-line waiting for other traffic already sent during an earlier turn.

## Prospective evaluation

The burst limit of four was fixed before evaluation. Training used seeds 101/102,
24 nodes, three continuing-transfer generators (sparse, community, bursts), and
clean versus 30% data/ACK loss plus sleep. Each case compared concurrent Numbat,
FIFO local turns, and priority local turns. Time horizon 800, retry interval 50,
search depth 32, search budget 96, event budget two million per phase. The same
input and sleep schedules were reused, although activity changes subsequent RNG
consumption. These are small synthetic comparisons, not evidence on Sarafu.

The promotion criterion fixed before training required lower aggregate posted
ledger debt-area, no higher final debt, and at most 110% of FIFO wire attempts.
Training met this criterion, so the identical configuration was then evaluated
on held-out seeds 0/1. There are 36 training and 36 held-out runs; every run passed
independent per-edge settlement replay, final net-position conservation and
capacity checks.

| Held-out aggregate | Concurrent Numbat | FIFO local turns | Priority local turns |
| --- | ---: | ---: | ---: |
| Final remaining debt, scaled units | 18,109,000 | 19,264,000 | 19,133,000 |
| Posted debt-area, scaled amount × ticks | 12,530,281,000 | 13,198,128,000 | 13,073,036,000 |
| Data and ACK attempts | 60,222 | 68,716 | 70,473 |
| Total transfer posting delay, ticks | 15,028 | 15,939 | 15,670 |
| Unposted transfers at horizon | 0 | 1 | 0 |

Priority reduced FIFO final debt by **0.68%** and posted debt-area by **0.95%**,
while increasing attempts by **2.56%**. It left less debt in 7 paired held-out
cases, tied in 1 and left more in 4. Relative to concurrent Numbat it left
**5.65% more debt**, incurred **4.33% more posted debt-area**, and used **17.02%
more attempts**; it lost 10 of 12 paired final-debt comparisons.

Training's small debt-area improvement also came with 3.32% greater posting delay.
Posted debt-area excludes not-yet-posted external transfers, so it must be read
alongside posting delay and horizon backlog. No claim is made that this metric
alone captures user experience. Clearing percentages are not compared against
historical static Sarafu benchmarks.

Keep this as a modest improvement when local turns are independently required;
concurrent Numbat remains the stronger tested default here. Priority scheduling
alone does not rescue turn waiting's overall cost. This experiment does not
establish bounded worst-case latency, crash safety, or a production settlement
protocol.

Reproduce:

```sh
python3 experiments/temporal_priority_benchmark.py \
  --output experiments/results/temporal-priority-training.json
python3 -m unittest discover -s experiments -p 'test_temporal_priority.py' -v
```

Frozen source hashes, full parameters, input hashes, metrics and audits are in
[`results/temporal-priority-training.json`](results/temporal-priority-training.json).

Independent review reproduced all aggregate metrics and paired outcomes, matched all nine source hashes and regenerated input hashes, and verified local queue decisions preserve the wire-sequence and grant barriers.
