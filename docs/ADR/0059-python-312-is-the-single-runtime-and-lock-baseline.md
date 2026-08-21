# ADR 0059: Python 3.12 is the single runtime and lock baseline

## Status
Accepted

## Context
Backend lockfiles had been generated with Python 3.14 while CI and container runtime targeted Python 3.12. That made lockfile freshness checks non-deterministic and risked environment-specific dependency drift.

## Decision
- Python 3.12 is the single backend baseline for:
  - lockfile generation
  - CI
  - Docker runtime
  - Cloud Run runtime
- `pyproject.toml` constrains the project to Python `>=3.12,<3.13`.
- Lock freshness checks compile with the same baseline version and compare against checked-in lockfiles.

## Consequences
- Lock regeneration is reproducible across development and CI.
- Container/runtime compatibility is easier to reason about because one interpreter family owns the backend baseline.
- Future Python upgrades must be deliberate repo-wide decisions rather than ad-hoc local tooling drift.
