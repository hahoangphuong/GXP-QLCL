# ADR 0052: Compute Engine VM Is The Current Production Baseline

## Status
Accepted

## Context
The repository previously treated Cloud Run + Cloud SQL + external bridge as the active production path. The operator now wants the primary production deployment to be a single small Compute Engine VM that hosts:

- frontend production assets
- backend/API
- local PostgreSQL
- Tailscale
- direct SMB access to Synology DS115j

while keeping the full Cloud Run / Cloud SQL code path dormant in the repository for future rollback or reactivation.

## Decision
- Current production baseline is `Compute Engine VM + local PostgreSQL + direct SMB over Tailscale`.
- Structured business data lives in local PostgreSQL on the VM.
- File binaries remain on Synology only.
- `StorageService` remains the business-layer abstraction.
- Active VM production storage class baseline is `synology_smb`.
- Active VM production DB baseline is `DB_MODE=local_postgres`.
- Active VM production auth baseline is `AUTH_PROVIDER=google_oidc`.
- Cloud Run + Cloud SQL + external bridge remain supported as dormant infrastructure options, not the default production path.

## Consequences
- Production deployment scripts, docs, and validators must default to VM flow.
- Cloud Run deployment code must stay isolated so it does not block VM production deploy.
- Backup responsibility shifts to operator-managed PostgreSQL logical backups, with Cloud SQL retained temporarily as a rollback option.
