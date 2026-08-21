# Phase 1 Target Schema Baseline

This migration placeholder documents the first concrete target schema baseline.

Current source of truth:
- SQLAlchemy metadata in `backend/app/db/models/phase1.py`
- rendered PostgreSQL DDL in `artifacts/phase1/schema.sql`

Why this is a documentation placeholder instead of executable Alembic revision:
- Phase 1 in this repository is still schema-definition and migration-contract work.
- We are not applying a live database migration yet.
- A real Alembic environment should be created together with Phase 2 staging database bootstrap.
