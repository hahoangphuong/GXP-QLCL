from __future__ import annotations

import pytest

from migrations.target_resolution import resolve_alembic_database_url


def test_explicit_postgres_url_has_precedence_in_local_postgres_mode():
    assert resolve_alembic_database_url(
        {"DB_MODE": "local_postgres", "DATABASE_URL": "postgresql+psycopg://u:p@host/db"},
        "sqlite:///artifacts/alembic-dev.db",
    ).startswith("postgresql+")
def test_explicit_postgres_url_has_precedence_in_cloud_sql_mode():
    assert resolve_alembic_database_url(
        {"DB_MODE": "cloud_sql", "DATABASE_URL": "postgresql+psycopg://u:p@host/db"},
        "sqlite:///artifacts/alembic-dev.db",
    ).startswith("postgresql+")


def test_explicit_sqlite_url_has_precedence():
    assert resolve_alembic_database_url(
        {"DB_MODE": "local_postgres", "DATABASE_URL": "sqlite:///explicit.db"},
        "sqlite:///artifacts/alembic-dev.db",
    ) == "sqlite:///explicit.db"


def test_local_development_without_database_url_uses_ini_fallback():
    assert resolve_alembic_database_url({}, "sqlite:///artifacts/alembic-dev.db") == "sqlite:///artifacts/alembic-dev.db"


def test_managed_postgres_without_database_url_fails_closed_without_database_name_assumption():
    with pytest.raises(RuntimeError, match="DATABASE_URL is missing"):
        resolve_alembic_database_url({"DB_MODE": "local_postgres", "DB_NAME": "any_name"}, "sqlite:///artifacts/alembic-dev.db")


def test_cloud_sql_without_database_url_fails_closed():
    with pytest.raises(RuntimeError, match="refuses sqlalchemy.url fallback"):
        resolve_alembic_database_url({"DB_MODE": "cloud_sql"}, "sqlite:///artifacts/alembic-dev.db")


def test_whitespace_database_url_is_missing_in_managed_runtime():
    with pytest.raises(RuntimeError, match="DATABASE_URL is missing"):
        resolve_alembic_database_url({"DB_MODE": "local_postgres", "DATABASE_URL": "  "}, "sqlite:///artifacts/alembic-dev.db")
