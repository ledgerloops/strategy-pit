# Independent review of comfort-assisted settlement

Reviewed 12 October 2026. This is an implementation and adversarial-test review of the honest-peer TEST prototype, **not a production security audit or proof of Byzantine safety**. The reviewed design is described in [comfort_protocol.md](comfort_protocol.md). The independent checks are in [test_comfort_security.py](test_comfort_security.py); all twelve pass.

## Admission and conservation

The bilateral hard interval, from a node's viewpoint, is `[-peer_credit_limit, own_credit_limit]`. Shared comfort intersects this interval with the node's personal interval and the reflected peer interval. Empty intersections cannot participate. Existing debt is not erased when a limit is lowered: monotone reduction toward zero is permitted, while newly increasing excess exposure is refused.

For a fixed signed amount `d`, a participant changes its predecessor balance by `-d` and successor balance by `+d`. Its signed net position therefore remains unchanged. The receiving endpoint checks the sender's negated before/after values and swapped preference revisions. This ties the two endpoint views to the same edge transition. Preparation checks both local quotes again and holds both reservations.

Each admitted edge has nonincreasing distance from its agreed interval. The origin's outgoing edge must strictly improve. Under consistent bilateral snapshots and honest participants, the completed cycle therefore strictly reduces aggregate discomfort without requiring any node to calculate that aggregate. Neutral assistance and any increase in absolute exposure require both endpoints to opt in. Every participant also approves its exact local proposal manually. This is not a guarantee of lower total debt: the demonstration deliberately changes debt from 2 to 4 while eliminating discomfort.

## Races and durable decisions

The review specifically challenged stale snapshots between probe and prepare. An honest stale quote receives a protocol rejection rather than an endlessly retried HTTP error. Rejection unwinds through the origin's durable abort; reserved capacity is not freed merely because communication or approval takes time. The tests include an origin already reserved while its next peer changes preferences, and verify that the deferred synchronization finishes after abort with balances unchanged.

Local edits to reserved relationships are rejected. New peer revisions are deferred while the corresponding reservation exists. The immutable proposal and approval digest retain both local preference snapshots, their revisions, before/after balances and the shared interval. Existing approved terms survive later preference changes after local settlement.

The origin releases the fresh secret only after the readiness token has passed every participant's consent gate and returned. Local application and forwarding are committed in the same SQLite transaction. Tests cover restart immediately after origin release, duplicate delivery, and refusal to replace the irrevocable decision with abort. These guarantees depend on honest forwarding and retention of the current database.

## Findings corrected during review

The standalone receipt verifier initially accepted a reversed pair of neutral helper changes: absolute deltas and net conservation still matched, but their order contradicted the signed direction bound into the hashlock. The verifier now checks the ordered deltas `-direction * amount` and `+direction * amount`. It also requires the pinned incoming/outgoing quote records to match the corresponding changes and validates positive bounded integer preference revisions. The independent regression reproduces the former acceptance and now rejects it.

Comfort conditions use a separate context binding mode, policy and signed direction. Tests reject using cancellation evidence or another direction for comfort settlement. Valid negative-direction settlement is also covered. The original cancellation scheme remains supported.

## Evidence and remaining limits

The twelve independent tests cover:

- Opted-in assistance over zero balances, final bilateral agreement and signed-net conservation, with no completion before the last manual approval.
- Either endpoint refusing assistance; empty intervals; and refusal to originate without strict improvement.
- Stale probe and prepare revisions, deferred preference delivery, and reservations holding both snapshots.
- Hash context separation, receipt direction/revision tampering, positive and negative directions.
- Decline before disclosure, and durable restart after irrevocable release.

Separate network tests exercise actual HTTP processes; their results are reported in [COMFORT_NETWORK_TESTING.md](COMFORT_NETWORK_TESTING.md). This review does not substitute unit tests for those deployment-boundary checks.

No route, participant list or exact cycle length is needed: admission messages contain only the current direct edge's quote alongside the opaque protocol context. The minimum-three argument still assumes distinct honest identities and rejection of immediate reflection and revisits. Metadata, timing and collusion can reveal information.

Receipts establish local hashlock and accounting consistency, not signatures, remote consent or independently authenticated application. A dishonest peer can falsify readiness. Permanent origin loss, an indefinite partition or restoration of an old database can defeat progress or the retained-state assumptions. There is no timeout unlock, Byzantine agreement, public-network hardening, production key recovery or guarantee of simultaneous bilateral visibility. Assistance remains manually approved; the opt-in setting does not enable unattended signing.
