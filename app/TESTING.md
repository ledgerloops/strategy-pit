# App network validation

This report covers the executable app, separately from research simulation benchmarks. The test network uses fabricated integer TEST units and loopback TCP. Each participant is an independent process with its own SQLite database. Loopback does not model geographic latency or hostile hosts.

## Required evidence for this milestone

- Browser requests authenticate to one node and display actual persisted balances.
- Neighbour discovery produces a proposal without mutating balances or granting manual consent.
- All participants approve their own exact local changes before commit.
- Clearing preserves each participant's signed net position and counterparties reconcile after completion.
- Duplicate requests/messages cannot apply a settlement twice.
- An unavailable node leaves work visibly pending; restart with the same database resumes delivery and resolves it without releasing uncertain reservations on timeout.
- Unauthorized API/message requests and invalid amounts are rejected.
- Pause blocks fresh work while permitting recovery of admitted work.
- No setting enables real-value/live mode.

## Scope limits

Targeted failures provide evidence about the exercised transitions. They do not establish correctness at every possible crash boundary, Byzantine tolerance, stale-backup recovery, production key custody or legal finality. We will report actual test counts and observations below after running the implementation.

## Results — 11 October 2026

**24 Python tests passed**: six actual three-process HTTP tests, three launcher/configuration tests and fifteen independent adversarial state-machine tests. [Machine-readable evidence](network-test-results.json) pins the tested Python sources and records scope and runtime.

The network clears the three debts 7/3/5 to 4/0/2 after all three manual approvals. Signed net positions remain Alice −2, Bob +4, Doris −2. Tests include delivered commit with a lost HTTP acknowledgement, duplicate replay, SIGKILL after preparation, restart with retained consent/reservations, an offline participant, intermediary failure after local commit, recovery while paused, explicit decline and authorization failures. The independent suite additionally exercises digest mismatch, conflicting decisions, transaction rollback and reordered/duplicated delivery.

Browser checks exercised three authenticated sessions against the actual nodes: discover 3 TEST, approve in each browser, await all-participant confirmation, download the receipt, inspect five screens at 320/390/1280px, pause and disable new discovery while offline. This is functional/layout checking, not a complete accessibility audit.

Browser reproduction requires Playwright and Chromium in the development environment, separately from the dependency-free service. Start a **fresh** demo directory first, then:

```sh
APP_DEMO_DIR=/tmp/ledgerloops-demo node app/test_browser.cjs
# Optional: CHROMIUM_PATH=/path/to/chromium APP_BASE_PORT=8761
```

The browser test intentionally changes the test ledger and leaves Alice paused. Use a fresh network directory for another full run. Tokens are read from the local test configs without printing them. The screenshots show fabricated ledger records, not credentials.
