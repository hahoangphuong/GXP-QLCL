"""Opt-in, real PostgreSQL B6J planner/writer integration coverage."""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import os

import pytest
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, Certificate, Company, ProductionLine, Site
from backend.app.domain.production_line_population import canonical_artifact_bytes, canonical_json_bytes
from backend.app.domain.production_line_population_b6j import build_population_plan, plan_digest
from backend.app.domain.production_line_population_writer_b6j import ProductionLinePopulationApplyError, guarded_apply
from backend.app.domain.production_line_review_workspace import REVIEW_SCHEMA_VERSION, candidate_set_digest


if os.environ.get("B6J_POSTGRES_INTEGRATION") != "1":
    pytest.skip("set B6J_POSTGRES_INTEGRATION=1 for disposable B6J coverage", allow_module_level=True)
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or make_url(DATABASE_URL).get_backend_name() != "postgresql":
    raise RuntimeError("B6J integration requires an explicit PostgreSQL DATABASE_URL")
DATABASE_NAME = make_url(DATABASE_URL).database or ""
if not DATABASE_NAME.startswith("gxp_b6j_test_"):
    raise RuntimeError("B6J integration requires a gxp_b6j_test_ database")


def _row(number: int, cells: dict[int, object]) -> dict[str, object]:
    return {"source_row_number": number, "cells": [{"column_ordinal": key, "raw_value": value} for key, value in cells.items()]}


def _snapshot() -> dict[str, object]:
    return {"schema_version": "legacy-workbook-snapshot/v2", "sheets": [
        {"sheet_name": "db.ktra", "raw_rows": [
            _row(4, {1: "ID", 2: "LOẠI KT", 3: "ID CƠ SỞ", 4: "MÃ DC", 5: "Ngày K.tra"}),
            _row(5, {1: 10, 2: "GMP", 3: 7, 4: "A", 5: "17-19/07/2026"}),
            _row(6, {1: 11, 2: "GMP", 3: 7, 4: "B", 5: "-"}),
            _row(7, {1: 12, 2: "GMP", 3: 8, 4: "A", 5: "20/07/2026"}),
            _row(8, {1: 13, 2: "GMP", 3: 7, 4: None, 5: "21/07/2026"}),
            _row(9, {1: 14, 2: "GMP", 3: 7, 4: "C", 5: "-"}),
            _row(10, {1: 15, 2: None, 3: 7, 4: "D", 5: "22/07/2026"}),
        ]},
        {"sheet_name": "db.cc", "raw_rows": [
            _row(4, {1: "ID", 4: "LOẠI CC", 5: "ID ĐỢT KTRA", 8: "ID CƠ SỞ", 9: "MÃ DC", 10: "Ngày cấp CC"}),
            _row(5, {1: 20, 4: "GMP", 5: 10, 8: 7, 9: "A", 10: "2026-08-21"}),
            _row(6, {1: 21, 4: "GMP", 5: 11, 8: 7, 9: "B", 10: "2020-01-01"}),
            _row(7, {1: 22, 4: "GMP", 5: 12, 8: 7, 9: "A", 10: "2020-01-01"}),
            _row(8, {1: 23, 4: "GMP", 5: 13, 8: 7, 9: None, 10: "2020-01-01"}),
        ]},
    ]}


def _state(session: Session) -> dict[str, object]:
    sites = list(session.scalars(select(Site).order_by(Site.legacy_site_id)))
    cases = list(session.scalars(select(Case).order_by(Case.legacy_inspection_id)))
    certificates = list(session.scalars(select(Certificate).order_by(Certificate.legacy_certificate_id)))
    state: dict[str, object] = {"schema_version": "production-line-canonical-state/v1", "exported_at": None, "source_database_identity": {"database_name": DATABASE_NAME, "dialect": "postgresql"}, "source_alembic_revision": "20260929_0017", "sites": [{"id": item.id, "legacy_site_id": item.legacy_site_id} for item in sites], "existing_production_lines": [], "cases": [{"id": item.id, "legacy_inspection_id": item.legacy_inspection_id, "site_id": item.site_id, "scope_code_raw": item.scope_code, "production_line_id": item.production_line_id, "row_version": item.row_version} for item in cases], "certificates": [{"id": item.id, "legacy_certificate_id": item.legacy_certificate_id, "case_id": item.case_id, "site_id": item.site_id, "line_code_raw": item.line_code, "production_line_id": item.production_line_id, "row_version": item.row_version} for item in certificates], "physical_line_evidence": [], "transformations": []}
    state["source_state_fingerprint"] = sha256(canonical_json_bytes(state)).hexdigest()
    return state


@pytest.fixture()
def fixture_state():
    engine = create_engine(DATABASE_URL, future=True)
    with Session(engine) as session:
        # The runner owns a disposable database, but each test still resets its
        # own fixture rows so apply results cannot leak into the rollback case.
        session.execute(delete(Certificate))
        session.execute(delete(Case))
        session.execute(delete(ProductionLine))
        session.execute(delete(Site))
        session.execute(delete(Company))
        session.commit()
        company = Company(legal_name="B6J disposable company")
        session.add(company); session.flush()
        site7, site8 = Site(company_id=company.id, legacy_site_id=7, site_name="B6J site 7"), Site(company_id=company.id, legacy_site_id=8, site_name="B6J site 8")
        session.add_all((site7, site8)); session.flush()
        cases = [Case(legacy_inspection_id=identity, site_id=site.id, gxp_type="GMP", scope_code=raw, state=CaseState.INSPECTION_COMPLETED) for identity, site, raw in ((10, site7, "A"), (11, site7, "B"), (12, site8, "A"), (13, site7, None), (14, site7, "C"), (15, site7, "D"))]
        session.add_all(cases); session.flush()
        session.add_all((Certificate(legacy_certificate_id=20, case_id=cases[0].id, site_id=site7.id, certificate_type="GMP", line_code="A"), Certificate(legacy_certificate_id=21, case_id=cases[1].id, site_id=site7.id, certificate_type="GMP", line_code="B"), Certificate(legacy_certificate_id=22, case_id=cases[2].id, site_id=site7.id, certificate_type="GMP", line_code="A"), Certificate(legacy_certificate_id=23, case_id=cases[3].id, site_id=site7.id, certificate_type="GMP", line_code=None)))
        session.commit()
    try:
        yield engine
    finally:
        engine.dispose()


def _plan(session: Session) -> dict[str, object]:
    state = _state(session)
    state_sha256 = sha256(canonical_json_bytes(state)).hexdigest()
    preliminary = build_population_plan(_snapshot(), snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=state_sha256, candidate_set_sha256="b" * 64)
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
    roster: dict[str, object] = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "artifact_kind": "production_line_physical_identity_review_roster",
        "generated_at": None,
        "planner_version": "b6h-production-line-population/v2",
        "legacy_snapshot_sha256": "a" * 64,
        "canonical_state_sha256": state_sha256,
        "candidate_set_sha256": candidate_set_digest(items),
        "items": items,
    }
    roster["content_sha256"] = sha256(canonical_artifact_bytes(roster)).hexdigest()
    return build_population_plan(_snapshot(), snapshot_sha256="a" * 64, canonical_state=state, canonical_state_sha256=state_sha256, candidate_set_sha256=roster["candidate_set_sha256"], candidate_roster=roster, candidate_roster_raw_sha256=sha256(canonical_artifact_bytes(roster)).hexdigest())


def _counts(session: Session) -> tuple[int, int, int]:
    return (session.scalar(select(func.count()).select_from(ProductionLine)), sum(item.production_line_id is not None for item in session.scalars(select(Case))), sum(item.production_line_id is not None for item in session.scalars(select(Certificate))))


def test_postgres_writer_dry_run_apply_and_second_apply(fixture_state):
    with Session(fixture_state) as session:
        assert session.execute(text("SELECT current_database()")).scalar_one() == DATABASE_NAME
        assert session.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260929_0017"
        plan = _plan(session)
        assert plan["summary_counts"]["candidates"] == {"BLOCKED_EFFECTIVE_FROM_UNKNOWN": 1, "CREATE_NEW_PRODUCTION_LINE": 3}
        assert plan["summary_counts"]["cases"] == {"BLOCKED_EFFECTIVE_FROM_UNKNOWN": 1, "BLOCKED_NO_LINE": 1, "LINK_TO_NEW_LINE": 3, "NOT_APPLICABLE": 1}
        assert plan["summary_counts"]["certificates"] == {"BLOCKED_NO_LINE": 1, "BLOCKED_SITE_MISMATCH": 1, "LINK_TO_NEW_LINE": 2}
        before = _counts(session)
        dry = guarded_apply(session, plan, expected_database_name=DATABASE_NAME, apply=False)
        assert (dry["would_create_production_lines"], dry["would_link_cases"], dry["would_link_certificates"]) == (3, 3, 2)
        session.rollback()
    with Session(fixture_state) as session:
        assert _counts(session) == before
        plan = _plan(session)
        assert guarded_apply(session, plan, expected_database_name=DATABASE_NAME, apply=True)["status"] == "APPLIED"
        session.commit()
    with Session(fixture_state) as session:
        lines = list(session.scalars(select(ProductionLine).order_by(ProductionLine.site_id, ProductionLine.code)))
        assert len(lines) == 3
        planned = {item["proposed_production_line_id"]: item for item in plan["candidates"] if item["classification"] == "CREATE_NEW_PRODUCTION_LINE"}
        assert {item.id for item in lines} == set(planned)
        assert {(item.site_id, item.code, item.effective_from) for item in lines} == {(item["canonical_site_id"], item["canonical_line_code"], date.fromisoformat(item["effective_from"])) for item in planned.values()}
        assert len({item.id for item in lines if item.code == "A"}) == 2
        assert _counts(session) == (3, 3, 2)
        assert session.get(Case, session.scalar(select(Case.id).where(Case.legacy_inspection_id == 13))).production_line_id is None
        assert session.get(Case, session.scalar(select(Case.id).where(Case.legacy_inspection_id == 15))).production_line_id is None
        assert session.get(Certificate, session.scalar(select(Certificate.id).where(Certificate.legacy_certificate_id == 22))).production_line_id is None
        forbidden_tables = (
            "production_line_transformation", "production_line_transformation_member",
            "case_scope_phase", "case_scope_revision", "case_scope_revision_block",
            "case_scope_revision_selection", "case_scope_revision_unkeyed_entry",
            "certificate_relationship",
        )
        assert {name: session.execute(text(f"SELECT count(*) FROM {name}")).scalar_one() for name in forbidden_tables} == {name: 0 for name in forbidden_tables}
        with pytest.raises(ProductionLinePopulationApplyError):
            guarded_apply(session, plan, expected_database_name=DATABASE_NAME, apply=True)
        session.rollback()
        assert _counts(session) == (3, 3, 2)


def test_postgres_writer_rejects_resealed_mismatched_link_before_write(fixture_state):
    with Session(fixture_state) as session:
        plan = _plan(session)
        altered = dict(plan)
        altered["case_links"] = [dict(item) for item in plan["case_links"]]
        next(item for item in altered["case_links"] if item["classification"] == "LINK_TO_NEW_LINE")["planned_production_line_id"] = "00000000-0000-0000-0000-000000000099"
        altered["plan_sha256"] = plan_digest(altered)
        before = _counts(session)
        with pytest.raises(ProductionLinePopulationApplyError, match="target differs from sealed candidate"):
            guarded_apply(session, altered, expected_database_name=DATABASE_NAME, apply=True)
        session.rollback()
    with Session(fixture_state) as session:
        assert _counts(session) == before


def test_postgres_writer_rejects_resealed_wrong_dialect_before_write(fixture_state):
    with Session(fixture_state) as session:
        plan = _plan(session)
        altered = dict(plan)
        altered["source_database_identity"] = {**plan["source_database_identity"], "dialect": "sqlite"}
        altered["plan_sha256"] = plan_digest(altered)
        before = _counts(session)
        with pytest.raises(ProductionLinePopulationApplyError, match="identity differs from PostgreSQL target"):
            guarded_apply(session, altered, expected_database_name=DATABASE_NAME, apply=True)
        session.rollback()
    with Session(fixture_state) as session:
        assert _counts(session) == before


def test_postgres_writer_rejects_resealed_swapped_certificate_owner(fixture_state):
    # Certificate 22 and 20 both have Site 7 / raw code A; 22 is blocked by
    # the source inspection Site 8. A resealed plan must not link certificate
    # 22 merely because its raw text, Site and row-version fences all match.
    with Session(fixture_state) as session:
        plan = _plan(session)
        source = next(item for item in plan["certificate_links"]
                      if item["legacy_id"] == 20 and item["classification"] == "LINK_TO_NEW_LINE")
        blocked = session.scalar(select(Certificate).where(Certificate.legacy_certificate_id == 22))
        altered = dict(plan)
        altered["certificate_links"] = [dict(item) for item in plan["certificate_links"]]
        link = next(item for item in altered["certificate_links"] if item["legacy_id"] == 20)
        assert blocked.site_id == source["expected_site_id"]
        assert blocked.line_code == source["expected_canonical_raw_line_code"]
        assert blocked.row_version == source["expected_row_version"]
        link["canonical_record_id"] = blocked.id
        altered["plan_sha256"] = plan_digest(altered)
        before = _counts(session)
        with pytest.raises(ProductionLinePopulationApplyError, match="target legacy identity"):
            guarded_apply(session, altered, expected_database_name=DATABASE_NAME, apply=True)
        session.rollback()
    with Session(fixture_state) as session:
        assert _counts(session) == before


def test_postgres_writer_rejects_resealed_swapped_case_owner(fixture_state):
    # Create a same-site/same-raw Case that is unrelated to the source
    # candidate. Both target fences pass except legacy ownership.
    with Session(fixture_state) as session:
        unrelated = session.scalar(select(Case).where(Case.legacy_inspection_id == 14))
        unrelated.scope_code = "A"
        session.commit()
    with Session(fixture_state) as session:
        plan = _plan(session)
        source = next(item for item in plan["case_links"]
                      if item["legacy_id"] == 10 and item["classification"] == "LINK_TO_NEW_LINE")
        unrelated = session.scalar(select(Case).where(Case.legacy_inspection_id == 14))
        altered = dict(plan)
        altered["case_links"] = [dict(item) for item in plan["case_links"]]
        link = next(item for item in altered["case_links"] if item["legacy_id"] == 10)
        assert unrelated.site_id == source["expected_site_id"]
        assert unrelated.scope_code == source["expected_canonical_raw_line_code"]
        link["canonical_record_id"] = unrelated.id
        link["expected_row_version"] = unrelated.row_version
        altered["plan_sha256"] = plan_digest(altered)
        before = _counts(session)
        with pytest.raises(ProductionLinePopulationApplyError, match="target legacy identity"):
            guarded_apply(session, altered, expected_database_name=DATABASE_NAME, apply=True)
        session.rollback()
    with Session(fixture_state) as session:
        assert _counts(session) == before


def test_postgres_writer_rejects_unrelated_global_canonical_state_drift(fixture_state):
    with Session(fixture_state) as session:
        plan = _plan(session)
        unrelated = session.scalar(select(Case).where(Case.legacy_inspection_id == 14))
        unrelated.scope_code = "C-CHANGED"
        session.commit()
    with Session(fixture_state) as session:
        before = _counts(session)
        with pytest.raises(ProductionLinePopulationApplyError, match="global canonical state changed"):
            guarded_apply(session, plan, expected_database_name=DATABASE_NAME, apply=True)
        session.rollback()
        assert _counts(session) == before
