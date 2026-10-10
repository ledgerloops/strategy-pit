# Local turn waiting

`local_turns.py` provides an optional, endpoint-local communication primitive.
`temporal_turns.py` integrates it as `TurnTemporalProtocol`, a subclass of the
temporal simulator. It has no measured clearing advantage yet. The benchmark's
`stop_wait` mode is a separate transport baseline.

Each relationship has two `LocalTurn` instances, one at each peer. The smaller
peer ID initially owns epoch zero. A waiting endpoint sends `request`; the owner
finishes a bounded batch after learning about that demand, relinquishes its
turn, and sends `grant` for the next epoch. An idle owner also hands over on
request. No permission from any other neighbour is required.

A grant records how many payloads belonged to the preceding turn. Its recipient
cannot acquire the turn until all those payloads have arrived. This barrier
handles a grant overtaking its data. Epochs reject duplicate and stale grants;
sequence numbers deliver data once and in order. Completed epochs can discard
their duplicate-tracking state. A quiet peer does not cause periodic token
ping-pong.

The wire adapter must retry data **and controls** until acknowledged. A dropped
grant can temporarily leave neither endpoint holding the turn. It never gives
both endpoints permission to send. Eventually delivered retries restore
progress if endpoints retain state and wake up. Do not manufacture a new token
on timeout: a sleeping owner may still own the old one.

Call `enqueue(payload)` for an application message, `receive(TurnMessage)` for
a delivered wire message, and `pump()` during local scheduling opportunities.
Callbacks should enqueue events rather than recursively deliver them. Count
request, grant, acknowledgements, and retries in communication budgets. A
reliable adapter can wrap payload and control messages identically. Connect the
`deliver` callback to the clearing node's normal receive handler.

This serializes communication on one pair, not whole-loop settlement. It does
not reserve credit, decide which loop is preferable, make commits atomic, or
hold several pair turns together. Those remain separate protocol concerns.
Historical Squid/DLD turn waiting was designed around probe-exchange ordering;
this is a fresh transport primitive inspired by that concern, not a claim to
reproduce Squid.

Assumptions and limits:

- Peers retain state during sleep and do not forge messages. Crash recovery
  would require durable epochs, queues, and adapter state.
- Eventual progress requires eventual delivery and continued local scheduling.
  Permanent message loss or permanently sleeping peers can block a channel.
- The queue and reorder buffer need backpressure for production use; completed
  turn metadata itself does not grow with the number of turns.
- At zero balance, the enclosing lifecycle should drain pending work before
  destroying pair state. Reopening with delayed old packets requires a channel
  incarnation identifier or retained epochs; resetting both endpoints to zero
  while old traffic remains is unsafe.

Tests cover simultaneous demand, 30 randomized schedules with duplicated and
reordered delivery, grants arriving before payloads, stale controls, bounded
old-epoch state, and recovery after a dropped grant and a sleeping peer. These
are executable checks, not a proof of correctness for all failure modes.

```sh
PYTHONPATH=experiments python -m unittest experiments/test_local_turns.py -v
```

## Temporal simulator integration

```python
from temporal_turns import TurnTemporalProtocol
sim = TurnTemporalProtocol(seed=12, loss=.3, ack_loss=.5, turn_batch=8)
```

Use the same transfer/sleep/run/drain interface as `TemporalProtocol`. The
underlying reliable transport remains concurrent; `LocalTurn` endpoints control
application payload release. Request/grant/data envelopes all pass through the
same retry-and-ACK fault model, while ACKs and retries bypass the gate. Pair gate
objects persist across zero balance and reopening. Draining also checks that all
gate queues emptied and all application messages were delivered.

`messages`, `data_attempts`, `payload_repr_bytes`, `ack_attempts` and loss/retry
counters include wire control overhead. `turn_controls` splits out request/grant
messages. `wire_deliveries` counts unique wire envelopes;
`application_messages`/`application_deliveries` count the enclosed clearing
messages. Thus `messages = application_messages + turn_controls` after drain.
The simulator's internal `transport` remains `concurrent` because that field
configures the underlying reliability layer; select the subclass explicitly in
reports rather than labelling it as the baseline concurrent protocol.

Five integration tests cover all three search policies under loss/sleep,
12 changing-graph seeds, preservation of net positions, retained state after
closure/reopening, every first wire transmission and ACK lost, locality facades,
and permanent loss correctly reported as incomplete.

```sh
PYTHONPATH=experiments python -m unittest experiments/test_temporal_turns.py -v
```
