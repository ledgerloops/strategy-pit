# Deploying the hosted TEST alpha

Deployment target: **https://app.ledgerloops.com**. The root `ledgerloops.com`
website and other DNS records are not changed. The source contains a Python
Heroku application with a release process and one web dyno running both HTTP
and background worker processes, PostgreSQL-backed
durable local stores, passkey accounts, session cookies and neighbour envelopes.
This document and the deployment script do not establish that a public deployment
has happened; verify the release and public application after execution.

## Required access and resources

- The intended Heroku account, a chosen unique app name and permission to create
  or update that app. A new deployment provisions one Basic web dyno and
  `heroku-postgresql:essential-0`; these are paid resources, approximately
  USD 12/month before tax (USD 7 dyno plus USD 5 PostgreSQL).
- DNS access for `app.ledgerloops.com`. Use Heroku's generated DNS target, never
  a guessed IP or the app's ordinary `herokuapp.com` hostname.
- A committed SHA containing all deployment inputs. The script archives committed
  application files only, so uncommitted fixes will not be deployed.

Provide `HEROKU_API_KEY` through the execution environment's secret settings or
local credential manager. Do not paste it into chat, commit it, put it in a URL,
or print `heroku config` output. If using the optional Cloudflare automation, also
provide `CLOUDFLARE_API_TOKEN` with zone DNS read/edit access and
`CLOUDFLARE_ZONE_ID` for `ledgerloops.com`. The zone identifier is not a secret.

The deployment preserves existing configuration and node/account credentials.
It refuses to rewrite a different existing `PUBLIC_ORIGIN`, since that can break
registered passkeys. It never recreates a database merely to reset state.

## API deployment

From the repository root, check access first:

```sh
python ops/deploy_heroku.py --app YOUR_HEROKU_APP --check
git rev-parse HEAD
```

Then deploy the exact full SHA from the second command:

```sh
python ops/deploy_heroku.py --app YOUR_HEROKU_APP --deploy --commit FULL_40_CHARACTER_SHA
```

Add `--configure-dns` only when the Cloudflare environment variables are configured.
The script creates or updates **only** the `app.ledgerloops.com` CNAME, DNS-only.
Conflicting A/AAAA records cause an explicit stop; it does not delete them or
change root-domain, email, TXT or unrelated records.

The script uses the Heroku Sources API to upload a short-lived source archive,
creates a build pinned to the SHA, waits for a successful build and release phase,
then scales one Basic web dyno and disables any legacy standalone worker dyno.
It sets `PUBLIC_ORIGIN=https://app.ledgerloops.com`,
`PGSSLMODE=require` and `PYTHONUNBUFFERED=1`. Existing secrets are retained. It adds
the custom domain and enables Automated Certificate Management (ACM).

Public output contains only app/release/build status, source SHA and DNS target;
source signed URLs, database credentials, account credentials and provider error
bodies are never logged. A reported release is not a claim that DNS or TLS is ready.

## DNS and browser-only alternative

If API credentials are unavailable but the local browser is signed into Heroku:

1. Open the intended Heroku app, or create a Cedar/Heroku-24 Python app in EU.
2. Attach persistent Heroku Postgres and set the public configuration above.
3. Deploy the pinned repository commit, ensuring its release phase succeeds.
4. Enable one Basic `web` dyno and disable any old standalone `worker` dyno.
   `hosted_single.py` supervises Gunicorn and the background worker within web.
5. Add `app.ledgerloops.com` in Settings → Domains and enable ACM.
6. Copy the generated `*.herokudns.com` target into the DNS provider's CNAME for
   `app`. With Cloudflare, start DNS-only so Heroku certificate validation can
   reach the app. Remove conflicting records only as an explicit DNS migration.

The temporary Heroku hostname is suitable for `/healthz` checks. The app deliberately
requires the canonical domain for enrollment and ordinary UI requests; register
lasting passkeys only after `https://app.ledgerloops.com` works.

## Verify before announcing availability

- Heroku shows successful build/release and one running Basic web dyno. Its
  supervisor runs both Gunicorn and background wakeups; either service exiting
  fails the dyno so Heroku can restart it. SIGTERM reaches both service process
  groups, with forced cleanup after 20 seconds (Gunicorn gets 15 seconds to drain).
- DNS resolves the custom domain to its assigned target; ACM has issued a valid
  certificate. HTTPS `/healthz` returns `service: ledgerloops-alpha`, `status: ok`.
- Sign up with a passkey on the canonical domain. Save recovery codes privately.
  Sign out/in and exercise second-passkey/recovery using isolated TEST accounts.
- Establish mutually accepted trustlines and comfort zones; propose and approve
  TEST obligations, then run headroom clearing and inspect local receipts/history.
- Restart the web dyno and confirm account identity, obligations, balances
  and pending protocol state persist. Do not restore an old ledger snapshot to
  release reservations or discard pending work.
- Verify that operator-access and TEST-only disclosures are visible. The headroom
  mode is an honest-peer, sufficient but incomplete certificate: see
  [the protocol and theorem](headroom_protocol.md). No full optimality or hostile-
  peer security claim should appear in the deployment announcement.

Backups and a tested recovery procedure are operational responsibilities. A code
rollback must retain compatible current database state; blindly restoring an old
database can invalidate outstanding obligations and hashlock decisions.

## References and deployment-tool tests

- [Heroku build and release API](https://devcenter.heroku.com/articles/build-and-release-using-the-api)
- [Platform API reference](https://devcenter.heroku.com/articles/platform-api-reference)
- [Automated Certificate Management](https://devcenter.heroku.com/articles/automated-certificate-management)
- [Postgres plans and Essential limitations](https://devcenter.heroku.com/articles/heroku-postgres-plans)

```sh
python -m unittest discover -s ops -p 'test_*.py' -v
python -m unittest discover -s app -p 'test_hosted_single.py' -v
```

These tests use mocked provider APIs and a temporary local Git repository. They
do not create live resources or demonstrate real account/DNS authorization.
The supervisor checks use real isolated subprocesses to verify service failure,
signal forwarding and bounded cleanup without accessing a database.
