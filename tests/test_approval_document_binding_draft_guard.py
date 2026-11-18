"""Approval-document mutation admission preserves cached operator drafts.

A PCT/CT document binding is append-only. Owner verification, Case/Document
locks and idempotent lookup must not autoflush unrelated pending SQL objects.
Synthetic SQLite only.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Company, Document, InspectionApprovalDocumentLink,
    InspectionApprovalSubmission, Site,
)
from backend.app.services.workflow import CaseWorkflowService


USER = build_authenticated_user(
    "approval-binding-draft-guard", "manager",
    permissions={"inspection.edit", "document.read"},
)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'approval-binding-draft.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Committed company")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Committed site")
        db.add(site)
        db.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
        other = Case(site_id=site.id, gxp_type="GLP", state=CaseState.INSPECTION_COMPLETED)
        db.add_all((case, other))
        db.flush()
        approval = InspectionApprovalSubmission(
            case_id=case.id, stage="PCT", round_no=1, reference="Committed PCT",
        )
        document = Document(
            case_id=case.id, family_code="INSPECTION_PT_PCT",
            document_type_code="INSPECTION_PT_PCT", title="Committed document",
        )
        db.add_all((approval, document))
        db.commit()
        ids = (approval.id, document.id, other.id, approval.row_version)
    try:
        yield engine, ids
    finally:
        engine.dispose()


def bind(db, approval_id, doc_id, version):
    return CaseWorkflowService().bind_approval_document(
        db, approval_submission_id=approval_id, document_id=doc_id,
        expected_version=version, reason="Synthetic binding", user=USER,
    )


def observe(engine, db):
    sql, flushes = [], []

    def on_sql(_conn, _cursor, statement, _params, _context, _many):
        sql.append(statement.lstrip().split(None, 1)[0].upper())

    def no_flush(*_args):
        flushes.append(True)
        raise AssertionError("Approval binding admission autoflushed operator draft")

    event.listen(engine, "before_cursor_execute", on_sql)
    event.listen(db, "before_flush", no_flush)
    return sql, flushes, on_sql, no_flush


def release(engine, db, on_sql, no_flush):
    event.remove(engine, "before_cursor_execute", on_sql)
    event.remove(db, "before_flush", no_flush)


@pytest.mark.parametrize("dirty_owner", ["approval", "document"])
def test_dirty_owner_is_rejected_without_refresh_or_autoflush(seeded, dirty_owner):
    engine, (approval_id, document_id, _, version) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        approval = db.get(InspectionApprovalSubmission, approval_id)
        document = db.get(Document, document_id)
        if dirty_owner == "approval":
            approval.reference = "Uncommitted approval draft"
        else:
            document.title = "Uncommitted document draft"
        pending = Company(legal_name="Unrelated pending Company")
        db.add(pending)
        statements, flushes, sql_fn, flush_fn = observe(engine, db)
        try:
            with pytest.raises(HTTPException) as exc:
                bind(db, approval_id, document_id, version)
        finally:
            release(engine, db, sql_fn, flush_fn)
        assert exc.value.status_code == 409
        assert not flushes
        assert set(statements) <= {"SELECT"}
        assert (approval.reference == "Uncommitted approval draft") == (dirty_owner == "approval")
        assert (document.title == "Uncommitted document draft") == (dirty_owner == "document")
        assert pending in db.new
        assert (approval if dirty_owner == "approval" else document) in db.dirty
        db.rollback()
    with Session(engine) as check:
        assert check.scalar(select(func.count(InspectionApprovalDocumentLink.id))) == 0
        assert check.scalar(select(func.count(AuditEvent.id))) == 0
        assert check.scalar(select(func.count(Company.id))) == 1



def test_dirty_case_parent_rejected_before_binding_refresh(seeded):
    engine, (approval_id, document_id, _, version) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        approval = db.get(InspectionApprovalSubmission, approval_id)
        parent = db.get(Case, approval.case_id)
        parent.state = CaseState.CLOSED
        pending = Company(legal_name="Pending Company during binding")
        db.add(pending)
        statements, flushes, sql_fn, flush_fn = observe(engine, db)
        try:
            with pytest.raises(HTTPException) as exc:
                bind(db, approval_id, document_id, version)
        finally:
            release(engine, db, sql_fn, flush_fn)
        assert exc.value.status_code == 409
        assert "Case has uncommitted changes" in str(exc.value.detail)
        assert not flushes and set(statements) <= {"SELECT"}
        assert parent.state == CaseState.CLOSED and parent in db.dirty
        assert pending in db.new
        db.rollback()
    with Session(engine) as check:
        assert check.get(Case, approval.case_id).state == CaseState.INSPECTION_COMPLETED
        assert check.scalar(select(func.count(InspectionApprovalDocumentLink.id))) == 0
        assert check.scalar(select(func.count(AuditEvent.id))) == 0
        assert check.scalar(select(func.count(Company.id))) == 1


def test_missing_document_does_not_flush_pending_draft(seeded):
    engine, (approval_id, _, _, version) = seeded
    with Session(engine, autoflush=True) as db:
        pending = Company(legal_name="Unrelated pending Company")
        db.add(pending)
        statements, flushes, sql_fn, flush_fn = observe(engine, db)
        try:
            with pytest.raises(HTTPException) as exc:
                bind(db, approval_id, str(uuid4()), version)
        finally:
            release(engine, db, sql_fn, flush_fn)
        assert exc.value.status_code == 404
        assert not flushes
        assert statements and set(statements) == {"SELECT"}
        assert pending in db.new
        db.rollback()


def test_independent_document_reparent_fails_closed(seeded):
    engine, (approval_id, document_id, other_case_id, version) = seeded
    with Session(engine, expire_on_commit=False) as db:
        cached = db.get(Document, document_id)
        with Session(engine) as writer:
            writer.get(Document, document_id).case_id = other_case_id
            writer.commit()
        with pytest.raises(HTTPException) as exc:
            bind(db, approval_id, document_id, version)
        assert exc.value.status_code == 422
        # A clean cached identity is refreshed from the committed document owner.
        assert cached.case_id == other_case_id
        db.rollback()
    with Session(engine) as check:
        assert check.scalar(select(func.count(InspectionApprovalDocumentLink.id))) == 0
        assert check.scalar(select(func.count(AuditEvent.id))) == 0


def test_clean_binding_remains_append_only_with_one_audit(seeded):
    engine, (approval_id, document_id, _, version) = seeded
    with Session(engine) as db:
        first = bind(db, approval_id, document_id, version)
        assert first["created"] is True
        db.commit()
        replay = bind(db, approval_id, document_id, first["row_version"])
        assert replay["created"] is False
        assert replay["binding_id"] == first["binding_id"]
        db.commit()
    with Session(engine) as check:
        assert check.scalar(select(func.count(InspectionApprovalDocumentLink.id))) == 1
        assert check.scalar(select(func.count(AuditEvent.id))) == 1
