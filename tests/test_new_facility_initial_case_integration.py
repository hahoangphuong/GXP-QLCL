"""Disposable SQLite integration: Company → Site → physical line → first Case.

Canonical UUIDs own each aggregate. A shared physical-line code does not
identify an asset, and a newly created Site must not imply GxP authorization.
"""
from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import AuditEvent, Case, Certificate, Company, ProductionLine, Site
from backend.app.services.catalog import CatalogReadService
from backend.app.services.workflow import CaseWorkflowService


def uid():
    return str(uuid4())


def editor():
    return build_authenticated_user("synthetic-operator", permissions={"case.edit"})


@pytest.fixture
def engine():
    db_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(db_engine)
    yield db_engine
    db_engine.dispose()


def seed_facility(db):
    workflow = CaseWorkflowService()
    company_id, site_id = uid(), uid()
    workflow.create_company_master(
        db, company_id=company_id, legal_name="Source Company",
        legal_address="Source Legal Address", english_name=None, short_name=None,
        legal_address_en=None, reason="Source verified", user=editor(),
    )
    workflow.create_site_master(
        db, company_id=company_id, site_id=site_id, site_name="Source Site",
        site_address="Source Site Address", site_name_en=None, site_address_en=None,
        province_name=None, short_name=None, reason="Source verified", user=editor(),
    )
    return company_id, site_id


def create_line(db, site_id, line_id, code="SHARED-CODE"):
    return CaseWorkflowService().create_production_line_master(
        db, site_id=site_id, production_line_id=line_id, code=code,
        effective_from=date(2026, 1, 1), effective_to=None,
        physical_identity_evidence_reference="EXPLICIT-PHYSICAL-SOURCE",
        reason="Independently verified source", user=editor(),
    )


def create_case(db, site_id, line_id, case_id):
    return CaseWorkflowService().create_initial_inspection_case(
        db, site_id=site_id, case_id=case_id, gxp_type="GMP",
        production_line_id=line_id, inspection_type="Mới",
        applicable_standard="WHO-GMP", reason="First Case in exact context",
        user=editor(),
    )


def test_explicit_facility_two_same_code_lines_and_distinct_first_cases(engine):
    workflow, catalog = CaseWorkflowService(), CatalogReadService()
    line_a, line_b, case_a, case_b = (uid() for _ in range(4))
    with Session(engine) as db:
        company_id, site_id = seed_facility(db)
        db.commit()
    with Session(engine) as db:
        assert catalog.get_company(db, company_id).id == company_id
        assert catalog.get_site(db, site_id).company_id == company_id
        search = catalog.search_facilities(db, site_id=site_id)
        assert search["total_count"] == 1
        unclassified = search["items"][0]
        assert (unclassified["gxp_type"], unclassified["result_grain"],
                unclassified["production_line_identity_state"]) == (
                    None, "facility", "facility_wide",
                )
        assert catalog.search_facilities(db, site_id=site_id, gxp_type="GMP")["total_count"] == 0
        assert db.scalar(select(func.count()).select_from(Case)) == 0
        assert db.scalar(select(func.count()).select_from(Certificate)) == 0

        # Two distinct real physical lines are never merged by their shared code.
        for line_id in (line_a, line_b):
            result = create_line(db, site_id, line_id)
            assert result["id"] == line_id
            assert result["site_id"] == site_id
        db.commit()
    with Session(engine) as db:
        assert {
            line.id for line in db.scalars(
                select(ProductionLine).where(ProductionLine.site_id == site_id)
            )
        } == {line_a, line_b}
        assert db.scalar(select(func.count()).select_from(Case)) == 0
        for line_id in (line_a, line_b):
            readiness = workflow.get_create_initial_case_action_readiness(
                db, site_id=site_id, gxp_type="GMP",
                line_code="SHARED-CODE", production_line_id=line_id, user=editor(),
            )
            assert readiness["readiness_status"] == "available"
        result = create_case(db, site_id, line_a, case_a)
        assert result["state"] == "draft"
        db.commit()
    with Session(engine) as db:
        assert workflow.get_create_initial_case_action_readiness(
            db, site_id=site_id, gxp_type="GMP", line_code="SHARED-CODE",
            production_line_id=line_a, user=editor(),
        )["readiness_status"] == "conflict"
        assert workflow.get_create_initial_case_action_readiness(
            db, site_id=site_id, gxp_type="GMP", line_code="SHARED-CODE",
            production_line_id=line_b, user=editor(),
        )["readiness_status"] == "available"
        create_case(db, site_id, line_b, case_b)
        db.commit()
    with Session(engine) as db:
        rows = list(db.scalars(select(Case).where(Case.site_id == site_id)))
        assert {row.id: row.production_line_id for row in rows} == {
            case_a: line_a, case_b: line_b,
        }
        assert all(row.state == CaseState.DRAFT for row in rows)
        assert all(row.legacy_inspection_id is None for row in rows)
        assert all(row.legacy_inspection_code is None for row in rows)
        assert db.scalar(select(func.count()).select_from(Certificate)) == 0
        actions = list(db.scalars(select(AuditEvent.action)))
        assert actions.count("company.create") == 1
        assert actions.count("site.create") == 1
        assert actions.count("production_line.create") == 2
        assert actions.count("case.create_initial_case") == 2


@pytest.mark.parametrize("kind", ["line", "case"])
def test_ambiguous_post_replay_same_uuid_cannot_create_duplicate(engine, kind):
    line_id, case_id = uid(), uid()
    with Session(engine) as db:
        _, site_id = seed_facility(db)
        create_line(db, site_id, line_id, code="ORIGINAL")
        if kind == "case":
            create_case(db, site_id, line_id, case_id)
        db.commit()
    with Session(engine) as db:
        before = tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (ProductionLine, Case, AuditEvent)
        )
        with pytest.raises(HTTPException) as exc:
            if kind == "line":
                create_line(db, site_id, line_id, code="MISMATCH")
            else:
                create_case(db, site_id, line_id, case_id)
        assert exc.value.status_code == 409
        db.rollback()
        after = tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (ProductionLine, Case, AuditEvent)
        )
        assert before == after
        if kind == "line":
            assert db.get(ProductionLine, line_id).code == "ORIGINAL"
        else:
            assert db.get(Case, case_id).production_line_id == line_id
