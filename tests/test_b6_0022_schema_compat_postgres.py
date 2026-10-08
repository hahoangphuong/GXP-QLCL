"""Disposable PostgreSQL schema-drift and revision-gate probe for B6 at 0022.

This does NOT authorize B6 writer/exporter to run on 0022.  It documents
whether later migrations leave the B6 source tables/rows unchanged, while
the explicit 0017 revision gate must remain fail-closed.
"""
from __future__ import annotations

from datetime import date
import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, Certificate, Company, ProductionLine, Site
from backend.app.domain.production_line_canonical_state import export_canonical_state
from backend.app.domain.production_line_population import ProductionLinePlanningError
from backend.app.domain.production_line_population_writer_b6j import ProductionLinePopulationApplyError, _verify_target


if os.environ.get("B6_0022_COMPAT_INTEGRATION") != "1":
    pytest.skip("set B6_0022_COMPAT_INTEGRATION=1 for disposable schema probe", allow_module_level=True)

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or make_url(DATABASE_URL).get_backend_name() != "postgresql":
    raise RuntimeError("B6 schema compatibility probe requires PostgreSQL DATABASE_URL")
DATABASE_NAME = make_url(DATABASE_URL).database or ""
if not DATABASE_NAME.startswith("gxp_b6c_test_"):
    raise RuntimeError("B6 schema compatibility probe requires a disposable gxp_b6c_test_ database")

# Only tables read or written by the B6H/B6J identity projection/writer.
SOURCE_TABLES = ("site", "production_line", "case", "certificate", "production_line_transformation")


def _schema_signature(engine):
    # Compare actual PostgreSQL column/constraint/index definitions, not ORM
    # metadata (which may already describe the latest schema).
    with engine.connect() as connection:
        result = {}
        for table in SOURCE_TABLES:
            columns = connection.execute(text("""
                SELECT a.attname, format_type(a.atttypid, a.atttypmod),
                       a.attnotnull, pg_get_expr(d.adbin, d.adrelid)
                FROM pg_attribute AS a
                LEFT JOIN pg_attrdef AS d
                  ON d.adrelid = a.attrelid AND d.adnum = a.attnum
                WHERE a.attrelid = to_regclass(:name)
                  AND a.attnum > 0 AND NOT a.attisdropped
                ORDER BY a.attnum
            """), {"name": table}).all()
            constraints = connection.execute(text("""
                SELECT c.conname, c.contype, pg_get_constraintdef(c.oid)
                FROM pg_constraint AS c
                WHERE c.conrelid = to_regclass(:name)
                ORDER BY c.conname
            """), {"name": table}).all()
            indexes = connection.execute(text("""
                SELECT indexname, indexdef FROM pg_indexes
                WHERE schemaname = current_schema() AND tablename = :name
                ORDER BY indexname
            """), {"name": table}).all()
            assert columns, f"Missing protected source table {table}"
            result[table] = {
                "columns": [tuple(row) for row in columns],
                "constraints": [tuple(row) for row in constraints],
                "indexes": [tuple(row) for row in indexes],
            }
        return result


def _upgrade(revision: str) -> None:
    environment = {**os.environ, "DATABASE_URL": DATABASE_URL}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", revision], check=True, env=environment)


def _seed_and_snapshot(engine):
    with Session(engine) as session:
        company = Company(legal_name="B6 0022 disposable schema probe")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, legacy_site_id=920022, site_name="B6 0022 test site")
        session.add(site)
        session.flush()
        line = ProductionLine(site_id=site.id, code="LINE-1", effective_from=date(2026, 1, 1))
        session.add(line)
        session.flush()
        case = Case(legacy_inspection_id=920022, site_id=site.id, gxp_type="GMP",
                    state=CaseState.INSPECTION_COMPLETED, scope_code="LINE-1", production_line_id=line.id)
        session.add(case)
        session.flush()
        certificate = Certificate(legacy_certificate_id=920022, case_id=case.id,
                                  site_id=site.id, certificate_type="GMP",
                                  line_code="LINE-1", production_line_id=line.id)
        session.add(certificate)
        session.commit()
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        with Session(bind=connection) as session:
            state = export_canonical_state(session)
            assert state["source_alembic_revision"] == "20260929_0017"
            assert len(state["sites"]) == len(state["existing_production_lines"]) == 1
            assert len(state["cases"]) == len(state["certificates"]) == 1
            return {field: state[field] for field in
                    ("sites", "existing_production_lines", "cases", "certificates", "transformations")}


def test_0022_schema_is_source_stable_but_revision_gate_remains_closed():
    engine = create_engine(DATABASE_URL, future=True)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260929_0017"
        reference_schema = _schema_signature(engine)
        expected_rows = _seed_and_snapshot(engine)
    finally:
        engine.dispose()

    _upgrade("20261008_0022")

    engine = create_engine(DATABASE_URL, future=True)
    try:
        with Session(engine) as session:
            assert session.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20261008_0022"
        assert _schema_signature(engine) == reference_schema, "B6 owner tables drifted from revision 0017"
        # SELECTs are diagnostic only. Canonical-state exporter must continue
        # to reject 0022 until a separately reviewed compatibility release.
        with Session(engine) as session:
            assert [row.id for row in session.scalars(select(ProductionLine))] == [
                row["id"] for row in expected_rows["existing_production_lines"]
            ]
            assert [row.id for row in session.scalars(select(Case))] == [
                row["id"] for row in expected_rows["cases"]
            ]
            assert [row.id for row in session.scalars(select(Certificate))] == [
                row["id"] for row in expected_rows["certificates"]
            ]
            with pytest.raises(ProductionLinePlanningError, match="exact Alembic 20260929_0017"):
                export_canonical_state(session, require_read_only=False)
            with pytest.raises(ProductionLinePopulationApplyError, match="exact Alembic 20260929_0017"):
                _verify_target(session, expected_database_name=DATABASE_NAME)
    finally:
        engine.dispose()
