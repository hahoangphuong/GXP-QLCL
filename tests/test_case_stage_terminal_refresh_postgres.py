"""Disposable PostgreSQL: stale Session Case identity must not bypass terminal gate.

A separate committed transition closes the Case while the second Session retains
an old nonterminal ORM identity. SELECT Case.id FOR UPDATE must not be mistaken
for refreshing that cached Case state.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, CaseApplication, CaseAssessment, Company,
    InspectionOutcome, InspectionPlan, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)

STAGES = {
    "application": CaseApplication,
    "assessment": CaseAssessment,
    "plan": InspectionPlan,
    "outcome": InspectionOutcome,
}


@pytest.mark.parametrize("kind", tuple(STAGES))
def test_stage_write_rechecks_fresh_case_terminal_state(kind):
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Disposable gxp_qlcl_test database required; no mutation performed.")
    schema = "stage_terminal_refresh_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = closing = contender = None
    created_schema = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created_schema = True
        engine = create_engine(
            DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as setup:
            company = Company(legal_name="Synthetic stage " + schema)
            setup.add(company)
            setup.flush()
            site = Site(company_id=company.id, site_name="Synthetic stage site")
            setup.add(site)
            setup.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            setup.add(case)
            setup.flush()
            stage = STAGES[kind](case_id=case.id)
            setup.add(stage)
            setup.commit()
            case_id, stage_id, version = case.id, stage.id, stage.row_version

        service = CaseWorkflowService()
        user = build_authenticated_user("synthetic-stage-gate", "manager")
        contender = factory()
        cached = contender.get(Case, case_id)
        assert cached.state == CaseState.INSPECTION_COMPLETED
        closing = factory()
        terminal = closing.get(Case, case_id)
        terminal.state = CaseState.CLOSED
        closing.commit()

        def mutate():
            if kind == "application":
                return service.upsert_case_application(
                    contender, case_id=case_id, expected_version=version,
                    submitted_on=None, dossier_code=None, dossier_reference=None,
                    applicant_name="Should not persist", reason="stale state probe",
                    user=user, fields_set={"applicant_name"},
                )
            if kind == "assessment":
                return service.upsert_case_assessment(
                    contender, case_id=case_id, expected_version=version,
                    assessed_on=None, assessor_name=None, assessment_result=None,
                    notes="Should not persist", reason="stale state probe",
                    user=user, fields_set={"notes"},
                )
            if kind == "plan":
                return service.upsert_inspection_plan(
                    contender, case_id=case_id, expected_version=version,
                    plan_start_on=None, plan_end_on=None,
                    planning_sheet_name="Do not persist", decision_document_hint=None,
                    reason="stale state probe", user=user,
                    fields_set={"planning_sheet_name"},
                )
            return service.upsert_inspection_outcome(
                contender, case_id=case_id, expected_version=version,
                inspected_on=None, inspected_to_on=None, decision_reference=None,
                bbkt_reference=None, outcome_result="Do not persist",
                reason="stale state probe", user=user, fields_set={"outcome_result"},
            )

        with pytest.raises(HTTPException) as denied:
            mutate()
        assert denied.value.status_code == 409
        contender.rollback()

        with factory() as verify:
            assert verify.get(Case, case_id).state == CaseState.CLOSED
            child = verify.get(STAGES[kind], stage_id)
            assert child.row_version == version
            assert {
                "application": lambda x: x.applicant_name,
                "assessment": lambda x: x.notes,
                "plan": lambda x: x.planning_sheet_name,
                "outcome": lambda x: x.outcome_result,
            }[kind](child) is None
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        for session in (contender, closing):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created_schema:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
