"""Canonical PCT/CT stage and round allocation must use the domain contract."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, Company, InspectionApprovalSubmission, Site
from backend.app.services.workflow import CaseWorkflowService


def test_approval_creation_normalizes_stage_and_allocates_case_stage_rounds():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    user = build_authenticated_user("approval-stage-round-owner", "manager")
    service = CaseWorkflowService()
    try:
        with Session(engine) as session:
            company = Company(legal_name="Synthetic approval stages")
            session.add(company)
            session.flush()
            site = Site(company_id=company.id, site_name="Synthetic approval stage site")
            session.add(site)
            session.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            session.add(case)
            session.flush()
            case_id = case.id
            session.commit()

        with Session(engine) as session:
            pct1 = service.create_approval_submission(
                session, case_id=case_id, stage=" pct ", reference="PCT first",
                submitted_on=None, submitted_time=None, pct_submission_id=None,
                reason="canonical stage", user=user,
            )
            assert pct1["stage"] == "PCT"
            assert pct1["round_no"] == 1
            pct2 = service.create_approval_submission(
                session, case_id=case_id, stage="PCT", reference="PCT second",
                submitted_on=None, submitted_time=None, pct_submission_id=None,
                reason="independent round", user=user,
            )
            assert pct2["round_no"] == 2
            session.commit()

        # The CT parent must be a completed canonical PCT in this Case.
        with Session(engine) as session:
            parent = session.get(InspectionApprovalSubmission, pct1["approval_submission_id"])
            parent.completed_on = date(2026, 11, 13)
            session.commit()

        with Session(engine) as session:
            ct = service.create_approval_submission(
                session, case_id=case_id, stage=" ct ", reference="CT first",
                submitted_on=None, submitted_time=None,
                pct_submission_id=pct1["approval_submission_id"],
                reason="linked canonical PCT", user=user,
            )
            assert ct["stage"] == "CT"
            assert ct["round_no"] == 1
            assert ct["pct_submission_id"] == pct1["approval_submission_id"]
            with pytest.raises(HTTPException) as exc:
                service.create_approval_submission(
                    session, case_id=case_id, stage="unknown", reference="Invalid",
                    submitted_on=None, submitted_time=None, pct_submission_id=None,
                    reason=None, user=user,
                )
            assert exc.value.status_code == 422
            session.commit()

        with Session(engine) as session:
            rows = session.scalars(
                select(InspectionApprovalSubmission)
                .where(InspectionApprovalSubmission.case_id == case_id)
                .order_by(InspectionApprovalSubmission.stage, InspectionApprovalSubmission.round_no)
            ).all()
            assert [(row.stage, row.round_no) for row in rows] == [
                ("CT", 1), ("PCT", 1), ("PCT", 2)
            ]
            assert next(row for row in rows if row.stage == "CT").pct_submission_id == pct1["approval_submission_id"]
    finally:
        engine.dispose()
