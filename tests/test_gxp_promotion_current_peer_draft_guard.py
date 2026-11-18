"""GxP current promotion cannot refresh dirty DB-current peer identities.

Synthetic SQLite exercises reused Session current peer root, Version and linked Case.
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

USER = build_authenticated_user("gxp-peer-draft", "manager", permissions={"certificate.approve"})


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'gxp-current-peer-draft.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Persisted owner")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Persisted Site")
        db.add(site)
        db.flush()
        peer_case = Case(
            site_id=site.id, gxp_type="GMP", scope_code=None,
            state=CaseState.AWAITING_CERTIFICATE_DECISION,
        )
        db.add(peer_case)
        db.flush()
        peer = Certificate(
            site_id=site.id, case_id=peer_case.id, certificate_type="GMP",
            issuance_basis="inspection_case", latest_flag=True,
        )
        candidate = Certificate(
            site_id=site.id, certificate_type="GMP",
            issuance_basis="administrative_no_inspection", latest_flag=False,
        )
        db.add_all([peer, candidate])
        db.flush()
        peer_version = CertificateVersion(
            certificate_id=peer.id, version_no=1, is_latest_version=True,
            certificate_number="OLD-GMP", issue_date=date(2026, 11, 1),
            expiry_date=date(2029, 11, 1),
        )
        candidate_version = CertificateVersion(
            certificate_id=candidate.id, version_no=1, is_latest_version=True,
            certificate_number="NEW-GMP", issue_date=date(2026, 11, 2),
            expiry_date=date(2029, 11, 2),
        )
        db.add_all([peer_version, candidate_version])
        db.commit()
        ids = candidate.id, peer.id, peer_case.id, peer_version.id, candidate.row_version
    try:
        yield engine, ids
    finally:
        engine.dispose()


@pytest.mark.parametrize("dirty_owner", ["peer", "peer_version", "peer_case"])
def test_gxp_promotion_rejects_current_peer_draft_before_refresh(seeded, dirty_owner):
    engine, (candidate_id, peer_id, case_id, peer_version_id, token) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        peer = db.get(Certificate, peer_id)
        version = db.get(CertificateVersion, peer_version_id)
        case = db.get(Case, case_id)
        if dirty_owner == "peer":
            peer.latest_flag = False
            tracked, attr, draft = peer, "latest_flag", False
        elif dirty_owner == "peer_version":
            version.certificate_number = "UNSAVED-GMP"
            tracked, attr, draft = version, "certificate_number", "UNSAVED-GMP"
        else:
            case.state = CaseState.CANCELLED
            tracked, attr, draft = case, "state", CaseState.CANCELLED
        pending = Company(legal_name="Unrelated pending Company")
        db.add(pending)
        statements, flushes = [], []

        def watch(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement.lstrip().split(None, 1)[0].upper())

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("GxP promotion must not autoflush peer drafts")

        event.listen(engine, "before_cursor_execute", watch)
        event.listen(db, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as exc:
                CaseWorkflowService().promote_certificate_current(
                    db, certificate_id=candidate_id, expected_version=token,
                    reason="Synthetic current-peer draft", user=USER,
                )
        finally:
            event.remove(engine, "before_cursor_execute", watch)
            event.remove(db, "before_flush", forbid_flush)
        assert exc.value.status_code == 409
        assert "uncommitted changes" in str(exc.value.detail)
        assert set(statements) <= {"SELECT"} and not flushes
        assert pending in db.new
        assert tracked in db.dirty
        assert getattr(tracked, attr) == draft
        db.rollback()

    with Session(engine) as check:
        assert check.get(Certificate, peer_id).latest_flag is True
        assert check.get(Certificate, candidate_id).latest_flag is False
        assert check.get(CertificateVersion, peer_version_id).certificate_number == "OLD-GMP"
        assert check.get(Case, case_id).state == CaseState.AWAITING_CERTIFICATE_DECISION
        assert check.scalar(select(func.count(AuditEvent.id))) == 0
        assert check.scalar(select(func.count(Company.id))) == 1
