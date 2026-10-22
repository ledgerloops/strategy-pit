# Handoff to Ledgerloops (local)

22 October 2026. User explicitly requested this handoff to **Ledgerloops (local)**.
Destination task ID: `01a1630a-dff7-7eb1-b90d-6179ea6a385a`, host `local`, task cwd
`/Users/michieldejong/Documents/Codex/2026-10-22/ledg`.

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
