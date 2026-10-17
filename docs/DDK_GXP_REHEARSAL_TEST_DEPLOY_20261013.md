# GXP-QLCL — rehearsal test deploy with Alembic 0022 → 0023

Scope: development/testing VM only, **gxp_legacy_rehearsal**, not the future
go-live database **gxp_qlcl**.

## Why this change exists

`infra/vm/deploy_rehearsal.sh` delegates to `deploy_prod.sh`, which already
backs up its configured database and runs `alembic upgrade head` before
switching the release and testing `/readyz`. The earlier rehearsal preflight
incorrectly required the target to be at head *before* that deploy.
`tools/prepare_rehearsal_deploy.py` now accepts either the current head or
a recognized ancestor from Alembic's on-disk revision graph. Unknown,
divergent, future, missing or uninitialized revisions still fail.

Current observed VM test state (2026-10-13): runtime SHA
`8e032071558d63c2b53d397e64addca7894cbc0b`, `/readyz` HTTP 200,
database `gxp_legacy_rehearsal`, revision `20261008_0022`. The next
candidate PR #7 includes `20261012_0023`, which creates two **empty**
DDK GxP source-provenance relations (no source rows are imported).

## Test deployment

From the VM's clean source checkout, after the exact candidate CI has passed,
run its existing orchestrated rehearsal deploy rather than applying the
standalone SQL first:

```bash
cd /opt/gxp/src/GXP-QLCL
sudo env DEPLOY_GIT_SHA=<verified_PR7_candidate_SHA> \
  bash infra/vm/deploy_rehearsal.sh
```

The VM checkout must already contain the updated `deploy_rehearsal.sh`
preflight and its Python helper, e.g. by fast-forwarding/fetching the PR #7
checkout while preserving local work. `DEPLOY_GIT_SHA` pins the release
artifact; it does **not** automatically update the scripts executed from
the current source checkout. Inspect `/etc/gxp/runtime.env` only with
private, secret-safe tooling if configuration diagnostics are required.
The script derives a **temporary** rehearsal database URL from the
canonical env and does not edit that canonical env.

This is a **testing** deployment: a short interruption/readiness mismatch
during the schema+runtime transition is acceptable. The normal deploy
auto-restores previous *runtime* symlinks on a later-stage failure,
**but does not undo an already-completed Alembic schema upgrade**.
If the upgrade commits and a later stage fails, do not treat rollback
to the 0022 application as successful (its readiness will likely be 503).
Repair/redeploy a schema-compatible candidate or use a reviewed
database restore/downgrade procedure. Avoid restarting the old backend
expecting head 0022 while the database remains at 0023.

After success, verify `/readyz` and independently check the revision,
DDL shape, and empty source tables using
`scripts/verify_ddk_gxp_0023_postflight_readonly.sql`. Do **not** claim
that the 3,120 groups/861 tokens have been imported merely because
migration 0023 succeeded. That is a separate source-load step.

This file documents a dev/test deployment; it does not authorize
replacing a production database or merging PR #3/PR #7.

## Existing VM already points at rehearsal (observed 2026-10-13)

The VM operator found `/etc/gxp/runtime.env` uses `DB_NAME=gxp_legacy_rehearsal`,
rather than the canonical `gxp_qlcl` assumed by earlier rehearsal preflight.
The preflight now explicitly supports **both** source configurations, and
rejects a runtime env whose declared rehearsal DB disagrees with its effective
PostgreSQL URL. This change belongs to rehearsal deployment only; production
import continues requiring the canonical source and retains its own checks.

VM `/opt/gxp/src/GXP-QLCL` is owned by the application account, not
the SSH operator. Run `git` under the repo owner (typically `gxp`);
do **not** apply a global `safe.directory` exception. Use a shell with
`set -e` so failed source fetch/switch cannot accidentally continue to
deploy from an old checkout.

CI for prior head `a1ea5e2f43547142606a9e1ed5a21e93dadc422a` failed due to
an Alembic `CommandError` when a test supplies nonexistent `wrong-head`.
The runtime graph check now treats this as an expected mismatch.
Only an exact-head PASS of backend, frontend and hygiene authorizes
invoking the next test deployment.
