"""ĐĐK creation must not commit an unsaved Site operator draft.

Synthetic isolated SQLite; mutation fails closed prior to actor/certificate/audit writes.
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
from backend.app.db.models.phase1 import (
    AuditEvent, BusinessEligibilityCertificate, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


USER = build_authenticated_user(
    "ddk-issue-site-draft", "manager", permissions={"certificate.issue"},
)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'ddk-issue-draft.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Committed owner")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Committed Site")
        db.add(site)
        db.commit()
        site_id = site.id
    try:
        yield engine, site_id
    finally:
        engine.dispose()


@pytest.mark.parametrize("dirty_field", ["site_name", "company_id"])
def test_ddk_issue_rejects_dirty_site_before_any_mutation(seeded, dirty_field):
    engine, site_id = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        site = db.get(Site, site_id)
        drafted_value = "Operator draft" if dirty_field == "site_name" else str(uuid4())
        setattr(site, dirty_field, drafted_value)
        pending = Company(legal_name="Unrelated pending Company")
        db.add(pending)
        statements, flushes = [], []

        def on_sql(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement.lstrip().split(None, 1)[0].upper())

        def no_flush(*_args):
            flushes.append(True)
            raise AssertionError("ĐĐK issuance must not flush cached operator drafts")

        event.listen(engine, "before_cursor_execute", on_sql)
        event.listen(db, "before_flush", no_flush)
        try:
            with pytest.raises(HTTPException) as exc:
                CaseWorkflowService().issue_business_eligibility(
                    db,
                    site_id=site_id,
                    certificate_number="SYNTHETIC",
                    issued_on=date(2026, 11, 18),
                    expires_on=date(2029, 11, 18),
                    professional_responsible_person_name="Synthetic Person",
                    notes=None,
                    linked_certificates=[],
                    reason="Synthetic owner draft regression",
                    user=USER,
                )
        finally:
            event.remove(engine, "before_cursor_execute", on_sql)
            event.remove(db, "before_flush", no_flush)
        assert exc.value.status_code == 409
        if dirty_field == "company_id":
            assert "Site/Company owner changed" in str(exc.value.detail)
        else:
            assert "Site has uncommitted changes" in str(exc.value.detail)
        assert set(statements) <= {"SELECT"}
        assert not flushes
        assert site in db.dirty and getattr(site, dirty_field) == drafted_value
        assert pending in db.new
        db.rollback()

    with Session(engine) as check:
        persisted = check.get(Site, site_id)
        assert persisted.site_name == "Committed Site"
        assert persisted.company_id != drafted_value
        assert check.scalar(select(func.count(BusinessEligibilityCertificate.id))) == 0
        assert check.scalar(select(func.count(AuditEvent.id))) == 0
        assert check.scalar(select(func.count(Company.id))) == 1
