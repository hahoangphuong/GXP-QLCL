"""Synthetic contract tests: one canonical document belongs to one PCT/CT round."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Company, Document, InspectionApprovalDocumentLink,
    InspectionApprovalSubmission, Site,
)
from backend.app.read_models import CaseWorkspaceRead
from backend.app.services.catalog import CatalogReadService
from backend.app.services.workflow import CaseWorkflowService


@pytest.fixture
def owner_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Synthetic approval documentary contract")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Synthetic binding site")
        session.add(site)
        session.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
        other = Case(site_id=site.id, gxp_type="GLP", state=CaseState.INSPECTION_COMPLETED)
        session.add_all([case, other])
        session.flush()
        pct1 = InspectionApprovalSubmission(case_id=case.id, stage="PCT", round_no=1,
                                            completed_on=date(2026, 11, 11))
        pct2 = InspectionApprovalSubmission(case_id=case.id, stage="PCT", round_no=2)
        session.add_all([pct1, pct2])
        session.flush()
        ct = InspectionApprovalSubmission(case_id=case.id, stage="CT", round_no=1,
                                          pct_submission_id=pct1.id)
        session.add(ct)
        pct_doc = Document(case_id=case.id, family_code="INSPECTION_PT_PCT",
                           document_type_code="INSPECTION_PT_PCT", title="PCT case document")
        pct_doc2 = Document(case_id=case.id, family_code="INSPECTION_PT_PCT",
                            document_type_code="INSPECTION_PT_PCT", title="PCT round two")
        ct_doc = Document(case_id=case.id, family_code="INSPECTION_PT_CT",
                          document_type_code="INSPECTION_PT_CT", title="CT case document")
        foreign_doc = Document(case_id=other.id, family_code="INSPECTION_PT_PCT",
                               document_type_code="INSPECTION_PT_PCT", title="Wrong Case")
        session.add_all([pct_doc, pct_doc2, ct_doc, foreign_doc])
        session.flush()
        ids = {
            "case": case.id, "other": other.id,
            "pct1": pct1.id, "pct2": pct2.id, "ct": ct.id,
            "pct_doc": pct_doc.id, "pct_doc2": pct_doc2.id,
            "ct_doc": ct_doc.id, "foreign_doc": foreign_doc.id,
        }
        session.commit()
    try:
        yield engine, ids
    finally:
        engine.dispose()


def _counts(session):
    return (
        session.scalar(select(func.count(InspectionApprovalDocumentLink.id))),
        session.scalar(select(func.count(AuditEvent.id))),
    )


def test_explicit_approval_document_bind_and_round_readback(owner_db):
    engine, ids = owner_db
    workflow = CaseWorkflowService()
    catalog = CatalogReadService()
    user = build_authenticated_user("approval-doc-contract", "manager")
    with Session(engine) as session:
        before = _counts(session)
        first = workflow.bind_approval_document(
            session, approval_submission_id=ids["pct1"],
            document_id=ids["pct_doc"], expected_version=1,
            reason="Synthetic source confirmation", user=user,
        )
        assert first["created"] is True
        assert first["row_version"] == 2
        session.commit()
        assert _counts(session) == (before[0] + 1, before[1] + 1)

    with Session(engine) as session:
        replay = workflow.bind_approval_document(
            session, approval_submission_id=ids["pct1"],
            document_id=ids["pct_doc"], expected_version=2,
            reason=None, user=user,
        )
        assert replay["created"] is False
        assert replay["binding_id"] == first["binding_id"]
        session.commit()
        assert _counts(session) == (1, 1)

    with Session(engine) as session:
        second = workflow.bind_approval_document(
            session, approval_submission_id=ids["pct2"],
            document_id=ids["pct_doc2"], expected_version=1,
            reason=None, user=user,
        )
        third = workflow.bind_approval_document(
            session, approval_submission_id=ids["ct"],
            document_id=ids["ct_doc"], expected_version=1,
            reason=None, user=user,
        )
        session.commit()
        assert second["created"] and third["created"]

    with Session(engine) as session:
        workspace = CaseWorkspaceRead.model_validate(
            catalog.get_case_workspace(session, case_id=ids["case"], user=user)
        )
        links = workspace.inspection.approval_document_links
        assert {(row.approval_submission_id, row.document_id) for row in links} == {
            (ids["pct1"], ids["pct_doc"]),
            (ids["pct2"], ids["pct_doc2"]),
            (ids["ct"], ids["ct_doc"]),
        }
        assert all(row.binding_id for row in links)
        assert [item.round_document_binding_state for item in
                workspace.inspection.approval_document_evidence] == ["bound", "bound"]
        assert _counts(session) == (3, 3)
        assert not session.new and not session.dirty


@pytest.mark.parametrize(
    ("submission", "document", "status"),
    [
        ("pct1", "ct_doc", 422),
        ("pct1", "foreign_doc", 422),
    ],
)
def test_approval_doc_rejects_wrong_stage_or_case_without_writing(owner_db, submission, document, status):
    engine, ids = owner_db
    user = build_authenticated_user("approval-doc-contract", "manager")
    with Session(engine) as session:
        before = _counts(session)
        with pytest.raises(HTTPException) as exc:
            CaseWorkflowService().bind_approval_document(
                session, approval_submission_id=ids[submission],
                document_id=ids[document], expected_version=1,
                reason=None, user=user,
            )
        assert exc.value.status_code == status
        session.rollback()
        assert _counts(session) == before


def test_approval_doc_prevents_rebinding_and_stale_token(owner_db):
    engine, ids = owner_db
    service = CaseWorkflowService()
    user = build_authenticated_user("approval-doc-contract", "manager")
    with Session(engine) as session:
        service.bind_approval_document(
            session, approval_submission_id=ids["pct1"],
            document_id=ids["pct_doc"], expected_version=1,
            reason=None, user=user,
        )
        session.commit()

    with Session(engine) as session:
        for submission_id, document_id, version, expected_http in (
            (ids["pct2"], ids["pct_doc"], 1, 409),
            (ids["pct1"], ids["pct_doc2"], 1, 409),
        ):
            before = _counts(session)
            with pytest.raises(HTTPException) as exc:
                service.bind_approval_document(
                    session, approval_submission_id=submission_id,
                    document_id=document_id, expected_version=version,
                    reason=None, user=user,
                )
            assert exc.value.status_code == expected_http
            session.rollback()
            assert _counts(session) == before

    with Session(engine) as session:
        case = session.get(Case, ids["case"])
        case.state = CaseState.CLOSED
        session.commit()

    with Session(engine) as session:
        before = _counts(session)
        with pytest.raises(HTTPException) as exc:
            service.bind_approval_document(
                session, approval_submission_id=ids["pct2"],
                document_id=ids["pct_doc2"], expected_version=1,
                reason=None, user=user,
            )
        assert exc.value.status_code in {409, 422}
        session.rollback()
        assert _counts(session) == before


def test_unbound_history_remains_unverified(owner_db):
    engine, ids = owner_db
    with Session(engine) as session:
        workspace = CaseWorkspaceRead.model_validate(
            CatalogReadService().get_case_workspace(
                session, case_id=ids["case"],
                user=build_authenticated_user("approval-doc-contract", "manager"),
            )
        )
        assert workspace.inspection.approval_document_links == []
        assert [x.round_document_binding_state
                for x in workspace.inspection.approval_document_evidence] == ["unbound", "unbound"]
