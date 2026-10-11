# Faster simulator transport without protocol changes

`fast_temporal_transport.py` contains separate `FastEpisodeTemporalProtocol` and
`FastConcurrentHeadroom` adapters. Existing sources and running benchmarks remain
unchanged. This is a simulator implementation experiment, not a new clearing
algorithm or a reduction in communication.

The adapters remove the redundant first `deepcopy` of a message payload. The
inherited transport still snapshots the entire envelope before returning to its
sender, and still copies the saved payload before handing it to a receiver.
They also cache the byte length of `repr` of that private envelope snapshot for
retransmission accounting. Retry counts, byte counts, ACKs, delays, random draws
and event scheduling remain identical.

The cache assumes ordinary protocol dataclasses with pure representations. It is
not a general replacement for arbitrary mutable or side-effecting serialization
objects. The simulation never mutates retained envelope payloads; the isolation
test explicitly mutates both sender and receiver copies and verifies the saved
snapshot and retry byte count remain unchanged.

Tests compare the complete scheduled-event trace, ledger, cycle records, every
metric, RNG state, node state and final queues for random DFS, Numbat and signed
Headroom, two seeds and both concurrent and stop-wait transport under data/ACK
loss and sleeping nodes. The separate runtime harness repeats larger matched
runs, checks the same final fingerprints, pins dependency hashes, and alternates
original/fast execution order over three repetitions. Its saved timings exclude
setup and equality checking. They run on a shared worker and are approximate;
large Sarafu runtime improvement has not been established by these samples.

Reproduce with `python3 experiments/fast_transport_benchmark.py`. The result is
saved in `experiments/results/fast-transport-runtime.json`. Use a new explicitly
named adapter and source hash for future campaigns; do not substitute it into an
in-progress experiment or relabel old measured runtimes.

The first completed runtime matrix has **12 configurations × 3 repetitions × 2
adapters = 72 runs**, using 24/72-node burst graphs, clean seed 31 or 30% data/ACK
loss plus sleep at seed 32, and all three methods. Every matched final fingerprint
is identical. All saved dependency hashes match the final files.

Summing configuration medians gives **13.05 seconds original versus 9.32 seconds
optimized**, or **1.40× throughput / 28.6% less simulation time**. Individual
configuration speedups range from 1.30× to 1.55×. Grouped median ratios are 1.45×
for random DFS, 1.33× for Numbat and 1.42× for concurrent Headroom. This is useful
local runtime evidence, with no change in simulated debt, messages or wire bytes.
It does not establish the same speedup on a full Sarafu run.

These runtime samples used Python 3.12.14 (`python3`) in the shared workspace.
