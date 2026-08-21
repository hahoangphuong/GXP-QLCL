# ADR 0048: Production bootstrap fails closed

## Status
Approved

## Context
The backend bootstrap path previously allowed local-development defaults such as SQLite, `header_stub`, and missing storage to remain reachable from the same `create_app()` entrypoint used for Cloud Run production packaging.

That created a risk where production env configuration existed but was silently bypassed by local defaults.

## Decision
- `create_app()` must default `database_url` to `None`, not a hardcoded SQLite URL.
- Production startup must fail closed when:
  - database resolves to SQLite
  - auth mode is `header_stub`
  - trusted-header fallback is enabled
  - role source is not database-owned
  - storage is missing or fake
- Development/test may still intentionally use SQLite and fake/local storage.

## Consequences
- Local convenience remains available, but only outside production mode.
- Cloud Run rollout fails earlier and more explicitly when invariants are broken.
