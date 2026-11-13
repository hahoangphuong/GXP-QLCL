"""Canonical inspection-plan date interval mutation and partial-update regression.

No human, rehearsal or production data: all facts are synthetic.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import AuditEvent, Case, Company, InspectionEvent, InspectionPlan, Site
from backend.app.services.workflow import CaseWorkflowService


def _fixture(engine):
    with Session(engine) as session:
        company = Company(legal_name="Synthetic inspection plan interval")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Synthetic planning site")
        session.add(site)
        session.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
        session.add(case)
        session.commit()
        return case.id


def _save(service, session, case_id, version, **changes):
    values = {
        "plan_start_on": None,
        "plan_end_on": None,
        "planning_sheet_name": None,
        "decision_document_hint": None,
        "decision_reference": None,
        "decision_date": None,
    }
    values.update(changes)
    return service.upsert_inspection_plan(
        session,
        case_id=case_id,
        expected_version=version,
        reason="synthetic plan interval",
        user=build_authenticated_user("synthetic-plan-owner", "manager"),
        fields_set=set(changes),
        **values,
    )


def _counts(session):
    return (
        session.scalar(select(func.count(InspectionPlan.id))),
        session.scalar(select(func.count(AuditEvent.id))),
        session.scalar(select(func.count(InspectionEvent.id))),
    )


def test_plan_interval_partial_changes_validate_canonical_dates_before_audit():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    try:
        case_id = _fixture(engine)
        for changes in (
            {"plan_end_on": date(2026, 11, 14)},
            {"plan_start_on": date(2026, 11, 15), "plan_end_on": date(2026, 11, 14)},
        ):
            with Session(engine) as session:
                with pytest.raises(HTTPException) as error:
                    _save(service, session, case_id, None, **changes)
                assert error.value.status_code == 422
                session.rollback()
                assert _counts(session) == (0, 0, 0)

        with Session(engine) as session:
            created = _save(service, session, case_id, None, plan_start_on=date(2026, 11, 13))
            session.commit()
            assert created["plan_end_on"] is None
            version = created["row_version"]

        for changes in (
            {"plan_end_on": date(2026, 11, 12)},
            {"plan_start_on": None, "plan_end_on": date(2026, 11, 14)},
        ):
            with Session(engine) as session:
                before = _counts(session)
                with pytest.raises(HTTPException) as error:
                    _save(service, session, case_id, version, **changes)
                assert error.value.status_code == 422
                session.rollback()
                assert _counts(session) == before
                saved = session.scalar(select(InspectionPlan).where(InspectionPlan.case_id == case_id))
                assert saved.plan_start_on == date(2026, 11, 13)
                assert saved.plan_end_on is None
                assert saved.row_version == version

        with Session(engine) as session:
            extended = _save(service, session, case_id, version, plan_end_on=date(2026, 11, 14))
            session.commit()
            assert extended["plan_start_on"] == date(2026, 11, 13)
            assert extended["plan_end_on"] == date(2026, 11, 14)
            version = extended["row_version"]

        for changes in (
            {"plan_start_on": date(2026, 11, 15)},
            {"plan_start_on": None},
        ):
            with Session(engine) as session:
                before = _counts(session)
                with pytest.raises(HTTPException) as error:
                    _save(service, session, case_id, version, **changes)
                assert error.value.status_code == 422
                session.rollback()
                assert _counts(session) == before

        with Session(engine) as session:
            same_day = _save(service, session, case_id, version, plan_start_on=date(2026, 11, 14))
            session.commit()
            assert same_day["plan_start_on"] == same_day["plan_end_on"] == date(2026, 11, 14)
            with Session(engine) as readback:
                saved = readback.scalar(select(InspectionPlan).where(InspectionPlan.case_id == case_id))
                assert (saved.plan_start_on, saved.plan_end_on) == (date(2026, 11, 14), date(2026, 11, 14))
    finally:
        engine.dispose()


def test_legacy_invalid_plan_is_readable_metadata_only_and_explicitly_correctable():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    try:
        case_id = _fixture(engine)
        with Session(engine) as session:
            old = InspectionPlan(
                case_id=case_id,
                plan_start_on=date(2026, 11, 15),
                plan_end_on=date(2026, 11, 13),
                planning_sheet_name="Legacy invalid date source",
            )
            session.add(old)
            session.commit()
            version = old.row_version

        with Session(engine) as session:
            meta = _save(service, session, case_id, version, planning_sheet_name="Updated metadata only")
            session.commit()
            assert meta["plan_start_on"] > meta["plan_end_on"]
            assert meta["planning_sheet_name"] == "Updated metadata only"

        with Session(engine) as session:
            with pytest.raises(HTTPException) as error:
                _save(service, session, case_id, meta["row_version"], plan_end_on=date(2026, 11, 14))
            assert error.value.status_code == 422
            session.rollback()

        with Session(engine) as session:
            corrected = _save(service, session, case_id, meta["row_version"], plan_end_on=date(2026, 11, 16))
            session.commit()
            assert corrected["plan_start_on"] == date(2026, 11, 15)
            assert corrected["plan_end_on"] == date(2026, 11, 16)
            with Session(engine) as verify:
                saved = verify.scalar(select(InspectionPlan).where(InspectionPlan.case_id == case_id))
                assert saved.plan_end_on == date(2026, 11, 16)
                assert saved.planning_sheet_name == "Updated metadata only"
    finally:
        engine.dispose()
