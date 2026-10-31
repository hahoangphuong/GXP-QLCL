"""Regression: persisted approval rows must satisfy canonical Case workspace read model."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, Company, InspectionApprovalSubmission, Site
from backend.app.read_models import CaseWorkspaceRead
from backend.app.services.catalog import CatalogReadService


def test_workspace_projection_preserves_case_owned_pct_ct_rounds_on_reload():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    user = build_authenticated_user("approval-projection", "manager")
    try:
        with Session(engine) as session:
            company = Company(legal_name="Synthetic approval source")
            session.add(company)
            session.flush()
            site = Site(company_id=company.id, site_name="Synthetic site")
            session.add(site)
            session.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
            session.add(case)
            session.flush()
            case_id = case.id
            other_case = Case(site_id=site.id, gxp_type="GLP", state=CaseState.DRAFT)
            session.add(other_case)
            session.flush()
            pct1 = InspectionApprovalSubmission(case_id=case_id, stage="PCT", round_no=1, reference="PCT-1")
            pct2 = InspectionApprovalSubmission(case_id=case_id, stage="PCT", round_no=2, reference="PCT-2")
            session.add_all([pct1, pct2])
            session.flush()
            ct = InspectionApprovalSubmission(
                case_id=case_id, stage="CT", round_no=1, reference="CT-1",
                pct_submission_id=pct1.id,
            )
            foreign = InspectionApprovalSubmission(
                case_id=other_case.id, stage="PCT", round_no=1, reference="OTHER",
            )
            session.add_all([ct, foreign])
            session.commit()

        service = CatalogReadService()
        for _ in range(2):  # Fresh sessions: canonical persistence/readback, not cached responses.
            with Session(engine) as session:
                workspace = CaseWorkspaceRead(**service.get_case_workspace(session, case_id=case_id, user=user))
                approvals = workspace.inspection.approval_submissions
                assert len(approvals) == 3
                assert all(item.case_id == case_id for item in approvals)
                assert {item.approval_submission_id for item in approvals} == {pct1.id, pct2.id, ct.id}
                assert next(item for item in approvals if item.approval_submission_id == ct.id).pct_submission_id == pct1.id
    finally:
        engine.dispose()
