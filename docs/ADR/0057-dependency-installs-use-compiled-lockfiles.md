# ADR 0057: Dependency installs use compiled lockfiles

## Status
Accepted

## Context
The backend runtime manifest and frontend package manifest were sufficient for local experimentation, but not for reproducible installs across Cloud Run builds, CI, and teammate machines.

## Decision
- Backend Python dependencies are resolved into checked-in compiled lockfiles:
  - `backend/requirements.runtime.lock.txt`
  - `backend/requirements.dev.lock.txt`
- Runtime container builds install from the runtime lockfile.
- CI verifies the lockfiles are fresh relative to their source manifests.
- Frontend installs remain pinned by:
  - exact `packageManager`
  - checked-in `pnpm-lock.yaml`
  - `pnpm install --frozen-lockfile`

## Consequences
- Runtime and test environments become more reproducible.
- Drift between source manifests and resolved locks is caught in CI instead of during deployment.
- Dependency upgrades require intentional manifest and lock refresh rather than accidental floating resolution.
