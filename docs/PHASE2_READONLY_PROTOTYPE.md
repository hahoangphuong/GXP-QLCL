# Phase 2 Read-Only Prototype

## Scope completed
- Read-only import from workbook snapshot into local relational database artifact
- Reconciliation report between source workbook counts and imported target counts
- Minimal read-only FastAPI surface for company, site, and case listing/search

## Implementation
- Import runner: `tools/run_phase2_import.py`
- Import logic: `backend/app/domain/phase2_import.py`
- Workbook reader: `backend/app/domain/legacy_snapshot.py`
- Read-only API: `backend/app/main.py`

## Produced artifacts
- `artifacts/phase2/staging_readonly.db`
- `artifacts/phase2/reconciliation.md`
- `artifacts/phase2/reconciliation.json`

## Current prototype mode
- Local prototype database uses SQLite for repeatable workspace execution.
- The target runtime database remains PostgreSQL / Cloud SQL.
- No Synology writes are performed.
- No legacy files are modified.

## Observed reconciliation outcome on 2026-08-13
- `db.cty`: imported fully
- `db.cso`, `db.ktra`, `db.cc`, `db.dkkd`, `db.Tdoi`, `db.Tdoi2`: imported partially with skipped rows
- Skips are caused by missing or unresolved normalized foreign-key dependencies during Phase 2 import
- `db.cc` now supports valid certificate rows without `ID ĐỢT KTRA` when `ID CƠ SỞ` resolves; these import as non-case-backed certificates instead of being skipped automatically.

## Prototype read-only routes
- `GET /healthz`
- `GET /companies`
- `GET /sites`
- `GET /cases`

## Known limitations
- The local snapshot reader currently exposes mojibake header names through COM, so importer normalizes known aliases explicitly.
- No PostgreSQL staging instance is configured in this workspace yet.
- DDKD-to-certificate links are present structurally, but current workbook snapshot import did not resolve any valid links after normalization.
- No document rows are imported yet; document generation replacement belongs to later phases.
