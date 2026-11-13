"""Disposable PostgreSQL owner proof for PCT/CT document links.

All mutations are isolated in a fresh schema of loopback gxp_qlcl_test.
Never connect this test to rehearsal, go-live, or external PostgreSQL.
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
    AuditEvent, Case, Company, Document, InspectionApprovalDocumentLink,
    InspectionApprovalSubmission, Site,
)
from backend.app.read_models import CaseWorkspaceRead
from backend.app.services.catalog import CatalogReadService
from backend.app.services.workflow import CaseWorkflowService


DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.fixture
def owner_db():
    url = make_url(DATABASE_URL)
    if url.host not in {"127.0.0.1", "localhost"} or url.database != "gxp_qlcl_test":
        pytest.fail("Only loopback disposable gxp_qlcl_test permitted; no writes performed.")
    schema = "approval_doc_fence_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = None
    created = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            DATABASE_URL,
            connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as session:
            company = Company(legal_name="Synthetic document link " + schema)
            session.add(company)
            session.flush()
            site = Site(company_id=company.id, site_name="Synthetic document link site")
            session.add(site)
            session.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            other_case = Case(site_id=site.id, gxp_type="GLP", state=CaseState.INSPECTION_COMPLETED)
            session.add_all([case, other_case])
            session.flush()
            pct = InspectionApprovalSubmission(case_id=case.id, stage="PCT", round_no=1)
            document = Document(
                case_id=case.id, family_code="INSPECTION_PT_PCT",
                document_type_code="INSPECTION_PT_PCT", title="Synthetic document",
            )
            session.add_all([pct, document])
            session.flush()
            ids = {
                "case": case.id, "other": other_case.id,
                "pct": pct.id, "document": document.id,
            }
            session.commit()
        yield factory, ids
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.mark.parametrize(
    ("writer_change", "http_status"),
    [
        ("submission_other_case", 409),
        ("document_other_case", 422),
        ("case_closed", 409),
    ],
)
def test_document_binding_refreshes_cached_owners_after_writer_commit(
    owner_db, writer_change, http_status,
):
    factory, ids = owner_db
    contender = writer = None
    try:
        # A live operator has already selected the source in a long-lived Session.
        contender = factory()
        prior_submission = contender.get(InspectionApprovalSubmission, ids["pct"])
        prior_document = contender.get(Document, ids["document"])
        prior_case = contender.get(Case, ids["case"])
        assert prior_submission.case_id == prior_document.case_id == prior_case.id
        original_version = prior_submission.row_version

        # Committed canonical source changes after the UI snapshot was cached.
        writer = factory()
        if writer_change == "submission_other_case":
            writer.get(InspectionApprovalSubmission, ids["pct"]).case_id = ids["other"]
        elif writer_change == "document_other_case":
            writer.get(Document, ids["document"]).case_id = ids["other"]
        else:
            writer.get(Case, ids["case"]).state = CaseState.CLOSED
        writer.commit()

        with pytest.raises(HTTPException) as denied:
            CaseWorkflowService().bind_approval_document(
                contender,
                approval_submission_id=ids["pct"],
                document_id=ids["document"],
                expected_version=original_version,
                reason="Cached owner must not create a link",
                user=build_authenticated_user("synthetic-link-owner", "manager"),
            )
        assert denied.value.status_code == http_status
        contender.rollback()

        with factory() as verify:
            assert verify.scalar(select(func.count(InspectionApprovalDocumentLink.id))) == 0
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
            assert verify.get(InspectionApprovalSubmission, ids["pct"]).case_id == (
                ids["other"] if writer_change == "submission_other_case" else ids["case"]
            )
            assert verify.get(Document, ids["document"]).case_id == (
                ids["other"] if writer_change == "document_other_case" else ids["case"]
            )
    finally:
        for session in (contender, writer):
            if session is not None:
                session.rollback()
                session.close()


def test_approval_document_lost_response_is_resolvable_by_canonical_readback(owner_db):
    factory, ids = owner_db
    contender = writer = None
    user = build_authenticated_user("synthetic-link-recovery", "manager")
    try:
        # The original request/response has been lost while this UI Session
        # still has the previous approval row_version and Document identity.
        contender = factory()
        stale_submission = contender.get(InspectionApprovalSubmission, ids["pct"])
        assert stale_submission.row_version == 1
        assert contender.get(Document, ids["document"]).case_id == ids["case"]

        writer = factory()
        original = CaseWorkflowService().bind_approval_document(
            writer,
            approval_submission_id=ids["pct"],
            document_id=ids["document"],
            expected_version=1,
            reason="First POST committed, response lost",
            user=user,
        )
        assert original["created"]
        writer.commit()

        with pytest.raises(HTTPException) as denied:
            CaseWorkflowService().bind_approval_document(
                contender,
                approval_submission_id=ids["pct"],
                document_id=ids["document"],
                expected_version=1,
                reason="Must not silently replay stale POST",
                user=user,
            )
        assert denied.value.status_code == 409
        contender.rollback()

        # A canonical GET resolves the unknown outcome; no second POST or
        # inferred success based on an HTTP timeout is needed.
        with factory() as verify:
            workspace = CaseWorkspaceRead.model_validate(
                CatalogReadService().get_case_workspace(
                    verify, case_id=ids["case"], user=user,
                )
            )
            assert len(workspace.inspection.approval_document_links) == 1
            link = workspace.inspection.approval_document_links[0]
            assert link.binding_id == original["binding_id"]
            assert link.approval_submission_id == ids["pct"]
            assert link.document_id == ids["document"]
            assert workspace.inspection.approval_document_candidates[0].bound_submission_id == ids["pct"]
            assert workspace.inspection.approval_document_bind_readiness[0].expected_version == original["row_version"]
            assert verify.scalar(select(func.count(InspectionApprovalDocumentLink.id))) == 1
            assert verify.scalar(select(func.count(AuditEvent.id))) == 1

        with factory() as replay:
            same = CaseWorkflowService().bind_approval_document(
                replay,
                approval_submission_id=ids["pct"],
                document_id=ids["document"],
                expected_version=original["row_version"],
                reason=None, user=user,
            )
            assert same["created"] is False
            assert same["binding_id"] == original["binding_id"]
            replay.commit()
        with factory() as verify:
            assert verify.scalar(select(func.count(InspectionApprovalDocumentLink.id))) == 1
            assert verify.scalar(select(func.count(AuditEvent.id))) == 1
    finally:
        for session in (contender, writer):
            if session is not None:
                session.rollback()
                session.close()
