# Propose, approve and list TEST obligations

The private v2 app supports new bilateral obligations between configured direct
peers. Open **06 / Obligations**, choose a peer, choose **I owe this peer** or
**This peer owes me**, enter a positive whole TEST amount and an optional
description, then confirm and propose. This is a separate action from saving
credit/comfort preferences.

The other person sees the same description and the mirrored before/after
balance. They must explicitly approve those exact terms, or decline. Neither
balance changes merely because a proposal was submitted or delivered. A
declined or stale proposal remains in history with no balance change.

The list contains all unresolved proposals and up to 100 recent completed or
declined entries. **Activity** also shows obligations. **Peers → View history**
combines the contact's obligation entries and clearing receipts. These lists
are not a complete historical export; starting fixture balances are not
synthetic obligation entries. Completed obligation entries remain visible after
later clearing changes the current balance.

## Try entering a cycle and clearing it

Python 3.12 is the tested runtime; the servers use the standard library.

```sh
python3 app/run_obligations_demo.py \
  --data-dir /tmp/ledgerloops-obligations-demo --base-port 8991
```

Use a fresh directory. This starts Alice, Bob and Doris at zero, with 10 TEST
credit grants and zero comfort targets on every relationship. Open
`http://localhost:8991`, `:8992` and `:8993`. Connect each tab using the `token`
field in its corresponding JSON config in the printed data directory.

1. Alice proposes **I owe Bob 3 TEST**. Bob approves in Obligations.
2. Bob proposes **I owe Doris 3 TEST**. Doris approves.
3. Doris proposes **I owe Alice 3 TEST**. Alice approves.
4. Once all three obligations show **Recorded**, Alice opens **Clearing**,
   selects **Reduce existing debt**, and requests exactly **3 TEST**.
5. Approve the clearing proposal in each tab. All balances return to zero;
   the three obligations and the clearing receipts remain in history.

An existing private or comfort demo also supports obligation entry after all
nodes run this version. Existing credit grants still apply: raise the
creditor's grant in **Peers** if needed, and wait for synchronization before
proposing. The new launcher does not overwrite other demos. Restarting with
the same directory preserves balances, preferences, decisions and pending work.

## Agreement, credit and recovery

Submitting a proposal records the proposer's consent and reserves that
relationship. Delivery also reserves the recipient's matching relationship
while they review it. Preference edits and competing clearing/obligation work
cannot change a reserved edge. Both snapshots, preference revisions and the
resulting balance must match, and the result must fit both credit grants.
Comfort ranges do not prevent a consensual obligation outside comfort but
within credit limits: that obligation can create a clearing opportunity.

The proposer currently cannot withdraw a submitted proposal. The recipient
can decline before approval. Approval is irrevocable; both sides retain the
decision and wait for its outcome rather than unlocking on a timer. An absent
peer can therefore leave the relationship reserved indefinitely.

Posting uses a durable offer/accept/commit/settled exchange between the two
direct peers. The origin records its balance change and outgoing commit in
one SQLite transaction, and retains its reservation until the peer confirms
application. The recipient records its own mirrored change and reply
atomically. Duplicate deliveries and restarts do not apply the change again.
Application may be visible at different times at the two nodes. The UI labels
local application while peer completion is still pending.

An obligation changes the two participants' signed net positions. A completed
clearing operation subsequently preserves each net position. These operations
have different accounting purposes.

Proposal IDs make retries idempotent; reusing an ID with different terms is
rejected. The browser retains an unconfirmed proposal's original ID across
refresh in the same tab, checks refreshed state, and can retry that request.
Opening a new tab does not carry over the old tab's pending request; inspect
the list before submitting another proposal. Failed known-invalid submissions
retain the editable form. Digests bind approval terms; they are not public
signatures. This remains an honest-peer, isolated TEST network with retained
databases, configured credentials and eventual peer recovery.

## API and validation

Only private v2 nodes advertise `obligation_capable: true`. `/api/state` includes
`obligations`; authenticated `GET /api/obligations` returns the same list policy.

- `POST /api/obligations`: `{id, peer, amount, direction, description}`. `id` is
  a fresh 64-character lowercase hex identifier; `direction` is `i_owe` or
  `peer_owes` from the proposer's perspective. Description is at most 200
  characters; amount is a positive integer up to 1,000,000,000 TEST.
- `POST /api/obligations/{id}/approve` or `/decline`: `{digest}` from the displayed
  local proposal. The authenticated client of the receiving node decides.

Responses contain `{ok: true, obligation: ...}`. Views use local `before`,
`after` and `direction`, plus `peer`, `amount`, `description`, `origin`, `approved`,
`digest`, `created_at`, `status`, `applied_at` and optional `reason`. Statuses are
`proposed`, `pending`, `approved`, `committing`, `committed` and `aborted`.

```sh
python3 -m unittest discover -s app -p 'test_obligations*.py' -v
# Start a separate fresh zero-balance demo for the browser test:
APP_DEMO_DIR=/tmp/ledgerloops-obligations-demo APP_BASE_PORT=8991 \
  node app/test_obligations_browser.cjs
```

The browser exercise requires Playwright and Chromium (`CHROMIUM_PATH` can
select its executable). It enters the obligations through the actual UI,
checks approvals, decline, caps, text escaping, persistent contact history and
an actual three-node cancellation cycle. Python tests additionally inject
stale snapshots, duplicate messages, transaction rollback, concurrent decisions,
lost acknowledgments, crashes and shared-reservation conflicts.
