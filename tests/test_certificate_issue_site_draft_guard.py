"""GxP candidate creation must not flush unsaved Site operator drafts.

Both Case-backed and administrative issuance use the canonical Site owner.
Synthetic isolated SQLite, no deployment or rehearsal data.
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
from backend.app.db.models.phase1 import AuditEvent, Case, Certificate, Company, Site
from backend.app.services.workflow import CaseWorkflowService


USER = build_authenticated_user(
    "gxp-site-draft", "manager", permissions={"certificate.issue"},
)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'gxp-issue-site-draft.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Committed owner")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Committed Site")
        db.add(site)
        db.flush()
        case = Case(
            site_id=site.id,
            gxp_type="GMP",
            state=CaseState.AWAITING_CERTIFICATE_DECISION,
        )
        db.add(case)
        db.commit()
        ids = site.id, case.id
    try:
        yield engine, ids
    finally:
        engine.dispose()


@pytest.mark.parametrize("dirty_field", ["site_name", "company_id"])
@pytest.mark.parametrize("case_backed", [True, False])
def test_issue_rejects_unsaved_site_draft_without_autoflush(seeded, dirty_field, case_backed):
    engine, (site_id, case_id) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        site = db.get(Site, site_id)
        draft = "Operator Site draft" if dirty_field == "site_name" else str(uuid4())
        setattr(site, dirty_field, draft)
        pending = Company(legal_name="Unrelated uncommitted owner")
        db.add(pending)
        statements, flushes = [], []

        def on_sql(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement.lstrip().split(None, 1)[0].upper())

        def no_flush(*_args):
            flushes.append(True)
            raise AssertionError("Site draft autoflushed during certificate issuance admission")

        event.listen(engine, "before_cursor_execute", on_sql)
        event.listen(db, "before_flush", no_flush)
        try:
            with pytest.raises(HTTPException) as exc:
                CaseWorkflowService().issue_certificate(
                    db,
                    site_id=site_id,
                    case_id=case_id if case_backed else None,
                    certificate_type="GMP",
                    issuance_basis="inspection_case" if case_backed else "administrative_no_inspection",
                    certificate_number="SYNTHETIC",
                    issue_date=date(2026, 11, 18),
                    expiry_date=date(2029, 11, 18),
                    scopes=[],
                    reason="Synthetic Site draft regression",
                    user=USER,
                )
        finally:
            event.remove(engine, "before_cursor_execute", on_sql)
            event.remove(db, "before_flush", no_flush)

        assert exc.value.status_code == 409
        assert "Site has uncommitted changes" in str(exc.value.detail)
        assert set(statements) <= {"SELECT"}
        assert not flushes
        assert site in db.dirty and getattr(site, dirty_field) == draft
        assert pending in db.new
        db.rollback()
    with Session(engine) as check:
        committed = check.get(Site, site_id)
        assert committed.site_name == "Committed Site"
        assert committed.company_id != draft
        assert check.scalar(select(func.count(Certificate.id))) == 0
        assert check.scalar(select(func.count(AuditEvent.id))) == 0
        assert check.scalar(select(func.count(Company.id))) == 1
