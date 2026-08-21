# ADR 0055: Alembic owns runtime schema evolution

## Status
Accepted

## Context
The project already had SQLAlchemy models, but runtime migration ownership was not represented by a real Alembic environment and revision chain. Relying on metadata creation outside isolated tests/tools would make Cloud SQL promotion and rerun semantics unsafe.

## Decision
- Runtime schema evolution is owned by Alembic revisions.
- The repository keeps:
  - `alembic.ini`
  - `migrations/env.py`
  - `migrations/script.py.mako`
  - checked-in revisions under `migrations/versions/`
- Production and CI validation should run `alembic upgrade head` against a clean database.
- `Base.metadata.create_all()` remains acceptable only in isolated tests or one-off tooling where no production migration ownership is implied.

## Consequences
- Schema changes become reviewable, ordered, and replayable.
- Cloud SQL bootstrap can validate upgrade behavior before serving traffic.
- Tests and utility scripts must distinguish between test-only bootstrap and production migration paths.
