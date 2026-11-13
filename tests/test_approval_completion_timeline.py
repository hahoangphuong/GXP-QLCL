"""End-to-end mutation guard for PCT/CT submission completion chronology."""
from __future__ import annotations

from datetime import date, time

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Company, InspectionApprovalSubmission, Site,
)
from backend.app.services.workflow import CaseWorkflowService


@pytest.mark.parametrize(
    ("stage", "submitted_on", "submitted_time", "completed_on", "completed_time", "allowed"),
    [
        ("PCT", date(2026, 11, 13), None, date(2026, 11, 12), None, False),
        ("CT", date(2026, 11, 13), time(15, 30), date(2026, 11, 13), time(15, 29), False),
        ("PCT", date(2026, 11, 13), time(15, 30), date(2026, 11, 13), time(15, 30), True),
        ("CT", date(2026, 11, 13), time(15, 30), date(2026, 11, 13), None, True),
        ("PCT", date(2026, 11, 13), time(15, 30), date(2026, 11, 14), time(9, 0), True),
    ],
)
def test_approval_completion_owner_prevents_backdated_mutation_without_audit(
    stage, submitted_on, submitted_time, completed_on, completed_time, allowed
):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    user = build_authenticated_user("synthetic-approval-completion", "manager")
    try:
        with Session(engine) as setup:
            company = Company(legal_name="Synthetic completion chronology")
            setup.add(company)
            setup.flush()
            site = Site(company_id=company.id, site_name="Synthetic timeline site")
            setup.add(site)
            setup.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            setup.add(case)
            setup.flush()
            pct_parent_id = None
            if stage == "CT":
                pct_parent = InspectionApprovalSubmission(
                    case_id=case.id,
                    stage="PCT",
                    round_no=1,
                    reference="PCT parent",
                    completed_on=date(2026, 11, 12),
                )
                setup.add(pct_parent)
                setup.flush()
                pct_parent_id = pct_parent.id
            submission = InspectionApprovalSubmission(
                case_id=case.id,
                stage=stage,
                round_no=1,
                reference="SYNTHETIC",
                submitted_on=submitted_on,
                submitted_time=submitted_time,
                pct_submission_id=pct_parent_id,
            )
            setup.add(submission)
            setup.commit()
            submission_id = submission.id
            expected_version = submission.row_version

        with Session(engine) as mutation:
            before_audit = mutation.scalar(select(func.count(AuditEvent.id)))
            kwargs = dict(
                approval_submission_id=submission_id,
                expected_version=expected_version,
                completed_on=completed_on,
                completed_time=completed_time,
                reason="synthetic chronological test",
                user=user,
            )
            if allowed:
                result = service.complete_approval_submission(mutation, **kwargs)
                assert result["completed_on"] == completed_on
                assert result["completed_time"] == completed_time
                mutation.commit()
            else:
                with pytest.raises(HTTPException) as exc:
                    service.complete_approval_submission(mutation, **kwargs)
                assert exc.value.status_code == 422
                assert "cannot precede" in str(exc.value.detail)
                mutation.rollback()

        with Session(engine) as verify:
            persisted = verify.get(InspectionApprovalSubmission, submission_id)
            assert persisted.completed_on == (completed_on if allowed else None)
            assert persisted.completed_time == (completed_time if allowed else None)
            assert persisted.row_version == expected_version + (1 if allowed else 0)
            assert verify.scalar(select(func.count(AuditEvent.id))) == (before_audit + (1 if allowed else 0))
    finally:
        engine.dispose()
