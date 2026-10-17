# VM PostgreSQL nightly backup — prepared, intentionally disabled

Status: **source-only candidate / NOT INSTALLED / NOT ENABLED / NOT RUNNING**.

This change is for the development and rehearsal stage of GXP-QLCL.
It does not create a VM service, timer, cron, backup object or database write.
Issue: #14. Parent: isolated checksum remediation PR #12. Do not modify
the frozen integration PR #9 without a separate, approved source/CI gate.

## Intended schedule (after a future explicit authorization)

- Timer: `infra/vm/gxp-postgres-nightly-backup.timer`
- Service: `infra/vm/gxp-postgres-nightly-backup.service`
- Entrypoint: `tools/run_vm_nightly_backup.py`
- Existing dump/upload owner: `infra/vm/backup_postgres.sh`
- UTC schedule: 01:30 daily (not local time); `Persistent=false` prevents
  boot/start catch-up runs. No automatic retries or backup-on-install.
- Service identity: `gxp`, not root; reads canonical `/etc/gxp/runtime.env`
  and active `/etc/gxp/runtime.systemd.env` in a read-only preflight.
- Source of truth: **currently deployed backend release**, not a mutable
  Git checkout or a candidate PR.
- The unit hardcodes `GXP_NIGHTLY_BACKUP_ENABLED=0`; the entrypoint
  declines to call any backup logic while the opt-in is not exactly `1`.
  Even a manually started unit cannot create a backup in the shipped state.

Do **not** install, enable, start, or run these files as part of ordinary
development, CI, Draft PR review, or rehearsal release preparation.
No cron entry should be added to duplicate this timer. The older suggested
`sudo crontab -e` entry in `docs/VM_PRODUCTION_BASELINE.md` is a
**manual reference**, not an already active scheduler.

## Fail-closed target binding

Before invoking the existing backup script, the Python entrypoint checks:

1. Explicit opt-in environment marker.
2. The running `gxp-web` systemd unit references the expected active
   systemd environment file and is active.
3. Both canonical and active configurations have `APP_ENV=production`,
   `DB_MODE=local_postgres`, and matching, explicit `DB_NAME`,
   `DB_USER`, `DB_HOST`, `DB_PORT`.
4. Active `DATABASE_URL` exists and matches those database target fields.
   Canonical `DATABASE_URL` is optional, but if present it must match.
   Credentials and full URLs are not printed.
5. Active `DEPLOYMENT_GIT_SHA` agrees with the release metadata; the
   `current-backend` symlink and executing script root agree with that
   metadata. Malformed env input is never echoed.
6. Cloud Storage bucket is configured. Scheduled execution forbids
   `ALLOW_USER_GCLOUD_AUTH=1` break-glass override.

If any check fails, the script refuses to invoke `backup_postgres.sh`.
The existing owner still enforces pg_dump, digest creation, GCS upload and
the attached VM service-account identity contract. The checksum portability
fix lives in PR #12 and is the direct parent of this candidate.

Current operator read-only evidence (2026-10-17) found canonical and active
targets both `gxp_legacy_rehearsal`. This is not a guarantee for future
deployments; preflight checks them **again on every permitted run**.

## Activation contract — FUTURE ONLY, requires separate approval

Only after the backend fix PRs have been reviewed, integration sources
refreshed, suitable push CI passed, a verified recent backup and disposable
restore drill are available, and the operator explicitly approves:

- Review the service's exact `ExecStart` absolute path, group permissions,
  database target, timezone, budget/retention and notification ownership.
- Install the two approved unit files using controlled privileged operations
  **without** enabling or starting them. Review `systemd-analyze verify`,
  `systemctl cat`, `systemctl is-enabled`, and deployed source SHA.
- A separate operator-controlled activation step may change the service
  opt-in to `1` and enable/start the timer. This requires explicit approval;
  it is not part of this branch or PR.
- After activation, validate actual creation times, paired GCS objects,
  cloud IAM, checksum verification, and a disposable PostgreSQL restore.
  Inspect `systemctl status` / `journalctl -u gxp-postgres-nightly-backup.service`
  for failures. A paired filename alone does not prove recoverability.

No attempt is made to restore into `gxp_legacy_rehearsal` or `gxp_qlcl`.
No scheduler automation should be enabled during the current testing stage.

## Evidence and unresolved gates

Prior VM read-only inventory: 86 paired object names with newest dump from
2026-10-14 01:01 UTC (approximately 79 hours old on 17 October). Cron
inactive; `pg_dump@.timer` and `pg_basebackup@.timer` are templates only;
no running backup timer found. A historical run tied to deployment is
plausible, but external schedulers have not been exhaustively ruled out.

This candidate creates code and tests **without executing backup**.
Full backup freshness, GCS object checksum, external alarm setup and a
real disposable restore drill remain pending. Current gate stays
`REHEARSAL_DEPLOY_NO_GO`.
