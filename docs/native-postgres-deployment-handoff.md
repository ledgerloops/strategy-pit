# Laptop deployment handoff: native PostgreSQL storage

Status: **deployed from the laptop on 27 October 2026 as Heroku v14**. The
running application source is exactly `d7a1fab55aeb2f9bf92ac0a09b6b960084c641e2`.
The current release record below supersedes the original execution checklist.
The user authorized deployment of PR #47 and its offline migration; Atomic
work remains separate and was excluded.

- Repository: `ledgerloops/strategy-pit`.
- PR: https://github.com/ledgerloops/strategy-pit/pull/47
- Review branch: `feat/native-postgres-storage`, based on `research/mdg2-local-improvement`.
- **Deploy tested source `d7a1fab55aeb2f9bf92ac0a09b6b960084c641e2`.** Subsequent handoff-only documentation does not change that application revision.
- Existing app: **`ledgerloops-alpha`**, canonical origin **https://app.ledgerloops.com**.
- Validation: 251 application tests, 8 deployment-tooling tests and native PostgreSQL CI passed. The unchanged legacy Node/Jest job reports no tests.
- Cloud has no Heroku credential or database URL. Use the laptop's normal authenticated CLI/API session; never copy credentials into chat, Git or task summaries.

## Verified local cutover result — 27 October 2026

- Live application: **https://app.ledgerloops.com**, Heroku **ledgerloops-alpha**,
  successful release **v14**, source **d7a1fab55aeb2f9bf92ac0a09b6b960084c641e2**.
- Exactly **one Basic web dyno** supervises HTTP and background work. Maintenance
  is off; the existing **Essential-0** database, credentials, origin and DNS remain.
  PR #47 was deployed at the tested pin without merging unrelated work or Atomic.
- Before any import, maintenance was enabled and every app writer was stopped.
  A full provider backup was captured and downloaded privately. The complete
  archive was decoded successfully, independently restored into a dedicated
  disposable local PostgreSQL database, and all **17** restored scope identities,
  image hashes, versions and timestamps matched the frozen production baseline.
  Backup exports and verification records are mode 0600, outside Git.
- The offline importer migrated **17 scopes / 127,282 rows**, including accounts,
  enrollment and every actor. An independent comparison then checked every
  native tuple against the retained source: **323 scope/table combinations**
  across all **19 domain tables**, with every stored column, rowid/order, missing
  table and allowed invitation default accounted for. Every value matched.
- All source hashes/versions remained identical; migration markers, old-writer
  fence and release readiness passed. All 19 domain tables force RLS, unscoped
  reads returned no rows, and the actual runtime role is neither superuser nor
  BYPASSRLS. It remains the ordinary object owner used by the existing release
  initializer; this is not a claim that runtime DDL authority has been removed.
- Before opening the router, the actual native application gateway accepted the
  **9 existing worker TEST cookies**, with their original accounts, node state
  and relationship history. Those read-only checks changed no registry versions.
- Canonical HTTPS health and live existing-cookie checks passed after reopening.
  Private aliases, balances, delivery/message records and historical clearing
  receipts were preserved. Six observed session/state requests took
  **0.125–0.281 seconds**; older deployment TEST accounts were checked separately.
- A message between known labeled worker TEST peers was submitted twice using
  the same ID. It was delivered once, acknowledged and stored in native rows at
  both endpoints; their native registry versions advanced. Financial records
  remained unchanged, and **all 17 legacy images, versions and timestamps stayed
  exactly unchanged**. No message was sent to a human peer.
- An actual single-dyno restart retained the native message, acknowledgment,
  existing cookies, financial records and history; the legacy hashes still
  matched. Pending protocol rows/secrets were included in the exact offline
  preservation check; none were discarded or force-released.
- Local validation passed **251 application tests**, **8 deployment-tool tests**,
  and the real Chromium/Flask/PostgreSQL integration against native storage with
  an ordinary non-BYPASSRLS test role. The browser fixture covered invitations,
  value-delivery consent, automatic 2-to-1 clearing, labels, messages and history.

Direct PostgreSQL inspection after live native processing measured **211,141,919
bytes (about 201 MiB)**, **17 native scopes / 17 completed migration markers**,
6 connections including the audit connection, and zero blocked connections.
This includes the deliberately retained legacy images alongside native tables.
Heroku's summary still showed the older 82.5 MB / one-table sample at that time;
use fresh direct measurements when provider metrics lag. The plan was not upgraded.

**Recovery boundary:** normal work now changes native rows. The retained legacy
images are stale recovery evidence, not a usable live fallback. Preserve the fence,
markers and backups. An old-code restart or snapshot restore is unsafe after native
processing; stop writers and plan a state-preserving recovery if a problem arises.
Account recovery UX remains deferred in [issue #45](https://github.com/ledgerloops/strategy-pit/issues/45).

## Original deployment plan

The following checklist records the reviewed procedure used for this cutover.

## Goal and boundaries

Replace the active SQLite-image persistence with native PostgreSQL tables and
forced owner-scoped RLS. Preserve all existing accounts, cookies, passkeys,
node/channel keys, names, balances, preferences, history, unreleased secrets,
reservations, inbox deduplication and queued outgoing work. Do not seed demos,
rotate credentials, change DNS/origin, upgrade paid plans or deploy Atomic WIP.
Do not merge/rebase unrelated work merely to deploy this pinned revision.

## Execute the reviewed offline cutover

1. Inspect the current checkout and preserve local changes/private files. Fetch
   the review branch and verify the full tested SHA is available. Read `AGENTS.md`,
   `app/HOSTED_STORAGE.md` and `app/HEROKU_DEPLOYMENT.md` from that revision.
2. Verify the existing Heroku app, current release/source, dyno formation and
   database attachment using normal authenticated tools. Confirm access before
   changing availability. Do not print configuration dumps or database URLs.
3. Put the app in maintenance and stop **every** web/worker writer, including
   the background worker supervised inside the web dyno. Confirm they stopped.
4. Capture and verify a private database backup while writers are stopped.
   Record a private baseline of account/node identities, balances, pending work
   and legacy image hashes/versions. Protect exports with restrictive permissions.
5. From the tested source and installed pinned dependencies, connect privately
   to that same database and run:

   ```sh
   python app/migrate_postgres_snapshots.py --confirm-offline
   ```

   Include **all** scopes, including accounts and enrollment. The importer
   retains originals and fences old writers. It is resumable; never bypass a
   failed import or overwrite a nonempty destination to force progress.
6. Verify native state and source markers against the retained baseline. Check
   the intended runtime role has neither SUPERUSER nor BYPASSRLS, and run the
   release readiness check. Preserve the migration's old-writer fence.
7. Deploy the exact tested source via the existing tooling, preserving app,
   database, origin and configuration. The release phase must succeed. Start
   only the native runtime with the established dyno formation.
8. Verify `/healthz`, existing account/session continuity, peer labels, balances,
   messages, retained history and durable pending work. Use only known labeled
   TEST accounts for any mutating smoke check; do not alter other participants.
   Confirm new changes affect native rows without rewriting legacy images.
9. Leave maintenance only when verification passes. Record the actual new
   release/source and verification evidence in a follow-up handoff/PR update,
   without credentials or private ledger contents.

If backup, migration or verification fails, preserve the stopped state and report
the concrete failure. After native processing starts, the retained old images are
stale: restarting the old release is not a safe rollback. Follow the storage
runbook's recovery boundary rather than discarding pending financial state.

The cloud Atomic rewrite is separate. Deployment authorization for this native
PostgreSQL revision does not authorize deploying that unfinished rewrite.
