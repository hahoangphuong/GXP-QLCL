"""Certificate issuance must not refresh or autoflush unsaved Case drafts.

Synthetic isolated SQLite; exercises the authoritative service mutation path.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import AuditEvent, Case, Certificate, Company, Site
from backend.app.services.workflow import CaseWorkflowService


USER = build_authenticated_user(
    "certificate-issue-case-draft", "manager",
    permissions={"certificate.issue"},
)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'certificate-issue-draft.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Committed owner")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Original Site")
        other_site = Site(company_id=company.id, site_name="Other Site")
        db.add_all((site, other_site))
        db.flush()
        case = Case(
            site_id=site.id, gxp_type="GMP",
            state=CaseState.AWAITING_CERTIFICATE_DECISION,
        )
        db.add(case)
        db.commit()
        ids = case.id, site.id, other_site.id
    try:
        yield engine, ids
    finally:
        engine.dispose()


@pytest.mark.parametrize("dirty_field", ["state", "site_id"])
def test_dirty_case_rejected_before_issuance_lock_refresh(seeded, dirty_field):
    engine, (case_id, site_id, other_site_id) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        cached = db.get(Case, case_id)
        if dirty_field == "state":
            cached.state = CaseState.CANCELLED
            expected_draft = CaseState.CANCELLED
        else:
            cached.site_id = other_site_id
            expected_draft = other_site_id
        pending = Company(legal_name="Uncommitted unrelated Company")
        db.add(pending)
        statements, flushes = [], []

        def on_sql(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement.lstrip().split(None, 1)[0].upper())

        def no_flush(*_args):
            flushes.append(True)
            raise AssertionError("Certificate issuance admission autoflushed operator draft")

        event.listen(engine, "before_cursor_execute", on_sql)
        event.listen(db, "before_flush", no_flush)
        try:
            with pytest.raises(HTTPException) as exc:
                CaseWorkflowService().issue_certificate(
                    db,
                    site_id=site_id,
                    case_id=case_id,
                    certificate_type="GMP",
                    issuance_basis="inspection_case",
                    certificate_number="SYNTHETIC",
                    issue_date=date(2026, 11, 18),
                    expiry_date=date(2029, 11, 18),
                    scopes=[],
                    reason="Synthetic regression",
                    user=USER,
                )
        finally:
            event.remove(engine, "before_cursor_execute", on_sql)
            event.remove(db, "before_flush", no_flush)

        assert exc.value.status_code == 409
        assert "Case has uncommitted changes" in str(exc.value.detail)
        assert not flushes and set(statements) <= {"SELECT"}
        assert cached in db.dirty
        assert getattr(cached, dirty_field) == expected_draft
        assert pending in db.new
        db.rollback()

    with Session(engine) as check:
        persisted = check.get(Case, case_id)
        assert persisted.state == CaseState.AWAITING_CERTIFICATE_DECISION
        assert persisted.site_id == site_id
        assert check.scalar(select(func.count(Certificate.id))) == 0
        assert check.scalar(select(func.count(AuditEvent.id))) == 0
        assert check.scalar(select(func.count(Company.id))) == 1
