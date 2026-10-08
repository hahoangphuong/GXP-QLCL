"""Disposable PostgreSQL source schema, provenance, and B6 0022 apply probe.

Supports only an explicitly allowlisted 0022 revision on a fresh gxp_b6c_test_
database. A plan from 0017 remains unusable after a revision change.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, Certificate, Company, ProductionLine, Site
from backend.app.domain.production_line_canonical_state import canonical_state_digest_pair, export_canonical_state
from backend.app.domain.production_line_population import (
    build_production_line_population_plan, canonical_artifact_bytes,
)
from backend.app.domain.production_line_population_b6j import build_population_plan
from backend.app.domain.production_line_population_writer_b6j import ProductionLinePopulationApplyError, _verify_target, guarded_apply
from backend.app.domain.production_line_review_workspace import REVIEW_SCHEMA_VERSION, candidate_set_digest


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



def _row(number: int, cells: dict[int, object]) -> dict[str, object]:
    return {"source_row_number": number, "cells": [
        {"column_ordinal": key, "raw_value": value} for key, value in cells.items()
    ]}


def _snapshot() -> dict[str, object]:
    return {"schema_version": "legacy-workbook-snapshot/v2", "sheets": [
        {"sheet_name": "db.ktra", "raw_rows": [
            _row(4, {1: "ID", 2: "LOẠI KT", 3: "ID CƠ SỞ", 4: "MÃ DC", 5: "Ngày K.tra"}),
            _row(5, {1: 920022, 2: "GMP", 3: 920022, 4: "LINE-1", 5: "05/01/2026"}),
            _row(6, {1: 920023, 2: "GMP", 3: 920022, 4: "LINE-2", 5: "20/01/2026"}),
        ]},
        {"sheet_name": "db.cc", "raw_rows": [
            _row(4, {1: "ID", 4: "LOẠI CC", 5: "ID ĐỢT KTRA", 8: "ID CƠ SỞ", 9: "MÃ DC", 10: "Ngày cấp CC"}),
            _row(5, {1: 920022, 4: "GMP", 5: 920022, 8: 920022, 9: "LINE-1", 10: "01/02/2026"}),
            _row(6, {1: 920023, 4: "GMP", 5: 920023, 8: 920022, 9: "LINE-2", 10: "01/02/2026"}),
        ]},
    ]}


def _plan(state: dict[str, object]) -> dict[str, object]:
    source_sha256, _ = canonical_state_digest_pair(state)
    snapshot = _snapshot()
    snapshot_sha256 = sha256(canonical_artifact_bytes(snapshot)).hexdigest()
    preliminary = build_population_plan(
        snapshot, snapshot_sha256=snapshot_sha256, canonical_state=state,
        canonical_state_sha256=source_sha256, candidate_set_sha256="b" * 64,
    )
    items = [{
        "candidate_key": candidate["candidate_key"],
        "source_site_legacy_id": candidate["legacy_site_id"],
        "canonical_site_id": candidate["canonical_site_id"],
        "canonical_line_text": candidate["canonical_line_code"],
        "source_case_ids": candidate["source_case_ids"],
        "source_certificate_ids": candidate["source_certificate_ids"],
        "case_count": len(candidate["source_case_ids"]),
        "certificate_count": len(candidate["source_certificate_ids"]),
        "existing_production_line_id": candidate["existing_production_line_id"],
        "review_tags": [], "review_status": "PENDING_HUMAN_REVIEW",
    } for candidate in preliminary["candidates"]]
    roster = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "artifact_kind": "production_line_physical_identity_review_roster",
        "generated_at": None,
        "planner_version": "b6h-production-line-population/v2",
        "legacy_snapshot_sha256": snapshot_sha256,
        "canonical_state_sha256": source_sha256,
        "candidate_set_sha256": candidate_set_digest(items),
        "items": items,
    }
    roster["content_sha256"] = sha256(canonical_artifact_bytes(roster)).hexdigest()
    return build_population_plan(
        snapshot, snapshot_sha256=snapshot_sha256, canonical_state=state,
        canonical_state_sha256=source_sha256,
        candidate_set_sha256=roster["candidate_set_sha256"],
        candidate_roster=roster,
        candidate_roster_raw_sha256=sha256(canonical_artifact_bytes(roster)).hexdigest(),
    )


def _read_only_state(engine) -> dict[str, object]:
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            with Session(bind=connection, autoflush=False) as session:
                return export_canonical_state(session)


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
        first = Case(
            legacy_inspection_id=920022, site_id=site.id, gxp_type="GMP",
            state=CaseState.INSPECTION_COMPLETED, scope_code="LINE-1",
            production_line_id=line.id,
        )
        second = Case(
            legacy_inspection_id=920023, site_id=site.id, gxp_type="GMP",
            state=CaseState.INSPECTION_COMPLETED, scope_code="LINE-2",
        )
        session.add_all((first, second))
        session.flush()
        session.add_all((
            Certificate(
                legacy_certificate_id=920022, case_id=first.id, site_id=site.id,
                certificate_type="GMP", line_code="LINE-1", production_line_id=line.id,
            ),
            Certificate(
                legacy_certificate_id=920023, case_id=second.id, site_id=site.id,
                certificate_type="GMP", line_code="LINE-2",
            ),
        ))
        session.commit()
    state = _read_only_state(engine)
    assert state["source_alembic_revision"] == "20260929_0017"
    assert len(state["sites"]) == len(state["existing_production_lines"]) == 1
    assert len(state["cases"]) == len(state["certificates"]) == 2
    return state


def test_0022_schema_is_source_stable_and_guarded_population_is_revision_bound():
    engine = create_engine(DATABASE_URL, future=True)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260929_0017"
        reference_schema = _schema_signature(engine)
        state_0017 = _seed_and_snapshot(engine)
        plan_0017 = _plan(state_0017)
        assert plan_0017["source_alembic_revision"] == "20260929_0017"
    finally:
        engine.dispose()

    _upgrade("20261008_0022")

    engine = create_engine(DATABASE_URL, future=True)
    try:
        with Session(engine) as session:
            assert session.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20261008_0022"
        assert _schema_signature(engine) == reference_schema, "B6 owner tables drifted from revision 0017"
        state_0022 = _read_only_state(engine)
        assert state_0022["source_alembic_revision"] == "20261008_0022"
        for field in ("sites", "existing_production_lines", "cases", "certificates", "transformations"):
            assert state_0022[field] == state_0017[field], f"B6 canonical {field} drifted across schema upgrade"
        # The B6H physical-identity discovery/review owner must consume the
        # same 0022 export, not only the separately approved B6J migration plan.
        b6h_plan = build_production_line_population_plan(
            _snapshot(), snapshot_sha256="a" * 64,
            canonical_state=state_0022,
            canonical_state_sha256=canonical_state_digest_pair(state_0022)[0],
        )
        assert b6h_plan["discovery"]["candidates"]
        plan_0022 = _plan(state_0022)
        assert plan_0022["source_alembic_revision"] == "20261008_0022"
        by_code = {item["canonical_line_code"]: item for item in plan_0022["candidates"]}
        assert by_code["LINE-1"]["classification"] == "MAP_TO_EXISTING_PRODUCTION_LINE"
        assert by_code["LINE-2"]["classification"] == "CREATE_NEW_PRODUCTION_LINE"
        for kind in ("case_links", "certificate_links"):
            existing = next(item for item in plan_0022[kind] if item["legacy_id"] == 920022)
            assert existing["classification"] == "NOT_APPLICABLE"
            assert existing["block_reason"] == "ALREADY_LINKED_TO_PLANNED_LINE"
            new_link = next(item for item in plan_0022[kind] if item["legacy_id"] == 920023)
            assert new_link["classification"] == "LINK_TO_NEW_LINE"
            assert new_link["block_reason"] is None
        old_line2 = next(item for item in plan_0017["candidates"] if item["canonical_line_code"] == "LINE-2")
        assert by_code["LINE-2"]["proposed_production_line_id"] != old_line2["proposed_production_line_id"]

        with Session(engine) as session:
            with pytest.raises(ProductionLinePopulationApplyError, match="target Alembic revision differs from sealed plan"):
                _verify_target(session, expected_database_name=DATABASE_NAME, expected_revision="20260929_0017")
            with pytest.raises(ProductionLinePopulationApplyError, match="target Alembic revision differs from sealed plan"):
                guarded_apply(session, plan_0017, expected_database_name=DATABASE_NAME, apply=True)
            session.rollback()
        with Session(engine) as session:
            dry = guarded_apply(session, plan_0022, expected_database_name=DATABASE_NAME, apply=False)
            assert (dry["would_create_production_lines"], dry["would_link_cases"], dry["would_link_certificates"]) == (1, 1, 1)
            session.rollback()
        assert _read_only_state(engine) == state_0022, "Dry-run modified canonical state"

        with Session(engine) as session:
            assert guarded_apply(session, plan_0022, expected_database_name=DATABASE_NAME, apply=True)["status"] == "APPLIED"
            session.commit()
        with Session(engine) as session:
            line2 = session.scalar(select(ProductionLine).where(ProductionLine.code == "LINE-2"))
            assert line2 is not None
            assert line2.id == by_code["LINE-2"]["proposed_production_line_id"]
            assert session.scalar(select(Case).where(Case.legacy_inspection_id == 920023)).production_line_id == line2.id
            assert session.scalar(select(Certificate).where(Certificate.legacy_certificate_id == 920023)).production_line_id == line2.id
            assert session.scalar(select(ProductionLine).where(ProductionLine.code == "LINE-1")).id == by_code["LINE-1"]["existing_production_line_id"]
            session.rollback()
        with Session(engine) as session:
            with pytest.raises(ProductionLinePopulationApplyError, match="global canonical state changed"):
                guarded_apply(session, plan_0022, expected_database_name=DATABASE_NAME, apply=True)
            session.rollback()
    finally:
        engine.dispose()
