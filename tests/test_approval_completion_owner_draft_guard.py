"""Approval completion owner admission must not flush or overwrite operator drafts.

Synthetic SQLite only. Mutation behavior stays versioned and Case-locked.
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Company, InspectionApprovalDocumentLink, InspectionApprovalSubmission, Site,
)
from backend.app.services.workflow import CaseWorkflowService


USER = build_authenticated_user(
    "approval-owner-regression", "manager", permissions={"inspection.edit"},
)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'approval-completion-drafts.sqlite').as_posix()}",
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
        other_case = Case(
            site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED,
        )
        db.add_all((case, other_case))
        db.flush()
        submission = InspectionApprovalSubmission(
            case_id=case.id, stage="PCT", round_no=1,
            reference="Committed reference", submitted_on=date(2026, 11, 15),
        )
        db.add(submission)
        db.commit()
        ids = (submission.id, case.id, other_case.id, submission.row_version)
    try:
        yield engine, ids
    finally:
        engine.dispose()


def complete(db, submission_id, version):
    return CaseWorkflowService().complete_approval_submission(
        db, approval_submission_id=submission_id,
        expected_version=version, completed_on=date(2026, 11, 16),
        completed_time=None, reason="Synthetic regression", user=USER,
    )


def spy(engine, db):
    commands, flushes = [], []

    def on_sql(_conn, _cursor, statement, _params, _context, _many):
        commands.append(statement.lstrip().split(None, 1)[0].upper())

    def on_flush(*_args):
        flushes.append(True)
        raise AssertionError("Approval completion admission autoflushed a draft")

    event.listen(engine, "before_cursor_execute", on_sql)
    event.listen(db, "before_flush", on_flush)
    return commands, flushes, on_sql, on_flush


def unspy(engine, db, on_sql, on_flush):
    event.remove(engine, "before_cursor_execute", on_sql)
    event.remove(db, "before_flush", on_flush)


def test_dirty_submission_is_rejected_without_autoflush_or_refresh(seeded):
    engine, (submission_id, case_id, _, version) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        cached = db.get(InspectionApprovalSubmission, submission_id)
        cached.reference = "Operator's uncommitted approval reference"
        pending = Company(legal_name="Uncommitted operator Company")
        db.add(pending)
        commands, flushes, on_sql, on_flush = spy(engine, db)
        try:
            with pytest.raises(HTTPException) as exc:
                complete(db, submission_id, version)
        finally:
            unspy(engine, db, on_sql, on_flush)
        assert exc.value.status_code == 409
        assert not flushes
        assert all(command == "SELECT" for command in commands)
        assert cached.reference == "Operator's uncommitted approval reference"
        assert cached.case_id == case_id
        assert cached in db.dirty
        assert pending in db.new
        db.rollback()

    with Session(engine) as verify:
        submission = verify.get(InspectionApprovalSubmission, submission_id)
        assert submission.reference == "Committed reference"
        assert submission.completed_on is None
        assert verify.scalar(select(func.count(Company.id))) == 1
        assert verify.scalar(select(func.count(AuditEvent.id))) == 0



def test_dirty_case_parent_rejected_before_completion_refresh(seeded):
    engine, (submission_id, case_id, _, version) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        case = db.get(Case, case_id)
        case.state = CaseState.CLOSED
        pending = Company(legal_name="Uncommitted Company during completion")
        db.add(pending)
        commands, flushes, on_sql, on_flush = spy(engine, db)
        try:
            with pytest.raises(HTTPException) as exc:
                complete(db, submission_id, version)
        finally:
            unspy(engine, db, on_sql, on_flush)
        assert exc.value.status_code == 409
        assert "Case has uncommitted changes" in str(exc.value.detail)
        assert not flushes and set(commands) <= {"SELECT"}
        assert case.state == CaseState.CLOSED and case in db.dirty
        assert pending in db.new
        db.rollback()

    with Session(engine) as check:
        assert check.get(Case, case_id).state == CaseState.INSPECTION_COMPLETED
        assert check.get(InspectionApprovalSubmission, submission_id).completed_on is None
        assert check.scalar(select(func.count(Company.id))) == 1
        assert check.scalar(select(func.count(AuditEvent.id))) == 0


def test_missing_submission_does_not_flush_unrelated_draft(seeded):
    engine, _ = seeded
    with Session(engine, autoflush=True) as db:
        pending = Company(legal_name="Uncommitted operator Company")
        db.add(pending)
        commands, flushes, on_sql, on_flush = spy(engine, db)
        try:
            with pytest.raises(HTTPException) as exc:
                complete(db, str(uuid4()), 1)
        finally:
            unspy(engine, db, on_sql, on_flush)
        assert exc.value.status_code == 404
        assert not flushes
        assert all(command == "SELECT" for command in commands)
        assert pending in db.new
        db.rollback()


def test_cached_old_case_owner_does_not_authorize_completion(seeded):
    engine, (submission_id, case_id, new_case_id, version) = seeded
    with Session(engine, expire_on_commit=False) as db:
        cached = db.get(InspectionApprovalSubmission, submission_id)
        assert cached.case_id == case_id
        with Session(engine) as writer:
            writer.get(InspectionApprovalSubmission, submission_id).case_id = new_case_id
            writer.commit()
        with pytest.raises(HTTPException) as exc:
            complete(db, submission_id, version)
        assert exc.value.status_code == 409
        db.rollback()
    with Session(engine) as verify:
        persisted = verify.get(InspectionApprovalSubmission, submission_id)
        assert persisted.case_id == new_case_id
        assert persisted.completed_on is None
        assert verify.scalar(select(func.count(AuditEvent.id))) == 0


def test_clean_completion_preserves_timeline_version_and_audit(seeded):
    engine, (submission_id, _, _, version) = seeded
    with Session(engine) as db:
        result = complete(db, submission_id, version)
        assert result["completed_on"] == date(2026, 11, 16)
        db.commit()
    with Session(engine) as verify:
        persisted = verify.get(InspectionApprovalSubmission, submission_id)
        assert persisted.completed_on == date(2026, 11, 16)
        assert persisted.row_version == version + 1
        assert verify.scalar(select(func.count(AuditEvent.id))) == 1


@pytest.mark.parametrize("pending_link", [True, False])
def test_completion_rejects_same_round_link_draft_without_flush(seeded, pending_link):
    """Completing PCT must not persist an unrelated round-document draft."""
    engine, (submission_id, _, other_case_id, version) = seeded
    with Session(engine) as seed:
        other = InspectionApprovalSubmission(
            case_id=other_case_id, stage="PCT", round_no=1,
        )
        seed.add(other)
        seed.flush()
        link = InspectionApprovalDocumentLink(
            approval_submission_id=(
                submission_id if pending_link else other.id
            ),
            document_id=str(uuid4()),
        )
        if not pending_link:
            seed.add(link)
        seed.commit()
        link_id = None if pending_link else link.id
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        if pending_link:
            cached = InspectionApprovalDocumentLink(
                approval_submission_id=submission_id, document_id=str(uuid4()),
            )
            db.add(cached)
        else:
            cached = db.get(InspectionApprovalDocumentLink, link_id)
            cached.approval_submission_id = submission_id
        statements, flushes, sql_fn, flush_fn = spy(engine, db)
        try:
            with pytest.raises(HTTPException) as exc:
                complete(db, submission_id, version)
        finally:
            unspy(engine, db, sql_fn, flush_fn)
        assert exc.value.status_code == 409
        assert "Approval document link has uncommitted changes" in str(exc.value.detail)
        assert not flushes and set(statements) <= {"SELECT"}
        assert cached in (db.new if pending_link else db.dirty)
        db.rollback()
    with Session(engine) as check:
        assert check.get(InspectionApprovalSubmission, submission_id).completed_on is None
        assert check.scalar(select(func.count(InspectionApprovalDocumentLink.id))) == (
            0 if pending_link else 1
        )
        assert check.scalar(select(func.count(AuditEvent.id))) == 0
