# Handoff to Ledgerloops (local)

22 October 2026. User explicitly requested this handoff to **Ledgerloops (local)**.
Destination task ID: `01a1630a-dff7-7eb1-b90d-6179ea6a385a`, host `local`, task cwd
`/Users/michieldejong/Documents/Codex/2026-10-22/ledg`.

## Current demo release — 23 October 2026

**Heroku v13**, source `3c189e9068884ebb1bd7e3f8294a7a4d48501348`, is live at
**https://app.ledgerloops.com**. Exactly one **Basic web.1** dyno is up, supervising
HTTP and background delivery; maintenance is off and Essential-0 remains attached.
No paid upgrade, credential rotation or data reseed was performed.

This release repairs the storage incident: idle deadline writes and impossible
one-sided search origins had repeatedly rewritten complete SQLite images, leaving
hundreds of MB of dead PostgreSQL TOAST space and failed-search journals. Searches
now require the existing node-local necessary origin condition and back off to
five minutes while balances/preferences are unchanged. No audit history is deleted.
Small version-only registry polling wakes changed nodes without constantly loading
all ledger images. Actors keep their own retry deadlines and a 60-second safety
heartbeat. Acknowledgments are committed in one own-node batch, with unchanged
receiver deduplication; binary snapshot reads avoid hex wire expansion. Smaller
expiring pools and bounded transaction/lock waits leave maintenance headroom.

Before physical compaction, every stored image/version was backed up privately.
The supervised web/worker dyno was fully stopped, stale connections reset and the
snapshot table compacted. All 14 image hashes and versions matched exactly before
and after. Allocated database size fell from 739,632,415 to 32,916,767 bytes; the
resumed application subsequently reuses space for normal protocol work. Heroku's
initially stale `pg:info` summary refreshed from **700 MB / 1 GB (68.35%)** to
**63.4 MB (6.19%)**, with **9/20 connections**. Direct SQL remains the current-size
check when provider summary metrics lag. After v13 recovery drained, two direct
samples 50 seconds apart both measured **89,531,679 bytes (85.4 MiB, under 9% of
the allowance)** with all 14 versions unchanged, zero blocked connections and
8–10 connections including the inspection session.

Validation: **222 Python app tests** passed with isolated real PostgreSQL, plus
real Chromium/Flask/PostgreSQL integration using the production scheduler class.
Regressions cover idle image/version stability, schema/PRAGMA persistence, bounded
row-lock rollback and recovery, incoming writes during a tick, retry deadlines,
restart wakeups, batched ACK partial failure and crash-before-ACK deduplication.
Browser checks still pass automatic clearing, named invitations, value deliveries,
private aliases, messages and combined history.

Live post-v13 checks passed with only the worker's existing labeled TEST accounts:
protected cookies/identities, private aliases, balances, delivery records, messages
and historical clearing receipts survived the restart. Six session/state requests
completed in **0.124–0.290 seconds**, compared with the earlier 30-second page
request timeouts. The older deployment TEST accounts and receipts were separately
verified preserved. No test message was sent to a human peer.

## Previous demo release — v11 (22 October 2026)

**Heroku v11**, source `2ac9a37b12eef4b67757db22fd956338802245e7`, is live at
**https://app.ledgerloops.com**. Verified after restart: one **Basic web.1** dyno
is up, supervising HTTP and the background worker. Essential-0 PostgreSQL remains.

The v11 release adds **Rename** (a private label for one direct peer), **Send
message** and **View history**. Message and rename forms are native modals.
Messages use durable own-node records and authenticated neighbour outboxes,
including zero-balance/paused/reserved relationships. Stable request IDs and
receiver deduplication prevent double sends after lost responses or delivery ACKs.
Delivered means persisted at the peer node, not read by its human participant.
Renaming never changes the peer's own label, identity, limits or balances.

Per-peer history combines messages, value deliveries and committed loop-clearing
receipts in date order. It filters durable local records before paging 100 entries;
Load earlier retains older records. Aborted background search noise is omitted
from this view. Text is escaped and message line breaks preserved. Financial
protocol envelopes take priority over queued chat in the outgoing worker batch.

All **201 Python app tests** passed with real isolated PostgreSQL, including
independent transport/privacy/ACK-loss/queue-priority fixtures. Both updated
Chromium suites passed aliases, zero/reserved-edge chat, HTML-like text, retained
retries and paginated combined history. Independent desktop/mobile real-browser
QA also checked 4xx error retention, lost-response reconciliation and focus.
Live canonical HTTPS checks used only the worker's existing labeled Value Delivery
TEST accounts: private rename isolation, both message directions, repeated-send
deduplication, peer-only mixed history, unchanged financial state and preserved
older TEST ledgers/receipts. An actual single-dyno restart retained cookies, private
aliases and messages. The temporary TEST alias was restored afterward. Existing
user accounts, balances, keys and preferences were not reset. Canonical deployed
frontend bytes match the source commit; Heroku reports one up Basic web.1 dyno.

The v10 follow-up makes **Copy invitation** copy only the URL. The targeted
Chromium suite passed again, and the live frontend bytes and HTTPS health were
verified. The broader feature and restart checks below were completed for v9
(source `24f95c73ef5ed05961a5f9536e5f781fd67dd9e5`).

The user approved the peer-list wireframes and the phrase **Record a value
delivery**, then asked for Invite a peer and delivery forms to be modals. The
implementation uses native desktop dialogs, full screen on phones, with Escape,
logical focus restoration after polling, retained drafts and inline errors.

Without an invite, onboarding asks only for a display name and Continue. With an
invite, it shows both names, the inviter's maximum and an editable recipient
maximum; one explicit Connect creates/reuses the cookie identity and accepts.
Both independently select MAX, prefilled 10 TEST. New own preferences are credit
MAX, comfort [-MAX, floor(MAX/2)], assistance enabled; default shared comfort is
[-5,5]. Odd maxima round the positive half down because TEST balances are whole
units. Invitation acceptance fixes each first choice durably so crash retries or
crossed invitations cannot replace established bounds or keys.

The home shows only the name and invitation action until a peer exists. It then
shows the peer list, named balances, shared comfort bars and per-peer delivery
action. A delivery selects its goods/service provider, description and TEST value,
previews the balance delta, and needs the peer's explicit confirmation. No extra
consent toggle is required. Sending, confirming and declining remain separate
from automatic clearing; API/storage names remain `obligation`.

Hosted automation now defaults on and searches/approves eligible debt-reducing
headroom clearing in the background under bilateral comfort permissions. A
versioned migration enables only untouched legacy defaults, preserving custom
opt-outs, hard/comfort bounds, pauses, keys, balances and pinned reservations.
Existing accounts and cookie identities are retained. Discovery is opportunistic
and incomplete; unit-size moves can be gradual and unavailable peers can stall
work. Hosted clearing is status-only; standalone research controls remain.

Validation: **192 Python app tests** and **three isolated Chromium suites** passed.
Independent desktop/mobile real-HTTP visual QA checked native dialogs, focus,
drafts, asymmetric limits, direction and confirmation. Lost-response regression
checks that reconciliation closes a successfully recorded request instead of
leaving a stale form available for duplicate submission.

Live canonical HTTPS checks with three clearly labeled Value Delivery TEST
accounts verified protected persistent-cookie reuse, named links/previews,
independent invitation limits, own [-10,5]/shared [-5,5], confirmed deliveries and
**automatic 2-to-1 clearing with no browser discovery/clearing-approval calls**.
Local completed receipts verified. A pending delivery, identities and ledger
survived an actual single-dyno restart; normal decline then drained reservations.
Only those fixture nodes were paused briefly for the exact restart snapshot and
resumed afterward. Existing deployment TEST identities, balances, delivery records
and historical receipts were independently verified unchanged. Automatic failed
search attempts legitimately append aborted receipts; verification compares old
receipts by ID instead of requiring the entire journal to stop growing.

## Previous demo release — v8

**Heroku v8**, source `7b6771317c293ed75e077ff83107a04274127f26`, is live at
**https://app.ledgerloops.com**, still on one Basic web dyno plus Essential-0
PostgreSQL. This release supersedes the passkey-first UI described in the older
checkpoints below, at the user's request.

The demo now asks only for a name, then keeps an opaque identity cookie for one
year, renewing it on return. Passkey/recovery setup is absent. Recovery issuance
and redemption are disabled by default; old accounts, passkeys, recovery hashes
and valid browser sessions remain. Names never authenticate or recover accounts.
Cookie loss/expiry or using another browser starts a new identity.

Before a peer exists, the app shows only the name/greeting and invitations.
Named `https://app.ledgerloops.com/#invite=…` links preview the inviter's name,
prefill the intended peer name through signup, and require explicit acceptance.
Copying an invite includes both names. Existing relationships keep their labels,
keys and preferences. New relationships start with credit 10 TEST, comfort
[-10,10], assistance off and automation off.

Once connected, named peer cards show balances, pending decisions and **Record an
economic event**. An event is a balance delta, confirmed by both peers before it
posts. Existing API/storage names remain `obligation`; Advanced contains research
controls after peers exist. A no-peer browser sees no navigation, financial
summary, raw invitation-code entry, sliders or settings.

Validation: all 52 hosted Python tests pass with isolated real PostgreSQL. Both
isolated Chromium fixtures pass name-only onboarding, returning cookie identity,
separate browser identities, names/links through signup, no automatic invitation
acceptance, same-tab fragment navigation, additive economic events in both
directions, consent, autosave, real neighbour HTTP and headroom 2-to-1 clearing.
The broader 179-test app suite passed before the final relationship-default and
UI refinements; targeted hosted and browser checks cover those refinements.

After deployment, live canonical HTTPS checks passed with three labeled Cookie
Demo TEST identities: persistent protected cookies/repeated-start reuse, disabled
recovery, named URL and preview metadata, explicit acceptance, economic events,
headroom 2-to-1 receipts, and a pending event reservation. Restarting the single
dyno retained those identities, ledgers and the pending reservation; normal
protocol decline then cleared it. The three older deployment test identities,
ledgers and cookies also stayed unchanged. Chrome retained the user's existing
identity and displayed the new invitation-only home without any credential reset.

## Local deployment result — 22 October 2026

The local worker deployed **https://app.ledgerloops.com** on Heroku app
`ledgerloops-alpha` (EU, Cedar, Heroku-24). Current app release **v7** succeeded,
source `84809d45b9fb3f526e760ab526e738ea2b797a13`. At the user's request,
**one Basic web dyno runs both HTTP and background delivery**, supervised by
`app/hosted_single.py`; there is no separate running worker dyno. Essential-0
PostgreSQL remains attached. Expected recurring cost is USD 12/month before tax.

Cloudflare now has a DNS-only CNAME for `app` targeting
`fathomless-atoll-4r9cg1op2j5o4r1otfoqg951.herokudns.com`. The existing root A
record and wildcard CNAME are retained. Heroku ACM reports **Cert issued**, with
verified Let's Encrypt TLS for `app.ledgerloops.com`, expiring 20 January 2027.

Live HTTPS checks passed: real P-256 WebAuthn server verification, sign-out/in,
second credential, one-use recovery and session revocation, protected session
cookies, invitations, synchronized comfort settings, two approved TEST
obligations, real background neighbour HTTP, 2-to-1 headroom clearing and local
receipt consistency. Restarting the single web dyno retained sessions/node
identities, balances, receipts and an additional pending TEST obligation and its
reservation. That pending test obligation was then declined through its ordinary
protocol; all test outboxes drained and no reservations remained. Three clearly
named Deployment TEST accounts and their settled one-unit TEST debt remain.
No preexisting user's credentials, local demo files or older testnet apps changed.

These live tests used software authenticators through HTTP, not a platform
passkey browser UI. This Mac initially retained the old site in its OS DNS cache;
test requests resolved the assigned Heroku target while retaining the canonical
HTTPS hostname, origin and full certificate verification. Public DNS resolvers
and the authoritative nameserver returned the new target. After the local stale DNS entry expired, Chrome loaded the canonical
login page normally and displayed the TEST/operator-access notices. Interactive
platform-passkey enrollment remains untested; no certificate warning was bypassed.

The initial Sources API upload signature issue was fixed by preserving the
signed empty Content-Type; a live upload/build/release succeeded. The build poller
was subsequently corrected to recognize the provider's actual `succeeded` status
(commit `fa02ba9`; tooling only, excluded from runtime archive). Eight deployment
unit tests and three real subprocess supervisor lifecycle tests pass. The earlier
cloud handoff below remains historical context, not the current deployment status.

## Request and current external state

The user authorized documenting and implementing comfort-zone clearing and working
until the alpha is deployed using Heroku. The final canonical URL is
**https://app.ledgerloops.com**, not the apex. The user thinks DNS is at Cloudflare
or Namecheap and explicitly authorized driving their **Chrome**. Hosting is
acceptable only with disclosed operator access; algorithms may not exploit shared
visibility or a clearing coordinator.

**Not deployed from this cloud task.** No Heroku app/add-on, DNS record, account or
production secret has been created/changed. No Heroku credential or DNS credential
was available. The Browser skill exists but no browser-control tool is exposed in
this task. Plugin searches found no applicable Chrome/Heroku/Cloudflare connector.
The local worker is expected to use its connected Chrome or configured CLI access.

The cloud task can read the destination worker but has no `handoff_thread`,
`create_thread` or send-to-thread tool. A handoff document opened in its panel does
not start it; the user must tell the worker to continue if no dispatch becomes
available. Do not claim a running handoff merely because the file is available.

## Source checkpoint

Repository: https://github.com/ledgerloops/strategy-pit

Branch: `research/mdg2-local-improvement`. Fetch its latest checkpoint containing
this document; inspect the local checkout and preserve any local changes. Read
`AGENTS.md` and the latest `docs/research-queue.md`. Do not create a worktree unless
the user requests one. Existing demo JSON configs, tokens, peer keys and databases
must be preserved. No token rotation or fresh reseed as part of an update.

## Implemented and reviewed

- `app/headroom_policy.py`, `private_node.py`, `verify_private_receipt.py`:
  `headroom` mode, `comfort-surplus-bit-v1`, `sha256-headroom-v1`. Actual isolated
  hashlock fixtures clear **3→1**, **2→1**, and the earlier **3→2 helper-increase**
  example, including restart, duplicate fulfillment, stale preferences and
  tampered surplus. Local permission stays within bilateral comfort/hard bounds.
- [Theory/protocol](../app/headroom_protocol.md): origin retains a reduction of
  two local exposure units per amount; each helper increase consumes a previously
  earned one-bit surplus. This proves strict total-debt reduction for accepted
  honest-peer transcripts without a route, roster, count or aggregate oracle.
  One capped prefix predicate is disclosed. The rule is incomplete; dishonest
  peers can fabricate surplus. No full-optimality/Byzantine claim is justified.
- `app/hosted_storage.py`: authoritative PostgreSQL row per local SQLite image,
  loaded only into memory under its own row lock. Ledger+outbox commit together
  before HTTP. No ephemeral-file persistence, no whole-loop DB transaction.
  [Exact semantics/limits](../app/HOSTED_STORAGE.md): O(node-state-size) I/O,
  software capability scoping rather than hostile-process sandboxing.
- `app/hosted_auth.py`: maintained WebAuthn verifier, actual P-256 tests, stable
  account/node identity, secure HttpOnly session cookies, exact origin and CSRF,
  second passkeys, one-use recovery codes. RP ID is **app.ledgerloops.com**.
- `app/hosted_runtime.py`, `hosted_server.py`, `hosted_worker.py`: session-bound
  own-node API, bilateral invitations, separate stable enrollment channel-key
  registry, independent node transactions and authenticated HTTP delivery.
  Explicit background-clearing opt-in; no auto-approval of obligations.
- UI: passkeys/recovery, cookie/CSRF integration, invitations, autosaved comfort
  controls, obligations/history, headroom receipt verification and automation.
  Standalone bearer-token demos remain functional. Operator access is disclosed.
- `Procfile`, `.python-version`, `requirements.txt`, `app.json`, `.slugignore`:
  Python/Heroku one web dyno supervising HTTP + worker, a release migration,
  PostgreSQL and canonical origin.
  Force the Python buildpack despite the repository's older `package.json`.

Review fixes included crossed-invitation key races, rejecting automatic cancellation
outside comfort zones, continuing delivery with empty shared zones, and avoiding
expected discovery failures rolling back whole worker wakeups.

## Validation and repeatable commands

The cloud's disposable PostgreSQL17 was at `127.0.0.1:55432`, database `postgres`,
test-only trust authentication. It is not a production credential or a resource
available on the local Mac. Provision a separate local TEST database for reruns.
Tests use random scoped rows and clean only their own rows; never use production.

Checkpoint results: **158 application Python tests passed with PostgreSQL enabled**;
the actual Chromium/Flask/PostgreSQL/HTTP integration passed, including 2-to-1
headroom clearing and stable re-login. The isolated hosted UI browser fixture and
standalone authentication regression also passed. **Seven deployment-tool tests**
passed against mocked providers and temporary Git source, not real infrastructure.

```sh
python -m pip install -r requirements.txt
LEDGERLOOPS_TEST_POSTGRES_DSN='postgresql://postgres@127.0.0.1:55432/postgres' \
  python -m unittest discover -s app -p 'test_*.py' -q
node app/test_hosted_ui.cjs
LEDGERLOOPS_TEST_POSTGRES_DSN='postgresql://postgres@127.0.0.1:55432/postgres' \
  node app/test_hosted_browser_integration.cjs
```

The browser fixture uses its own local server, isolated PostgreSQL prefix and
virtual authenticators; it is not a test against the user's signed-in browser.
Use the appropriate Chromium path on the local host. See the research queue for
the final counts from the checkpoint validation. Frozen benchmark sources/results
were not changed or rerun, and no new performance comparison is claimed.

## Continue through deployment

1. Inspect the local worker's available tools and read the Browser skill. Verify
   the connected browser is Chrome before interacting. Use the existing signed-in
   Heroku and DNS dashboards; ask the user to sign in only if actually blocked.
   Never print API keys, database URLs, recovery codes or full config dumps.
2. Follow [the Heroku runbook](../app/HEROKU_DEPLOYMENT.md). Inspect existing apps
   first. Deploy the pushed commit with Python buildpack, durable PostgreSQL,
   one Basic web dyno running both HTTP and background worker processes, and
   `PUBLIC_ORIGIN=https://app.ledgerloops.com`. Disable the old standalone worker
   dyno when updating a two-dyno release; the user requested one dyno locally.
   The release phase initializes storage idempotently. Review current plan/billing
   facts, not assumed historical prices. Do not touch unrelated existing apps.
3. Add `app.ledgerloops.com` to Heroku and obtain its actual DNS target. Determine
   the authoritative DNS provider; registrar and DNS hosting can differ. Change
   only the `app` record, preserve apex/mail/other subdomains, enable ACM and wait
   for a valid certificate. For Cloudflare, start DNS-only to verify Heroku TLS.
4. Verify the final HTTPS origin, `/healthz`, passkey enrollment/sign-in/recovery,
   invitation and preference exchange, bilateral TEST obligations, headroom
   settlement and receipt checks. Never register permanent alpha passkeys against
   a temporary herokuapp.com origin.
5. Verify worker operation and dyno restart persistence, including stable node
   identity and retained pending work. Leave unresolved operations visibly pending;
   never free locks through timeout or restore old ledgers against later peers.
6. Record exact commit, Heroku app/release, domain/TLS status and observed checks,
   then tell the user the actual live URL. Only say deployed after live evidence.

Implementation is ready for checkpoint review; this file does not assert that
all external prerequisites or production smoke checks have been completed.
