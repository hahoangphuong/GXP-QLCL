# Existing PostgreSQL backup-pair offline preflight — historical GMP Case reconciliation

**Status: Source-only Draft / NOT a backup, restore, or database-write authorization.**

This helper supports Issue #6 and is independent of the exact-row GMP 376 → Case 380 planning PR #34. It never runs `pg_dump`, `pg_restore --dbname`, SQL, GCS or systemd. It does **not** enable the disabled scheduled backup service.

`python -m tools.audit_existing_pg_backup_pair_readonly --backup /path/to/existing.dump`

Input must be an **already existing local** custom PostgreSQL dump and adjacent `.dump.sha256` produced by the existing VM backup script, or a transferred pair with identical basename. It rejects missing, untrusted/symlinked, mismatched, malformed, and changing files; checks SHA256 locally; then runs only `pg_restore --list` without echoing archive content.

A successful result means exactly `BACKUP_PAIR_INTEGRITY_AND_TOC_VERIFIED_ONLY`. It **does not** establish:
- Which physical PostgreSQL database generated the backup, including whether it was `gxp_legacy_rehearsal`.
- Whether the backup is recent enough for the desired FK correction.
- Whether a complete restore into a fresh disposable DB succeeds or preserves relevant Case/Certificate/Alembic data.
- Whether anyone authorized a database update or confirmed rollback readiness.

These are separate, indispensable requirements. Do not use checksum/Toc success as a surrogate for disposable restore rehearsal. This helper does not read or write the private one-row Case 380 plan and never publishes UUIDs/credentials.

If no approved recent backup exists, report **BLOCKED** and stop. Do not generate/download/copy a new backup, use GCS, or enable cron/timers without explicit operator permission. Do not run the existing restore script against `gxp_legacy_rehearsal`, `gxp_qlcl`, or any existing database. The current repository restore owner explicitly requires a newly created disposable `*_restore` target.

The whole Issue #6 remains open: GMP 1037/1180 require independent historical multi-Site inspection/certification scope and address review. Repairing 376 alone cannot resolve the complete Search 409.
