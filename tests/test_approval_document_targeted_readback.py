"""Approval document link recovery is a scoped canonical read, not a retry."""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.api.routers.workflow import register_workflow_routes
from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Company, Document, InspectionApprovalDocumentLink,
    InspectionApprovalSubmission, Site,
)
from backend.app.read_models import ApprovalDocumentReadbackRead
from backend.app.services.workflow import CaseWorkflowService


def _fixture(engine):
    with Session(engine) as session:
        company = Company(legal_name="Synthetic approval readback")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Synthetic readback site")
        session.add(site)
        session.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
        other = Case(site_id=site.id, gxp_type="GLP", state=CaseState.INSPECTION_COMPLETED)
        session.add_all([case, other])
        session.flush()
        pct = InspectionApprovalSubmission(case_id=case.id, stage="PCT", round_no=1)
        foreign = InspectionApprovalSubmission(case_id=other.id, stage="PCT", round_no=1)
        doc = Document(case_id=case.id, family_code="INSPECTION_PT_PCT",
                       document_type_code="INSPECTION_PT_PCT", title="PCT evidence")
        session.add_all([pct, foreign, doc])
        session.flush()
        ids = (case.id, other.id, pct.id, foreign.id, doc.id)
        session.commit()
        return ids


def test_targeted_approval_document_get_resolves_unknown_post_without_retry_or_audit():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    user = build_authenticated_user("synthetic-approval-readback", "manager", permissions={"inspection.edit", "document.read"})
    try:
        case, other, pct_id, foreign_id, document_id = _fixture(engine)
        with Session(engine) as session:
            empty = ApprovalDocumentReadbackRead.model_validate(
                service.get_approval_document_bindings(session, approval_submission_id=pct_id)
            )
            assert empty.approval_submission_id == pct_id
            assert empty.case_id == case
            assert empty.stage == "PCT"
            assert empty.round_no == 1
            assert empty.row_version == 1
            assert empty.links == []
            assert not session.new and not session.dirty

        with Session(engine) as writer:
            committed = service.bind_approval_document(
                writer, approval_submission_id=pct_id,
                document_id=document_id, expected_version=empty.row_version,
                reason="Commit succeeded, client lost response", user=user,
            )
            writer.commit()
            assert committed["created"] is True

        with Session(engine) as session:
            receipt = ApprovalDocumentReadbackRead.model_validate(
                service.get_approval_document_bindings(session, approval_submission_id=pct_id)
            )
            assert receipt.row_version == committed["row_version"] == 2
            assert len(receipt.links) == 1
            assert receipt.links[0].binding_id == committed["binding_id"]
            assert receipt.links[0].document_id == document_id
            assert receipt.links[0].approval_submission_id == pct_id
            assert receipt.links[0].stage == "PCT"
            assert receipt.links[0].round_no == 1
            # Readback remains scoped even with other Cases sharing a Site.
            foreign_receipt = ApprovalDocumentReadbackRead.model_validate(
                service.get_approval_document_bindings(session, approval_submission_id=foreign_id)
            )
            assert foreign_receipt.case_id == other
            assert foreign_receipt.links == []
            assert session.scalar(select(func.count(InspectionApprovalDocumentLink.id))) == 1
            assert session.scalar(select(func.count(AuditEvent.id))) == 1
            assert not session.new and not session.dirty

        with Session(engine) as stale:
            with pytest.raises(HTTPException) as exc:
                service.bind_approval_document(
                    stale, approval_submission_id=pct_id,
                    document_id=document_id, expected_version=empty.row_version,
                    reason="Blind POST replay must not pass", user=user,
                )
            assert exc.value.status_code == 409
            stale.rollback()
        with Session(engine) as verify:
            assert verify.scalar(select(func.count(InspectionApprovalDocumentLink.id))) == 1
            assert verify.scalar(select(func.count(AuditEvent.id))) == 1
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "corruption",
    ["cross_case_document", "wrong_family_document", "additional_parent_document"],
)
def test_targeted_readback_fails_closed_on_invalid_document_owner(corruption):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    user = build_authenticated_user("synthetic-approval-readback", "manager", permissions={"inspection.edit", "document.read"})
    try:
        case, other, pct_id, _foreign, document_id = _fixture(engine)
        with Session(engine) as session:
            service.bind_approval_document(
                session, approval_submission_id=pct_id,
                document_id=document_id, expected_version=1,
                reason=None, user=user,
            )
            session.commit()
        with Session(engine) as tamper:
            document = tamper.get(Document, document_id)
            if corruption == "cross_case_document":
                document.case_id = other
            elif corruption == "wrong_family_document":
                document.family_code = "INSPECTION_PT_CT"
            else:
                document.change_request_id = "00000000-0000-0000-0000-000000000001"
            # Legacy/corrupt data is only simulated in an isolated DB. The
            # canonical GET must refuse to call it proof of any binding.
            tamper.commit()
        with Session(engine) as session:
            audit_before = session.scalar(select(func.count(AuditEvent.id)))
            with pytest.raises(HTTPException) as exc:
                service.get_approval_document_bindings(session, approval_submission_id=pct_id)
            assert exc.value.status_code == 409
            assert session.scalar(select(func.count(AuditEvent.id))) == audit_before
            assert not session.new and not session.dirty
    finally:
        engine.dispose()


def test_readback_route_requires_same_permissions_as_post_before_looking_up_sources(monkeypatch):
    app = FastAPI()
    register_workflow_routes(app, lambda: None)
    route_path = "/approval-submissions/{approval_submission_id}/documents"
    routes = [r for r in app.routes if getattr(r, "path", None) == route_path]
    assert {frozenset(r.methods) for r in routes} == {
        frozenset({"GET"}), frozenset({"POST"}),
    }
    endpoint = next(r.endpoint for r in routes if r.methods == {"GET"})

    calls = []
    def canonical(_self, _session, *, approval_submission_id):
        calls.append(approval_submission_id)
        return {
            "approval_submission_id": approval_submission_id,
            "case_id": "canonical-case",
            "stage": "PCT",
            "round_no": 1,
            "row_version": 2,
            "links": [],
        }
    monkeypatch.setattr(CaseWorkflowService, "get_approval_document_bindings", canonical)
    source_session = object()
    for permissions in ({"document.read"}, {"inspection.edit"}):
        user = build_authenticated_user(
            "synthetic-no-access", permissions=permissions,
        )
        with pytest.raises(HTTPException) as exc:
            endpoint(approval_submission_id="hidden-source", session=source_session, user=user)
        assert exc.value.status_code == 403
        assert calls == []

    authorized = build_authenticated_user(
        "synthetic-authorized", permissions={"inspection.edit", "document.read"},
    )
    result = endpoint(
        approval_submission_id="source-uuid", session=source_session, user=authorized,
    )
    assert isinstance(result, ApprovalDocumentReadbackRead)
    assert result.approval_submission_id == "source-uuid"
    assert result.row_version == 2
    assert calls == ["source-uuid"]


def test_readback_ignores_pending_canonical_owner_drafts_without_autoflush(tmp_path):
    """GET must not flush a partially edited submission/Document before recovery."""
    from sqlalchemy import event

    engine = create_engine(f"sqlite:///{(tmp_path / 'approval-draft.sqlite').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    case_id, other_case_id, pct_id, _foreign_id, document_id = _fixture(engine)
    service = CaseWorkflowService()
    try:
        with Session(engine, autoflush=True, expire_on_commit=False) as session:
            submission = session.get(InspectionApprovalSubmission, pct_id)
            document = session.get(Document, document_id)
            assert submission.row_version == 1
            # Mutating the cached objects must never change the persisted
            # readback, invalidate Case ownership or cause an autoflush.
            submission.row_version = 91
            submission.stage = "CT"
            document.case_id = other_case_id
            document.family_code = "INSPECTION_PT_CT"
            statement_types = []

            def observe(_conn, _cursor, statement, _params, _context, _many):
                statement_types.append(statement.lstrip().split(None, 1)[0].upper())

            event.listen(engine, "before_cursor_execute", observe)
            try:
                result = service.get_approval_document_bindings(
                    session, approval_submission_id=pct_id,
                )
            finally:
                event.remove(engine, "before_cursor_execute", observe)
            assert result == {
                "approval_submission_id": pct_id, "case_id": case_id,
                "stage": "PCT", "round_no": 1, "row_version": 1, "links": [],
            }
            assert statement_types and set(statement_types) == {"SELECT"}
            assert submission.row_version == 91 and submission.stage == "CT"
            assert document.case_id == other_case_id
            assert document.family_code == "INSPECTION_PT_CT"
            assert submission in session.dirty and document in session.dirty
            session.rollback()
        with Session(engine) as verify:
            assert verify.get(InspectionApprovalSubmission, pct_id).row_version == 1
            assert verify.get(Document, document_id).case_id == case_id
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        engine.dispose()


def test_readback_uses_committed_owner_and_document_after_identity_cache(tmp_path):
    """A lost-response GET must not resurrect stale submission/Document owners."""
    from sqlalchemy import update

    engine = create_engine(f"sqlite:///{(tmp_path / 'approval-stale.sqlite').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    case_id, other_case_id, pct_id, _foreign_id, document_id = _fixture(engine)
    service = CaseWorkflowService()
    user = build_authenticated_user(
        "synthetic-binding", permissions={"inspection.edit", "document.read"},
    )
    try:
        with Session(engine) as writer:
            bound = service.bind_approval_document(
                writer, approval_submission_id=pct_id, document_id=document_id,
                expected_version=1, reason="synthetic commit", user=user,
            )
            writer.commit()
        with Session(engine, autoflush=False, expire_on_commit=False) as reader:
            cached_submission = reader.get(InspectionApprovalSubmission, pct_id)
            cached_document = reader.get(Document, document_id)
            assert cached_submission.row_version == bound["row_version"] == 2
            assert cached_document.case_id == case_id
            with Session(engine) as writer:
                writer.execute(
                    update(InspectionApprovalSubmission)
                    .where(InspectionApprovalSubmission.id == pct_id)
                    .values(row_version=3)
                )
                writer.commit()
            fresh = service.get_approval_document_bindings(
                reader, approval_submission_id=pct_id,
            )
            assert fresh["row_version"] == 3
            assert len(fresh["links"]) == 1
            assert fresh["links"][0]["document_id"] == document_id
            assert cached_submission.row_version == 2
            with Session(engine) as writer:
                writer.execute(
                    update(Document).where(Document.id == document_id)
                    .values(case_id=other_case_id)
                )
                writer.commit()
            with pytest.raises(HTTPException) as invalid:
                service.get_approval_document_bindings(
                    reader, approval_submission_id=pct_id,
                )
            assert invalid.value.status_code == 409
            assert cached_document.case_id == case_id
            assert not reader.dirty and not reader.new
            reader.rollback()
        with Session(engine) as verify:
            assert verify.scalar(select(func.count(InspectionApprovalDocumentLink.id))) == 1
            assert verify.scalar(select(func.count(AuditEvent.id))) == 1
    finally:
        engine.dispose()


def test_recovery_readback_uses_one_consistent_sql_snapshot(tmp_path):
    """Submitted owner/version and linked Document must derive from one statement.

    Under PostgreSQL READ COMMITTED, two SELECTs can observe different
    commits and create a mixed recovery receipt. A single joined statement
    cannot, while still avoiding ORM refreshes or flushing pending drafts.
    """
    from sqlalchemy import event

    engine = create_engine(
        f"sqlite:///{(tmp_path / 'approval-single-snapshot.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    case_id, _other_id, pct_id, _foreign_id, document_id = _fixture(engine)
    user = build_authenticated_user(
        "approval-single-snapshot", permissions={"inspection.edit", "document.read"},
    )
    try:
        with Session(engine) as writer:
            CaseWorkflowService().bind_approval_document(
                writer, approval_submission_id=pct_id,
                document_id=document_id, expected_version=1,
                reason="Synthetic committed evidence", user=user,
            )
            writer.commit()

        with Session(engine, autoflush=True, expire_on_commit=False) as reader:
            cached_submission = reader.get(InspectionApprovalSubmission, pct_id)
            cached_document = reader.get(Document, document_id)
            cached_submission.reference = "Operator unsaved approval reference"
            cached_document.title = "Operator unsaved document title"
            pending = Company(legal_name="Unrelated pending operator Company")
            reader.add(pending)
            queries = []
            flushes = []

            def observe(_conn, _cursor, statement, _params, _ctx, _many):
                queries.append(statement.lstrip().split(None, 1)[0].upper())
                if len(queries) > 1:
                    raise AssertionError(
                        "Approval recovery readback split into multiple SQL snapshots"
                    )

            def forbid_flush(*_args):
                flushes.append(True)
                raise AssertionError("Recovery GET flushed operator draft")

            event.listen(engine, "before_cursor_execute", observe)
            event.listen(reader, "before_flush", forbid_flush)
            try:
                receipt = CaseWorkflowService().get_approval_document_bindings(
                    reader, approval_submission_id=pct_id,
                )
            finally:
                event.remove(engine, "before_cursor_execute", observe)
                event.remove(reader, "before_flush", forbid_flush)
            assert queries == ["SELECT"]
            assert flushes == []
            assert receipt["case_id"] == case_id
            assert receipt["row_version"] == 2
            assert [row["document_id"] for row in receipt["links"]] == [document_id]
            assert cached_submission.reference == "Operator unsaved approval reference"
            assert cached_document.title == "Operator unsaved document title"
            assert cached_submission in reader.dirty
            assert cached_document in reader.dirty
            assert pending in reader.new
            reader.rollback()
    finally:
        engine.dispose()


def test_empty_recovery_readback_is_single_statement(tmp_path):
    from sqlalchemy import event

    engine = create_engine(
        f"sqlite:///{(tmp_path / 'approval-single-empty.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    case_id, _other_id, pct_id, _foreign_id, _document_id = _fixture(engine)
    try:
        with Session(engine) as reader:
            statements = []

            def observe(_conn, _cursor, statement, _params, _ctx, _many):
                statements.append(statement.lstrip().split(None, 1)[0].upper())

            event.listen(engine, "before_cursor_execute", observe)
            try:
                receipt = CaseWorkflowService().get_approval_document_bindings(
                    reader, approval_submission_id=pct_id,
                )
            finally:
                event.remove(engine, "before_cursor_execute", observe)
            assert statements == ["SELECT"]
            assert receipt["case_id"] == case_id
            assert receipt["links"] == []
            assert receipt["row_version"] == 1
    finally:
        engine.dispose()
