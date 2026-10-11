# Strict economic channel episodes

`temporal_episodes.py` adds `EpisodeTemporalProtocol`, a drop-in replacement for
`TemporalProtocol` for random DFS, largest-first DFS and Numbat. The earlier
sources and their saved results are unchanged. This is a cancellation baseline,
not a temporal Headroom algorithm.

Each endpoint holds its peer's episode number, revision, signed balance, ceiling
and live status. Every zero crossing closes the episode. Only external posting
opens another episode; reversal closes the old one and opens a new direction.
Same-direction transfers preserve unused headroom, partial clearing preserves the
ceiling, and reaching zero discards it. These ceilings are observed state here:
none of these three algorithms restores debt.

Search messages and prepares carry their transmitting pair's episode/revision.
A receiver cancels stale searches, including a packet that arrives after closure
and reopening with enough new balance to fit its old amount. The traversed route
carries outgoing-edge quotes; each prepare checks its own quoted edge again.
Revision changes reject old observations conservatively even if the same amount
would still fit. This may increase aborts under continuous transfers. All three
algorithms receive this same policy.

Control grace allows an already admitted token to finish or cancel through old
contacts. Commits require a live local reservation; an unknown commit cannot
acquire authority from a reopened edge. A previously applied commit returns
without forwarding or applying it again. The reliable transport independently
ACKs each delivered envelope and suppresses duplicate application delivery.
Tombstones and admitted token IDs are retained without a memory bound.

The substrate remains the earlier debtor-owned ledger with atomic bilateral
posting. A pair write installs state at its two endpoints; it does not consult
other pairs or choose routes. This models bilateral agreement and immediate
state visibility, rather than implementing authenticated replicated agreement.
Actor routing and admission consult local state and received payloads only.
External posting waits on either endpoint's existing reservation. The existing
fail-fast outgoing reservations, irrevocable staged commit lap, retries and sleep
semantics are unchanged. No crash recovery or whole-cycle atomicity is claimed.

Tests cover exact closure/reopening/reversal, stale episode and revision packets,
old outgoing quotes, unknown and duplicate applied commits, partial clearing cap
retention, dropped data/ACKs, sleeping nodes and drained conservation. Comparison
runs must record this new source hash and must not relabel old transport-grace
results as strict-episode results.
