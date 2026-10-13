"""DDK migration 0022->0023 and VM-equivalent read-only postflight on disposable CI PG.

This test must never run against any VM or non-CI database. A deliberately
separate ephemeral PostgreSQL DB named gxp_legacy_rehearsal is created inside
the GitHub Actions postgres:16 SERVICE ONLY, then always discarded.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
DISPOSABLE_DB = "gxp_legacy_rehearsal"
SOURCE_DB = "gxp_qlcl_test"
FILE = ROOT / "scripts/verify_ddk_gxp_0023_postflight_readonly.sql"


def _guarded_ci_database_url():
    if os.environ.get("GXP_DDK_CI_POSTGRES_INTEGRATION") != "1":
        pytest.skip("PostgreSQL 0023 integration enabled only on guarded disposable CI")
    assert os.environ.get("GITHUB_ACTIONS") == "true", "Not a GitHub Actions runner"
    url = make_url(os.environ["DATABASE_URL"])
    assert url.get_backend_name() == "postgresql"
    assert url.host == "127.0.0.1" and url.port == 5432
    assert url.database == SOURCE_DB
    assert url.username == "postgres" and url.password == "postgres"
    return url


def _postflight_do_block():
    source = FILE.read_text(encoding="utf-8")
    opening = "DO $ddk_0023_postflight$"
    closing = "$ddk_0023_postflight$;"
    assert source.count(opening) == source.count(closing) == 1
    return opening + source.split(opening, 1)[1].split(closing, 1)[0] + closing


def _run_migration(url, revision):
    env = dict(os.environ)
    env["DATABASE_URL"] = url.render_as_string(hide_password=False)
    env["DB_MODE"] = "local_postgres"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=180,
        check=False,
    )
    assert result.returncode == 0, f"Disposable migration failed at {revision}: {result.stderr[-1000:]}"


def _evaluate_postflight(conn):
    # Run the file's exact DO-block through psycopg/SQLAlchemy, without psql
    # meta-commands. The assertion proves real PostgreSQL execution, unlike
    # static syntax guards or the SQLite schema compiler.
    with conn.connect() as cx:
        try:
            cx.exec_driver_sql("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cx.exec_driver_sql(_postflight_do_block())
        finally:
            cx.rollback()


def test_real_pg_0023_schema_and_postflight_with_disposable_rehearsal_name():
    source = _guarded_ci_database_url()
    target = source.set(database=DISPOSABLE_DB)
    admin = create_engine(source, isolation_level="AUTOCOMMIT")
    created = False
    try:
        with admin.connect() as cx:
            exists = cx.execute(text(
                "SELECT 1 FROM pg_database WHERE datname = :name"
            ), {"name": DISPOSABLE_DB}).scalar()
            assert exists is None, "Disposable rehearsal CI DB unexpectedly already exists"
            cx.exec_driver_sql(f'CREATE DATABASE "{DISPOSABLE_DB}"')
            created = True
        _run_migration(target, "20261008_0022")
        engine = create_engine(target)
        try:
            with pytest.raises(Exception, match="Expected exactly Alembic revision 0023"):
                _evaluate_postflight(engine)
        finally:
            engine.dispose()
        _run_migration(target, "20261012_0023")
        engine = create_engine(target)
        try:
            _evaluate_postflight(engine)
            with engine.connect() as cx:
                assert cx.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one() == "20261012_0023"
                assert cx.execute(text("SELECT count(*) FROM public.business_eligibility_gxp_source_group")).scalar_one() == 0
                assert cx.execute(text("SELECT count(*) FROM public.business_eligibility_gxp_reference_evidence")).scalar_one() == 0
        finally:
            engine.dispose()
    finally:
        if created:
            with admin.connect() as cx:
                cx.exec_driver_sql(f'DROP DATABASE "{DISPOSABLE_DB}" WITH (FORCE)')
        admin.dispose()
