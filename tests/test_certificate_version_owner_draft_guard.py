"""Certificate latest-version edit preserves unsaved aggregate-root and child drafts.

Isolated synthetic SQLite; service-owner mutation rejects before SQL writes.
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
    AuditEvent, Certificate, CertificateScope, CertificateVersion, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


USER = build_authenticated_user("certificate-edit-draft", "manager", permissions={"certificate.edit"})


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'certificate-version-edit-draft.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Committed Company")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Committed Site")
        db.add(site)
        db.flush()
        cert = Certificate(
            site_id=site.id, certificate_type="GMP",
            issuance_basis="administrative_no_inspection", latest_flag=False,
        )
        db.add(cert)
        db.flush()
        version = CertificateVersion(
            certificate_id=cert.id, version_no=1, is_latest_version=True,
            certificate_number="COMMITTED-001", issue_date=date(2026, 11, 1),
            expiry_date=date(2029, 11, 1),
        )
        db.add(version)
        db.commit()
        ids = cert.id, version.id, cert.row_version
    try:
        yield engine, ids
    finally:
        engine.dispose()


@pytest.mark.parametrize("dirty_owner", ["certificate", "version"])
def test_unsaved_certificate_owner_rejected_without_draft_loss_or_sql_write(seeded, dirty_owner):
    engine, (certificate_id, version_id, expected_version) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        cert = db.get(Certificate, certificate_id)
        version = db.get(CertificateVersion, version_id)
        if dirty_owner == "certificate":
            cert.latest_flag = True
        else:
            version.certificate_number = "UNCOMMITTED-OPERATOR-DRAFT"
        pending = Company(legal_name="Unrelated pending Company")
        db.add(pending)
        statements, flushes = [], []

        def sql_observer(_connection, _cursor, statement, _params, _context, _many):
            statements.append(statement.lstrip().split(None, 1)[0].upper())

        def no_flush(*_args):
            flushes.append(True)
            raise AssertionError("Version edit admission autoflushed a draft")

        event.listen(engine, "before_cursor_execute", sql_observer)
        event.listen(db, "before_flush", no_flush)
        try:
            with pytest.raises(HTTPException) as exc:
                CaseWorkflowService().upsert_certificate_latest_version(
                    db, certificate_id=certificate_id, expected_version=expected_version,
                    certificate_number="NEW-001", issue_date=date(2026, 11, 2),
                    expiry_date=date(2029, 11, 2), scopes=[],
                    reason="Synthetic draft guard", user=USER,
                )
        finally:
            event.remove(engine, "before_cursor_execute", sql_observer)
            event.remove(db, "before_flush", no_flush)

        assert exc.value.status_code == 409
        assert "uncommitted changes" in str(exc.value.detail)
        assert set(statements) <= {"SELECT"}
        assert not flushes
        assert pending in db.new
        if dirty_owner == "certificate":
            assert cert.latest_flag is True and cert in db.dirty
        else:
            assert version.certificate_number == "UNCOMMITTED-OPERATOR-DRAFT"
            assert version in db.dirty
        db.rollback()

    with Session(engine) as check:
        persisted_cert = check.get(Certificate, certificate_id)
        persisted_version = check.get(CertificateVersion, version_id)
        assert persisted_cert.latest_flag is False
        assert persisted_version.certificate_number == "COMMITTED-001"
        assert persisted_version.issue_date == date(2026, 11, 1)
        assert check.scalar(select(func.count(CertificateScope.id))) == 0
        assert check.scalar(select(func.count(AuditEvent.id))) == 0
        assert check.scalar(select(func.count(Company.id))) == 1
