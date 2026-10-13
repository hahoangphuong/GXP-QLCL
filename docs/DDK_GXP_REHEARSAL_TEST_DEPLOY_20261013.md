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
