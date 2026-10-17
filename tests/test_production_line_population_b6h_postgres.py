"""Opt-in PostgreSQL safety tests for the B6H canonical-state exporter."""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.app.domain.production_line_canonical_state import export_canonical_state
from backend.app.domain.production_line_population import canonical_artifact_bytes
from sqlalchemy.engine import make_url


if os.environ.get("B6H_POSTGRES_INTEGRATION") != "1":
    pytest.skip("set B6H_POSTGRES_INTEGRATION=1 for disposable PostgreSQL safety coverage", allow_module_level=True)

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or make_url(DATABASE_URL).get_backend_name() != "postgresql":
    raise RuntimeError("B6H PostgreSQL integration requires an explicit PostgreSQL DATABASE_URL")
if not (make_url(DATABASE_URL).database or "").startswith("gxp_b6h_test_"):
    raise RuntimeError("B6H PostgreSQL integration requires a disposable gxp_b6h_test_ database")


def test_disposable_database_exporter_is_read_only_and_deterministic():
    engine = create_engine(DATABASE_URL, future=True)
    try:
        with engine.connect() as connection:
            before = connection.execute(text("SELECT count(*) FROM site")).scalar_one()
        outputs = []
        for _ in range(2):
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                    assert connection.execute(text("SHOW transaction_read_only")).scalar_one() == "on"
                    assert connection.execute(text("SELECT current_database()")).scalar_one().startswith("gxp_b6h_test_")
                    outputs.append(canonical_artifact_bytes(export_canonical_state(Session(bind=connection))))
                finally:
                    transaction.rollback()
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM site")).scalar_one() == before
        assert outputs[0] == outputs[1]
    finally:
        engine.dispose()
