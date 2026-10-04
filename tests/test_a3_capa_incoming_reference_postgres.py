"""CI-only PostgreSQL round-trip coverage for A3 migration 20261003_0018.

The main CI workflow provisions a fresh PostgreSQL service and upgrades it to
head before this test runs.  This test then verifies the immediate downgrade
and re-upgrade contract without allowing a local runtime database fallback.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


if os.environ.get("A3_POSTGRES_MIGRATION_INTEGRATION") != "1":
    pytest.skip(
        "set A3_POSTGRES_MIGRATION_INTEGRATION=1 for the disposable PostgreSQL migration gate",
        allow_module_level=True,
    )

DATABASE_URL = os.environ.get("DATABASE_URL", "")
EXPECTED_DATABASE = os.environ.get("A3_DISPOSABLE_POSTGRES_DATABASE", "")
if not DATABASE_URL.startswith("postgresql"):
    raise RuntimeError("A3 migration gate requires an explicit PostgreSQL DATABASE_URL")
if not EXPECTED_DATABASE or make_url(DATABASE_URL).database != EXPECTED_DATABASE:
    raise RuntimeError("A3 migration gate requires its explicitly named disposable database")


def _alembic(*arguments: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        check=True,
        env={**os.environ, "DATABASE_URL": DATABASE_URL},
    )


def _revision(engine) -> str:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _incoming_reference_column(engine):
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT data_type, character_maximum_length, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name = 'capa_cycle' "
                "AND column_name = 'incoming_reference'"
            )
        ).one_or_none()


def test_a3_capa_incoming_reference_downgrades_and_reupgrades_on_disposable_postgres() -> None:
    engine = create_engine(DATABASE_URL, future=True)
    try:
        assert engine.dialect.name == "postgresql"
        assert _revision(engine) == "20261003_0018"
        assert _incoming_reference_column(engine) == ("character varying", 255, "YES")

        _alembic("downgrade", "20260929_0017")
        assert _revision(engine) == "20260929_0017"
        assert _incoming_reference_column(engine) is None

        _alembic("upgrade", "20261003_0018")
        assert _revision(engine) == "20261003_0018"
        assert _incoming_reference_column(engine) == ("character varying", 255, "YES")
    finally:
        engine.dispose()
