from __future__ import annotations

from collections.abc import Mapping

from backend.app.config import resolve_db_mode


MANAGED_POSTGRES_MODES = {"local_postgres", "cloud_sql"}


def resolve_alembic_database_url(environment: Mapping[str, str], ini_url: str) -> str:
    """Resolve Alembic's target without allowing managed runtimes to fall back."""
    explicit_url = str(environment.get("DATABASE_URL", "")).strip()
    if explicit_url:
        return explicit_url
    if resolve_db_mode(dict(environment)) in MANAGED_POSTGRES_MODES:
        raise RuntimeError(
            "DATABASE_URL is missing; Alembic refuses sqlalchemy.url fallback in a managed PostgreSQL runtime."
        )
    return ini_url
