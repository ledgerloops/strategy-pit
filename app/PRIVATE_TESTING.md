# Private hashlock v2 validation

This suite targets the neighbour-private replacement tracked in [issue 004](../docs/issues/004-neighbour-private-hashlock-settlement.md). It is separate from the legacy path-carrying v1 network evidence in `network-test-results.json`.

## What must be tested

Participants run in separate processes with separate databases, connected by authenticated neighbour HTTP. Test instrumentation may know a fixture's full graph, but participant code receives only its own peer configuration. Rings of different sizes exercise the same message format without a membership list or hop-count field.

The privacy claim is a structural knowledge boundary: no remote participant identities, enumerated path, origin identity or exact total-loop count is required in participant records or protocol messages. It is not anonymity against timing, traffic analysis, collusion, topology inference or shared-condition correlation. Stable, non-aliased node identities and honest protocol execution are assumptions of the minimum-three argument; Sybil resistance is not implemented.

Hashlock tests must distinguish a valid preimage from permission: fulfillment also needs the exact local approved proposal and intact reservations. Conditions bind version, identifier, amount and unit. Test altered conditions, wrong and missing preimages, replay across transactions, pre-release API leakage, recovery after durable secret release, duplicate delivery and abort/release ordering.

The first implementation has no deadline that frees possibly fulfillable capacity. An offline peer or unavailable origin can block pending work. Safe decline is allowed only before that participant has granted irrevocable conditional consent, and release must never follow a durable abort. The runtime refuses legacy databases rather than migrating pending obligations implicitly.

## Reproduction

```sh
python3 -m unittest discover -s app -p 'test_private_*.py' -v
```

Actual TCP/process tests need permission to bind local sockets. Use fabricated TEST units only. Existing v1 tests remain available with `test_network.py` and `test_adversarial.py` to detect unintended regressions in the shared client/launcher infrastructure.

## Evidence boundaries

Selected fault schedules do not cover every crash boundary, disk loss, permanent participant disappearance or hostile neighbour. Privacy schema inspection does not prove cryptographic anonymity. Local receipt verification checks the stated hash condition and local accounting consistency; it does not independently prove that every other participant approved or settled. Report completion only at the scope justified by available evidence.

## Completed evidence — 11 October 2026

**50 tests passed:** 24 legacy regression checks, 16 private adversarial tests, seven private HTTP network tests, and three independent receipt-verifier tests. [The machine-readable report](private-test-results.json) pins sources, fixtures, commands and exact outcomes.

Real three-, four- and seven-node networks clear while preserving every local net position. Four/seven-node fixtures exercise the non-neighbour distinction; each node also has irrelevant offline side peers. Test-only proxies capture protocol bodies, and the harness inspects every node's logical database dump and API state for remote identity and route/count disclosure. Participants never receive the harness graph.

Faults include a delivered fulfillment whose acknowledgement is dropped, invalid preimages over HTTP, prepared-node restart, origin failure after durable release while the next peer is offline, decline, and a probe that enters a non-origin subcycle. The last case exposed a cleanup defect during review; explicit local refusal and idempotent forwarding now make its outboxes drain. Another regression ensures semantic probe replay cannot inject a stale rejection. Intersecting probes, both database-migration directions and abort/release ordering have independent state-machine tests.

The three-browser flow also passed: exact-amount discovery, local conditional approvals, context-bound WebCrypto verification, downloaded-receipt verification, deliberate preimage tampering producing a verification failure, five screens at three widths, pause and offline controls. Screenshots: [phone](screenshots/private/mobile.png), [desktop](screenshots/private/desktop.png). This is not a full accessibility audit.

To reproduce the browser flow, use a fresh private demo network and Playwright/Chromium:

```sh
APP_DEMO_DIR=/tmp/ledgerloops-private-demo APP_BASE_PORT=8861 \
  APP_PROTOCOL=private-hashlock-v2 node app/test_browser.cjs
```

The test changes the fabricated ledger and leaves Alice paused. No claim of public-network load performance, production security, Byzantine tolerance or proof of the entire original historical design follows from these results.
