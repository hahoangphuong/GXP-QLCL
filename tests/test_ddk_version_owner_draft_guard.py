"""DDK latest-version mutation must preserve cached operator drafts.

Synthetic SQLite with directly seeded persisted DDK aggregate and child version.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import (
    AuditEvent, BusinessEligibilityCertificate, BusinessEligibilityVersion,
    BusinessEligibilityCertificateLink, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


USER = build_authenticated_user(
    "ddk-version-draft", "manager", permissions={"certificate.edit"},
)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'ddk-version-draft.sqlite').as_posix()}", future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Committed company")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Committed Site")
        db.add(site)
        db.flush()
        cert = BusinessEligibilityCertificate(
            site_id=site.id, company_id=company.id, latest_flag=False,
        )
        db.add(cert)
        db.flush()
        version = BusinessEligibilityVersion(
            business_eligibility_certificate_id=cert.id, version_no=1,
            is_latest_version=True, certificate_number="DDK-COMMITTED",
            issued_on=date(2026, 11, 1), expires_on=date(2029, 11, 1),
        )
        db.add(version)
        db.commit()
        ids = cert.id, version.id, cert.row_version
    try:
        yield engine, ids
    finally:
        engine.dispose()


@pytest.mark.parametrize("dirty_owner", ["certificate", "version"])
def test_dirty_ddk_identity_is_not_refreshed_or_flushed_on_version_edit(seeded, dirty_owner):
    engine, (cert_id, version_id, expected_version) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        cert = db.get(BusinessEligibilityCertificate, cert_id)
        version = db.get(BusinessEligibilityVersion, version_id)
        if dirty_owner == "certificate":
            cert.latest_flag = True
        else:
            version.notes = "Uncommitted operator draft"
        pending = Company(legal_name="Unrelated pending company")
        db.add(pending)
        sql, flushes = [], []

        def watch_sql(_conn, _cursor, statement, _params, _context, _many):
            sql.append(statement.lstrip().split(None, 1)[0].upper())

        def no_flush(*_args):
            flushes.append(True)
            raise AssertionError("DDK edit admission autoflushed operator draft")

        event.listen(engine, "before_cursor_execute", watch_sql)
        event.listen(db, "before_flush", no_flush)
        try:
            with pytest.raises(HTTPException) as exc:
                CaseWorkflowService().upsert_business_eligibility_latest_version(
                    db, business_eligibility_certificate_id=cert_id,
                    expected_version=expected_version, certificate_number="DDK-NEW",
                    issued_on=date(2026, 11, 2), expires_on=date(2029, 11, 2),
                    professional_responsible_person_name=None, notes="Mutation",
                    linked_certificates=[], reason="Synthetic test", user=USER,
                )
        finally:
            event.remove(engine, "before_cursor_execute", watch_sql)
            event.remove(db, "before_flush", no_flush)

        assert exc.value.status_code == 409
        assert "uncommitted changes" in str(exc.value.detail)
        assert set(sql) <= {"SELECT"}
        assert not flushes
        assert pending in db.new
        if dirty_owner == "certificate":
            assert cert.latest_flag is True and cert in db.dirty
        else:
            assert version.notes == "Uncommitted operator draft" and version in db.dirty
        db.rollback()

    with Session(engine) as check:
        assert check.get(BusinessEligibilityCertificate, cert_id).latest_flag is False
        assert check.get(BusinessEligibilityVersion, version_id).certificate_number == "DDK-COMMITTED"
        assert check.get(BusinessEligibilityVersion, version_id).notes is None
        assert check.scalar(select(func.count(BusinessEligibilityCertificateLink.id))) == 0
        assert check.scalar(select(func.count(AuditEvent.id))) == 0
        assert check.scalar(select(func.count(Company.id))) == 1
