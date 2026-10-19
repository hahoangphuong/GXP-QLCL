# VM local nightly PostgreSQL backup trigger — read-only discovery

**Status: SOURCE-ONLY / NOT RUN ON VM / NO BACKUP AUTHORIZATION.**
Addresses [Issue #14](https://github.com/hahoangphuong/GXP-QLCL/issues/14)
without enabling timers, invoking `pg_dump`, reading database/GCS/NAS data,
creating a backup, or changing production configuration.

## Why this audit is needed

An operator's 17/10/2026 **GCS object-name metadata only** inventory recorded 86
paired dump/sidecar **names**, newest dated 14/10. Pairing does not prove
checksum or restore-ability. The current in-repository
`infra/vm/backup_postgres.sh` is called by `deploy_prod.sh` at deployment;
a deployment-produced backup does not prove an active nightly schedule.
The separate `gxp-postgres-nightly-backup.service` intentionally ships with
`GXP_NIGHTLY_BACKUP_ENABLED=0`, and the timer source is explicitly marked
**NOT INSTALLED / NOT ENABLED**. Source contents cannot certify the actual
deployed systemd/cron state or exclude external Cloud Scheduler.

## Read-only execution contract (later operator verification only)

After checking an exact reviewed source SHA and the intended host, an operator
may run the source-only CLI on the VM; this command performs no backup:

`python3 -m tools.audit_vm_backup_trigger_readonly`

The CLI inspects:
- Systemd timer `LoadState`, `ActiveState`, `UnitFileState` and whether
  it records a last trigger. It does not start/stop/reload any unit.
- Systemd service unit source for a literal opt-in environment assignment,
  service load/active status, and known successful *service result* (not a
  successful backup; an inactive service can also have `Result=success`).
- Read-only `crontab -u root -l` and `-u gxp -l` probes, `/etc/crontab`
  and non-symlink files in `/etc/cron.d`. Unreadable user crontabs remain
  **UNVERIFIED**, not confidently absent. Other user crontabs, wrappers and
  outside-machine schedulers are outside scope.
- Last up to 500 unit journal entries, reading JSON metadata and counting
  entries/timestamps ONLY. Never printing MESSAGE, user commands, storage
  locators or credentials.

Output is a single redacted JSON with three possible statuses:
`LOCAL_TRIGGER_REFERENCE_OBSERVED`,
`NO_ACTIVE_KNOWN_LOCAL_TRIGGER_OBSERVED`, or
`LOCAL_TRIGGER_UNVERIFIED`.
None of these is a successful nightly backup or restore proof. A visible
active trigger may still fail during `pg_dump`, SHA256 creation, GCS upload
or remote object integrity; a non-visible local trigger does not rule out
other hosts/external schedulers. All outputs explicitly set DB/storage writes
to zero and all backup/restore verified flags to false.

## Rehearsal VM V1 observation and precise clarification (19/10/2026)

The operator ran exact source SHA
`1c828e4e0d7a845aae1e8fd400953aec3867e289`
and blob `ffcca64610fdb172b6040903b6660e8b5614401b`
on `gxp-web-prod` in read-only mode. Sanitized V1 result:

- Named GXP backup timer and service both `LoadState=not-found`,
  `ActiveState=inactive`, with zero unit journal entries.
- The system-cron probe read two entries with no **direct** recognized backup
  reference, and skipped one entry for an **unknown reason**.
- The root and gxp `crontab -l` calls both returned `UNVERIFIED`,
  because V1 could not distinguish a missing user crontab from a
  permission/command error. The tool did not examine external schedulers.
- V1 misleadingly reported `unit_result_known_success=true` for
  a unit with `LoadState=not-found`; **this is a generic systemctl property,
  not evidence of a backup run**. The owner fix ensures this flag is false
  unless the service is actually loaded.
- V1 correctly reported zero DB/storage writes and no backup/restore proof.

The narrowed V2 owner repair classifies **only** the exact standard
`no crontab for root` / `no crontab for gxp` errors as `NO_CRONTAB`;
other stderr messages, localization, permission errors and command failures
stay `UNVERIFIED`, and stderr content is never output. It also emits
*aggregate counts only* for skipped system-cron files
(`symlink`, `oversized`, `nonregular`, `read_error`),
never private filenames, paths or commands. A skipped symlink remains
unverified, not proof of a missing trigger. Neither the new classifications
nor a successfully loaded service are proof of successful `pg_dump`,
GCS upload or restore.

This is a tool-output root-cause fix, **not** a backup scheduling change.
Re-running the trusted read-only audit on the same VM may sharpen the
local findings, but cannot exclude crontabs belonging to other users,
indirect cron wrappers or Cloud Scheduler in another project.

## Further gates before any remediation or activation

1. Review the sanitized local result and clarify the operator's expected
   schedule: **intentional disabled development stage** versus separately
   approved nightly requirement. Do not label a never-enabled timer as a
   silently failing installed service.
2. If a trigger is observed, use separately approved, redacted metadata
   investigation to distinguish missed fire, failing dump, checksum, upload,
   IAM and object listing. This tool does not replay scheduled jobs.
3. Explicit owner approval is required for enabling timers/cron, configuring
   permissions, manually taking or downloading backups, altering GCS,
   invoking a restore, or deploying/restarting VM services.
4. For the GMP 376 one-FK correction, source-only CI and a healthy timer
   alone are insufficient: a fresh verified backup, successfully exercised
   isolated restore/rollback, exact-row preflight and **separate DB-write
   approval** are mandatory.
5. Never restore into `gxp_legacy_rehearsal`, `gxp_qlcl` or `gmpnn_ai`;
   never update Case/Certificate/Site FK merely to clear the global HTTP 409.

This helper remains scoped to local trigger discovery and shall not grow
into alternate backup orchestration, automated task repair, or a downloader.
