"""Certificate current promotion must preserve cached unsaved owner drafts.

Synthetic isolated SQLite verifies SELECT-only rejected admission.
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
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Certificate, CertificateVersion, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


USER = build_authenticated_user(
    "certificate-promotion-draft", "manager", permissions={"certificate.approve"},
)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'cert-promotion-draft.sqlite').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Persisted Company")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Persisted Site")
        db.add(site)
        db.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.AWAITING_CERTIFICATE_DECISION)
        db.add(case)
        db.flush()
        certificate = Certificate(
            site_id=site.id, case_id=case.id, certificate_type="GMP",
            issuance_basis="inspection_case", latest_flag=False,
        )
        db.add(certificate)
        db.flush()
        version = CertificateVersion(
            certificate_id=certificate.id, version_no=1, is_latest_version=True,
            certificate_number="PERSISTED-GMP", issue_date=date(2026, 11, 1),
            expiry_date=date(2029, 11, 1),
        )
        db.add(version)
        db.commit()
        ids = certificate.id, site.id, case.id, version.id, certificate.row_version
    try:
        yield engine, ids
    finally:
        engine.dispose()


@pytest.mark.parametrize("dirty_owner", ["certificate", "site", "case", "version"])
def test_promotion_does_not_flush_or_refresh_unsaved_owner(seeded, dirty_owner):
    engine, (certificate_id, site_id, case_id, version_id, expected_version) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        cert = db.get(Certificate, certificate_id)
        site = db.get(Site, site_id)
        case = db.get(Case, case_id)
        version = db.get(CertificateVersion, version_id)
        if dirty_owner == "certificate":
            cert.latest_flag = True
        elif dirty_owner == "site":
            site.site_name = "Unsaved Site"
        elif dirty_owner == "case":
            case.state = CaseState.CANCELLED
        else:
            version.certificate_number = "UNSAVED-VERSION"
        pending = Company(legal_name="Pending Company")
        db.add(pending)
        sql, flushes = [], []

        def observe(_conn, _cursor, statement, _params, _context, _many):
            sql.append(statement.lstrip().split(None, 1)[0].upper())

        def no_flush(*_args):
            flushes.append(True)
            raise AssertionError("Promotion admission must not autoflush operator drafts")

        event.listen(engine, "before_cursor_execute", observe)
        event.listen(db, "before_flush", no_flush)
        try:
            with pytest.raises(HTTPException) as exc:
                CaseWorkflowService().promote_certificate_current(
                    db, certificate_id=certificate_id, expected_version=expected_version,
                    reason="Synthetic owner draft", user=USER,
                )
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            event.remove(db, "before_flush", no_flush)
        assert exc.value.status_code == 409
        assert "uncommitted changes" in str(exc.value.detail)
        assert set(sql) <= {"SELECT"} and not flushes
        assert pending in db.new
        if dirty_owner == "certificate":
            assert cert.latest_flag is True and cert in db.dirty
        elif dirty_owner == "site":
            assert site.site_name == "Unsaved Site" and site in db.dirty
        elif dirty_owner == "case":
            assert case.state == CaseState.CANCELLED and case in db.dirty
        else:
            assert version.certificate_number == "UNSAVED-VERSION" and version in db.dirty
        db.rollback()
    with Session(engine) as check:
        assert check.get(Certificate, certificate_id).latest_flag is False
        assert check.get(Site, site_id).site_name == "Persisted Site"
        assert check.get(Case, case_id).state == CaseState.AWAITING_CERTIFICATE_DECISION
        assert check.get(CertificateVersion, version_id).certificate_number == "PERSISTED-GMP"
        assert check.scalar(select(func.count(AuditEvent.id))) == 0
        assert check.scalar(select(func.count(Company.id))) == 1
