"""GxP scope-replacement admission preserves cached and pending operator children.

Synthetic isolated SQLite; no deployment or rehearsal data.
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

USER = build_authenticated_user(
    "scope-owner-draft", "manager", permissions={"certificate.edit"},
)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'gxp-scope-draft.sqlite').as_posix()}",
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
        cert = Certificate(
            site_id=site.id, certificate_type="GMP",
            issuance_basis="administrative_no_inspection", latest_flag=False,
        )
        db.add(cert)
        db.flush()
        version = CertificateVersion(
            certificate_id=cert.id, version_no=1, is_latest_version=True,
            certificate_number="COMMITTED", issue_date=date(2026, 11, 1),
            expiry_date=date(2029, 11, 1),
        )
        db.add(version)
        db.flush()
        scope = CertificateScope(
            certificate_version_id=version.id, scope_key="A",
            scope_text="Committed scope", language_code="vi", sort_order=1,
        )
        db.add(scope)
        db.commit()
        ids = cert.id, version.id, scope.id, cert.row_version
    try:
        yield engine, ids
    finally:
        engine.dispose()


@pytest.mark.parametrize("dirty_mode", ["scope_text", "sort_order", "pending_scope"])
def test_certificate_version_edit_fences_draft_scope_before_write(seeded, dirty_mode):
    engine, (cert_id, version_id, scope_id, token) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        scope = db.get(CertificateScope, scope_id)
        if dirty_mode == "scope_text":
            scope.scope_text = "Operator draft"
        elif dirty_mode == "sort_order":
            scope.sort_order = 9
        else:
            pending_scope = CertificateScope(
                certificate_version_id=version_id,
                scope_key="NEW", scope_text="Pending scope", sort_order=2,
            )
            db.add(pending_scope)
        unrelated = Company(legal_name="Unrelated pending Company")
        db.add(unrelated)
        statements, flushes = [], []

        def sql_observer(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement.lstrip().split(None, 1)[0].upper())

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Scope edit admission must not autoflush drafts")

        event.listen(engine, "before_cursor_execute", sql_observer)
        event.listen(db, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as exc:
                CaseWorkflowService().upsert_certificate_latest_version(
                    db, certificate_id=cert_id, expected_version=token,
                    certificate_number="MUTATION", issue_date=date(2026, 11, 2),
                    expiry_date=date(2029, 11, 2),
                    scopes=[{"scope_key":"A","scope_text":"New submitted scope"}],
                    reason="Synthetic scope draft admission", user=USER,
                )
        finally:
            event.remove(engine, "before_cursor_execute", sql_observer)
            event.remove(db, "before_flush", forbid_flush)

        assert exc.value.status_code == 409
        assert "Certificate scope has uncommitted changes" in str(exc.value.detail)
        assert set(statements) <= {"SELECT"} and not flushes
        assert unrelated in db.new
        if dirty_mode == "pending_scope":
            assert pending_scope in db.new and pending_scope.scope_text == "Pending scope"
        elif dirty_mode == "scope_text":
            assert scope in db.dirty and scope.scope_text == "Operator draft"
        else:
            assert scope in db.dirty and scope.sort_order == 9
        db.rollback()

    with Session(engine) as check:
        assert check.get(CertificateVersion, version_id).certificate_number == "COMMITTED"
        assert check.get(CertificateScope, scope_id).scope_text == "Committed scope"
        assert check.get(CertificateScope, scope_id).sort_order == 1
        assert check.scalar(select(func.count(CertificateScope.id))) == 1
        assert check.scalar(select(func.count(AuditEvent.id))) == 0
        assert check.scalar(select(func.count(Company.id))) == 1
