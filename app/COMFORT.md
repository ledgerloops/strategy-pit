# Address book, credit limits and shared comfort

Open **Peers / address book** on a private hashlock node. Each contact shows your current balance, your credit grant, your peer's grant, their preferred range in your perspective and the derived shared comfort zone. You can edit only your own preferences.

Positive means **the peer owes you**. Negative means **you owe the peer**. For example, your range −5…15 and your peer's own range −10…8 produce a shared −5…10, subject to both credit limits. Unknown peer preferences are shown as unknown. Disjoint ranges produce “No shared comfort zone”; they do not imply a zero target or a negotiated compromise.

## Dots and contact history

One signed balance diagram combines your editable comfort zone above the axis, the shared zone on the axis, and your peer’s mirrored comfort zone below it. Your credit limit points down from above; your peer’s limit points up from below. The current balance is a dot on the axis. Drag your comfort endpoints or credit-limit arrow; arrow keys adjust by one TEST. Labels and the shared-zone preview update immediately. Your peer’s settings are read-only. Zoom controls change only the scale, including the full supported range. Dragging a comfort endpoint beyond your maximum moves that maximum along with it. Lowering your maximum into the comfort band pulls the endpoints back, keeping your comfort maximum within your own credit grant. Your negative personal preference remains independent of your peer’s read-only grant; the shared zone still clips both preferences to the bilateral limits.

Preferences save automatically after you release a dragged control or pause keyboard adjustments. The assistance checkbox also saves automatically. The status below the diagram reports saving, local success, or an error; success means local persistence and queued delivery to your peer, not confirmed peer delivery. A failed save retains your edits for retry or discard. There is no Save button. Older saved zones outside your own maximum are fitted in the editable draft; simply opening the contact does not change saved preferences.

Select **View history** on a contact to see that relationship's obligation proposals, clearing proposals and local receipts, with dates and before/after balances. This includes unresolved obligations and up to 100 recent completed obligations, 100 clearing proposals and 100 receipts returned by your node; it is not a complete historical archive or a preference-change journal. New bilateral TEST obligations can be entered in [Obligations](OBLIGATIONS.md) and must be approved by the other peer. Downloaded receipts contain both of your local edges for the operation, as disclosed on the screen.

## Save and synchronize

Preferences are persisted in the node's SQLite database and sent only over the authenticated direct relationship. Revision checks reject stale edits and conflicting peer updates. The displayed shared zone uses the latest preferences received by that node; updates are eventually delivered, not a new bilateral settlement agreement. During an outage the two screens can temporarily differ.

Prepared settlements pin their existing terms. Editing a reserved contact is rejected, and incoming preference updates retry after the reservation ends. Lowering a credit grant preserves the existing balance, warns about exposure above the new cap and still allows cancellation that strictly reduces that exposure. It does not forgive debt or create new credit automatically.

Default personal ranges are zero, automatic adjustment is off, and initial credit grants cover the existing positive fixture balance. New contacts remain a separate onboarding feature; this release edits already configured neighbours.

## Comfort clearing on the test network

The clearing screen offers **Reduce existing debt** (the default) and, on nodes advertising the capability, **Move toward shared comfort**. Comfort discovery uses an exact requested amount. It can traverse configured relationships with zero balances and move a balance in either direction, within the bilateral credit and comfort rules. A search can miss a smaller feasible adjustment; no result is an optimality claim.

The diagram checkbox means **Allow this relationship to help comfort clearing**. The API retains the historical name `auto_adjust`, but this is assistance permission, not automatic execution. Neutral helping moves and increased exposure require the permissions required by the bilateral policy. **Every participating person still explicitly approves the exact proposal.** Automatically saving a preference or starting discovery alone does not settle anything.

Proposal review shows your local before/after balances, each edge’s distance from shared comfort, and the exact pinned local and peer preference revisions. A helping balance can move away from zero without becoming uncomfortable. Total debt can therefore increase while shared discomfort decreases; these are different objectives. Completed operations conserve each participant’s signed net position.

Comfort proposals use a distinct `sha256-comfort-v1` condition. It binds the amount, clearing mode, signed direction, policy, operation ID, protocol, unit and fulfillment. The browser independently verifies this context on released local receipts. A verified local fulfillment is not a claim that all other nodes have completed their writes. Existing hashlock recovery, reservation and honest-peer limitations still apply; this remains a TEST-only prototype.

The [simulation](../experiments/COMFORT-SIMULATION.md) explores the same interval model with automatically selected moves. Its settlement scheduler is separate from the manually approved network implementation. Use it to compare policies, not as proof of network recovery or automatic execution support.

Try the [interactive synthetic example](../experiments/comfort-demo.html): total debt can increase from 2 to 4 while discomfort falls from 2 to zero. Download/open the HTML in a browser, or serve the repository locally to explore it. No real node data is loaded.

## Validation

[Preference-only historical evidence](comfort-test-results.json) covers mirrored ranges, clipping, empty intersections, stale/conflicting updates, direct-peer authorization, reservation races, persistence and existing hashlock regressions. The browser flow saves both peers' preferences, verifies the two mirrored shared intervals, exercises disjoint ranges and a lowered credit cap, and checks linked credit/comfort controls, saving once on drag release, keyboard focus, reload persistence, failed-save retry, recovery after a committed write loses its response, draft preservation through history navigation, phone/desktop layout and offline controls. The three-node browser settlement test also verifies contact-filtered history and downloads its actual local receipt.

```sh
python3 app/run_private_demo.py --data-dir /tmp/ledgerloops-comfort-demo --base-port 8961
# With Playwright/Chromium available:
APP_DEMO_DIR=/tmp/ledgerloops-comfort-demo APP_BASE_PORT=8961 node app/test_comfort_browser.cjs
```

The integrated-diagram checks also cover independent keyboard access to coincident comfort endpoints and preserving ±1 trillion TEST preferences through reload.

The browser test changes fabricated contact settings; use a fresh demo directory for reproduction. [Contact diagram](screenshots/comfort/contact-diagram.png) · [Phone](screenshots/comfort/mobile.png) · [Desktop](screenshots/comfort/desktop.png) · [Contact history](screenshots/comfort/history-mobile.png).

## Network comfort browser exercise

The dedicated comfort fixture starts with Alice owing Bob 2 TEST and two zero-balance helping relationships. Its configured shared zones allow a manually approved comfort cycle to clear Alice–Bob while creating 2 TEST on each helping relationship. Gross debt rises from 2 to 4; shared discomfort falls from 2 to zero.

```sh
python3 app/run_comfort_demo.py --data-dir /tmp/ledgerloops-comfort-settlement --base-port 8991
APP_DEMO_DIR=/tmp/ledgerloops-comfort-settlement APP_BASE_PORT=8991 node app/test_comfort_settlement_browser.cjs
```

Use a fresh directory. The browser exercise checks the default cancellation selection, explicit comfort discovery, no execution before all three manual approvals, conserved net positions, independently verified context-bound receipts, rejection of a changed direction in receipt data, receipt download and contact-scoped history. See [final integration evidence](comfort-settlement-test-results.json), the [independent protocol review](COMFORT_REVIEW.md), and [network coverage](COMFORT_NETWORK_TESTING.md). [Completed settlement screenshot](screenshots/comfort/settlement.png).
