# Laptop deployment handoff: native PostgreSQL storage

Status: ready for an authenticated local worker; **not deployed from the cloud**.
The user explicitly authorized deployment of PR #47, then requested the deployment
be handed to a worker on their laptop while Atomic development continues in cloud.

- Repository: `ledgerloops/strategy-pit`.
- PR: https://github.com/ledgerloops/strategy-pit/pull/47
- Review branch: `feat/native-postgres-storage`, based on `research/mdg2-local-improvement`.
- **Deploy tested source `d7a1fab55aeb2f9bf92ac0a09b6b960084c641e2`.** Subsequent handoff-only documentation does not change that application revision.
- Existing app: **`ledgerloops-alpha`**, canonical origin **https://app.ledgerloops.com**.
- Validation: 251 application tests, 8 deployment-tooling tests and native PostgreSQL CI passed. The unchanged legacy Node/Jest job reports no tests.
- Cloud has no Heroku credential or database URL. Use the laptop's normal authenticated CLI/API session; never copy credentials into chat, Git or task summaries.

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
