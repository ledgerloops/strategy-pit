# Address book, credit limits and shared comfort

Open **Peers / address book** on a private hashlock node. Each contact shows your current balance, your credit grant, your peer's grant, their preferred range in your perspective and the derived shared comfort zone. You can edit only your own preferences.

Positive means **the peer owes you**. Negative means **you owe the peer**. For example, your range −5…15 and your peer's own range −10…8 produce a shared −5…10, subject to both credit limits. Unknown peer preferences are shown as unknown. Disjoint ranges produce “No shared comfort zone”; they do not imply a zero target or a negotiated compromise.

## Dots and contact history

Drag the credit-limit and comfort-bound dots along their aligned balance lines. Separate tracks keep coincident dots reachable. Arrow keys adjust by one TEST; the labels and shared-zone preview update immediately. Zoom controls change only the scale, including the full supported range. Select **Save preferences** to persist an edit, or discard it.

Select **View history** on a contact to see that relationship's clearing proposals and local receipts, with dates and before/after balances. This filters the latest 100 proposals and latest 100 receipts returned by your node; it is not a complete historical archive or a preference-change journal. Downloaded receipts contain both of your local edges for the operation, as disclosed on the screen.

## Save and synchronize

Preferences are persisted in the node's SQLite database and sent only over the authenticated direct relationship. Revision checks reject stale edits and conflicting peer updates. The displayed shared zone uses the latest preferences received by that node; updates are eventually delivered, not a new bilateral settlement agreement. During an outage the two screens can temporarily differ.

Prepared settlements pin their existing terms. Editing a reserved contact is rejected, and incoming preference updates retry after the reservation ends. Lowering a credit grant preserves the existing balance, warns about exposure above the new cap and still allows cancellation that strictly reduces that exposure. It does not forgive debt or create new credit automatically.

Default personal ranges are zero, automatic adjustment is off, and initial credit grants cover the existing positive fixture balance. New contacts remain a separate onboarding feature; this release edits already configured neighbours.

## What automatic adjustment means in this release

The checkbox saves a **preference for the experimental comfort policy**. Actual hashlock v2 settlement remains manually approved cancellation-only. It does not yet restore debt, route through zero-balance credit or act automatically based on these settings. Those operations need versioned bilateral admission and recovery rules before the preference can authorize live testnet adjustments. The interface states this explicitly.

The [simulation](../experiments/COMFORT-SIMULATION.md) does execute the comfort policy with the same interval model. An edge outside its shared range seeks improvement; an edge inside it can help without becoming uncomfortable. Neutral helping moves and increased exposure require both peers' assistance permissions. Strict improvement at the initiating edge ensures useful movement without a node needing a global objective or roster. Settlement is serialized by the simulator; this does not extend the app's hashlock guarantees.

Try the [interactive synthetic example](../experiments/comfort-demo.html): total debt can increase from 2 to 4 while discomfort falls from 2 to zero. Download/open the HTML in a browser, or serve the repository locally to explore it. No real node data is loaded.

## Validation

[App test evidence](comfort-test-results.json) covers mirrored ranges, clipping, empty intersections, stale/conflicting updates, direct-peer authorization, reservation races, persistence and existing hashlock regressions. The browser flow saves both peers' preferences, verifies the two mirrored shared intervals, exercises disjoint ranges and a lowered credit cap, and checks pointer/keyboard dot editing, unsaved draft preservation through history navigation, phone/desktop layout and offline controls. The three-node browser settlement test also verifies contact-filtered history and downloads its actual local receipt.

```sh
python3 app/run_private_demo.py --data-dir /tmp/ledgerloops-comfort-demo --base-port 8961
# With Playwright/Chromium available:
APP_DEMO_DIR=/tmp/ledgerloops-comfort-demo APP_BASE_PORT=8961 node app/test_comfort_browser.cjs
```

The browser test changes fabricated contact settings; use a fresh demo directory for reproduction. [Phone](screenshots/comfort/mobile.png) · [Desktop](screenshots/comfort/desktop.png) · [Contact history](screenshots/comfort/history-mobile.png).
