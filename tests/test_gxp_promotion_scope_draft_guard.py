"""GxP current promotion must not flush unsaved candidate or current-peer scopes.

Synthetic SQLite. Both certificate versions are in one canonical Site/GxP context.
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

USER = build_authenticated_user("scope-promotion", "manager", permissions={"certificate.approve"})


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'gxp-promotion-scope-draft.sqlite').as_posix()}",
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
        peer = Certificate(
            site_id=site.id, certificate_type="GMP",
            issuance_basis="administrative_no_inspection", latest_flag=True,
        )
        candidate = Certificate(
            site_id=site.id, certificate_type="GMP",
            issuance_basis="administrative_no_inspection", latest_flag=False,
        )
        db.add_all([peer, candidate])
        db.flush()
        peer_version = CertificateVersion(
            certificate_id=peer.id, version_no=1, is_latest_version=True,
            certificate_number="PEER-GMP", issue_date=date(2026, 11, 1),
            expiry_date=date(2029, 11, 1),
        )
        candidate_version = CertificateVersion(
            certificate_id=candidate.id, version_no=1, is_latest_version=True,
            certificate_number="CANDIDATE-GMP", issue_date=date(2026, 11, 2),
            expiry_date=date(2029, 11, 2),
        )
        db.add_all([peer_version, candidate_version])
        db.flush()
        peer_scope = CertificateScope(
            certificate_version_id=peer_version.id,
            scope_key="PEER", scope_text="Persisted peer scope", sort_order=1,
        )
        candidate_scope = CertificateScope(
            certificate_version_id=candidate_version.id,
            scope_key="CANDIDATE", scope_text="Persisted candidate scope", sort_order=1,
        )
        db.add_all([peer_scope, candidate_scope])
        db.commit()
        ids = (
            candidate.id, peer.id, candidate_version.id, peer_version.id,
            candidate_scope.id, peer_scope.id, candidate.row_version,
        )
    try:
        yield engine, ids
    finally:
        engine.dispose()


@pytest.mark.parametrize("dirty_owner", [
    "candidate_scope", "current_scope", "pending_candidate_scope", "pending_current_scope",
])
def test_promotion_scope_drafts_rejected_before_flush(seeded, dirty_owner):
    engine, (candidate_id, peer_id, candidate_v, peer_v, candidate_scope_id, peer_scope_id, token) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        candidate_scope = db.get(CertificateScope, candidate_scope_id)
        peer_scope = db.get(CertificateScope, peer_scope_id)
        if dirty_owner == "candidate_scope":
            candidate_scope.scope_text = "UNSAVED CANDIDATE"
            tracked, draft = candidate_scope, "UNSAVED CANDIDATE"
        elif dirty_owner == "current_scope":
            peer_scope.scope_text = "UNSAVED PEER"
            tracked, draft = peer_scope, "UNSAVED PEER"
        else:
            pending = CertificateScope(
                certificate_version_id=(
                    candidate_v if dirty_owner == "pending_candidate_scope" else peer_v
                ),
                scope_text="UNSAVED PENDING", scope_key="NEW", sort_order=2,
            )
            db.add(pending)
        unrelated = Company(legal_name="Unrelated pending owner")
        db.add(unrelated)
        statements, flushes = [], []

        def record(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement.lstrip().split(None, 1)[0].upper())

        def no_flush(*_args):
            flushes.append(True)
            raise AssertionError("Current promotion admission autoflushed scope")

        event.listen(engine, "before_cursor_execute", record)
        event.listen(db, "before_flush", no_flush)
        try:
            with pytest.raises(HTTPException) as exc:
                CaseWorkflowService().promote_certificate_current(
                    db, certificate_id=candidate_id, expected_version=token,
                    reason="Synthetic scope-draft admission", user=USER,
                )
        finally:
            event.remove(engine, "before_cursor_execute", record)
            event.remove(db, "before_flush", no_flush)
        assert exc.value.status_code == 409
        assert "Certificate scope has uncommitted changes" in str(exc.value.detail)
        assert set(statements) <= {"SELECT"} and not flushes
        assert unrelated in db.new
        if dirty_owner.startswith("pending"):
            assert pending in db.new and pending.scope_text == "UNSAVED PENDING"
        else:
            assert tracked in db.dirty and tracked.scope_text == draft
        db.rollback()

    with Session(engine) as check:
        assert check.get(Certificate, peer_id).latest_flag is True
        assert check.get(Certificate, candidate_id).latest_flag is False
        assert check.get(CertificateScope, candidate_scope_id).scope_text == "Persisted candidate scope"
        assert check.get(CertificateScope, peer_scope_id).scope_text == "Persisted peer scope"
        assert check.scalar(select(func.count(CertificateScope.id))) == 2
        assert check.scalar(select(func.count(AuditEvent.id))) == 0
        assert check.scalar(select(func.count(Company.id))) == 1

@pytest.mark.parametrize("owner", ["candidate", "current_peer"])
def test_gxp_promotion_rejects_explicit_scope_deletion(seeded, owner):
    engine, (candidate_id, peer_id, candidate_v, peer_v, candidate_scope_id, peer_scope_id, token) = seeded
    scope_id = candidate_scope_id if owner == "candidate" else peer_scope_id
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        scope = db.get(CertificateScope, scope_id)
        db.delete(scope)
        unrelated = Company(legal_name="Pending unrelated Company")
        db.add(unrelated)
        sql, flushes = [], []

        def observe(_conn, _cursor, statement, _params, _context, _many):
            sql.append(statement.lstrip().split(None, 1)[0].upper())

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Deleted scope draft was autoflushed")

        event.listen(engine, "before_cursor_execute", observe)
        event.listen(db, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as exc:
                CaseWorkflowService().promote_certificate_current(
                    db, certificate_id=candidate_id, expected_version=token,
                    reason="Deleted scope draft", user=USER,
                )
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            event.remove(db, "before_flush", forbid_flush)
        assert exc.value.status_code == 409
        assert "Certificate scope has uncommitted changes" in str(exc.value.detail)
        assert set(sql) <= {"SELECT"} and not flushes
        assert scope in db.deleted and unrelated in db.new
        db.rollback()
    with Session(engine) as check:
        assert check.get(CertificateScope, scope_id) is not None
        assert check.get(Certificate, candidate_id).latest_flag is False
        assert check.get(Certificate, peer_id).latest_flag is True
        assert check.scalar(select(func.count(AuditEvent.id))) == 0


def test_gxp_promotion_rejects_scope_reparented_from_unrelated_version(seeded):
    engine, (candidate_id, peer_id, candidate_v, peer_v, candidate_scope_id, peer_scope_id, token) = seeded
    with Session(engine) as db:
        site_id = db.get(Certificate, candidate_id).site_id
        other_certificate = Certificate(
            site_id=site_id, certificate_type="GSP",
            issuance_basis="administrative_no_inspection", latest_flag=False,
        )
        db.add(other_certificate)
        db.flush()
        other_version = CertificateVersion(
            certificate_id=other_certificate.id, version_no=1, is_latest_version=True,
            certificate_number="OTHER-CERT", issue_date=date(2026, 10, 1),
        )
        db.add(other_version)
        db.flush()
        foreign_scope = CertificateScope(
            certificate_version_id=other_version.id, scope_key="OTHER",
            scope_text="Persisted other scope", sort_order=1,
        )
        db.add(foreign_scope)
        db.commit()
        foreign_scope_id, foreign_version_id = foreign_scope.id, other_version.id

    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        foreign_scope = db.get(CertificateScope, foreign_scope_id)
        foreign_scope.certificate_version_id = candidate_v
        unrelated = Company(legal_name="Unrelated pending Company")
        db.add(unrelated)
        sql, flushes = [], []

        def observe(_conn, _cursor, statement, _params, _context, _many):
            sql.append(statement.lstrip().split(None, 1)[0].upper())

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("Locally reparented scope must not flush with promotion")

        event.listen(engine, "before_cursor_execute", observe)
        event.listen(db, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as exc:
                CaseWorkflowService().promote_certificate_current(
                    db, certificate_id=candidate_id, expected_version=token,
                    reason="Synthetic incoming scope reparent", user=USER,
                )
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            event.remove(db, "before_flush", forbid_flush)

        assert exc.value.status_code == 409
        assert "Certificate scope has uncommitted changes" in str(exc.value.detail)
        assert set(sql) <= {"SELECT"} and not flushes
        assert foreign_scope in db.dirty and foreign_scope.certificate_version_id == candidate_v
        assert unrelated in db.new
        db.rollback()

    with Session(engine) as check:
        assert check.get(CertificateScope, foreign_scope_id).certificate_version_id == foreign_version_id
        assert check.get(Certificate, candidate_id).latest_flag is False
        assert check.get(Certificate, peer_id).latest_flag is True
        assert check.get(CertificateScope, candidate_scope_id).scope_text == "Persisted candidate scope"
        assert check.get(CertificateScope, peer_scope_id).scope_text == "Persisted peer scope"
        assert check.scalar(select(func.count(AuditEvent.id))) == 0
