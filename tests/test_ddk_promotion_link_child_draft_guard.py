"""ĐĐK current promotion rejects unsaved candidate/current-peer links.

Synthetic isolated SQLite. Promotion is not a link-edit mutation; no
CertificateLink drafts may be persisted as collateral effects of its flush.
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
    BusinessEligibilityCertificateLink, Certificate, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService

USER = build_authenticated_user(
    "ddk-link-promotion-draft", "manager", permissions={"certificate.approve"},
)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'ddk-link-promotion-draft.sqlite').as_posix()}",
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
        gxp = Certificate(
            site_id=site.id, certificate_type="GMP",
            issuance_basis="administrative_no_inspection", latest_flag=False,
        )
        db.add(gxp)
        db.flush()
        peer = BusinessEligibilityCertificate(
            site_id=site.id, company_id=company.id, latest_flag=True,
        )
        candidate = BusinessEligibilityCertificate(
            site_id=site.id, company_id=company.id, latest_flag=False,
        )
        db.add_all([peer, candidate])
        db.flush()
        peer_version = BusinessEligibilityVersion(
            business_eligibility_certificate_id=peer.id, version_no=1,
            certificate_number="OLD-DDK", issued_on=date(2026, 11, 1),
        )
        candidate_version = BusinessEligibilityVersion(
            business_eligibility_certificate_id=candidate.id, version_no=1,
            certificate_number="NEW-DDK", issued_on=date(2026, 11, 2),
        )
        db.add_all([peer_version, candidate_version])
        db.flush()
        peer_link = BusinessEligibilityCertificateLink(
            business_eligibility_version_id=peer_version.id,
            certificate_id=gxp.id, link_role="source_certificate",
        )
        candidate_link = BusinessEligibilityCertificateLink(
            business_eligibility_version_id=candidate_version.id,
            certificate_id=gxp.id, link_role="source_certificate",
        )
        db.add_all([peer_link, candidate_link])
        db.commit()
        ids = (
            candidate.id, peer.id, candidate_version.id, peer_version.id,
            candidate_link.id, peer_link.id, gxp.id, candidate.row_version,
        )
    try:
        yield engine, ids
    finally:
        engine.dispose()


@pytest.mark.parametrize("draft_owner", [
    "candidate_link", "current_peer_link",
    "pending_candidate_link", "pending_current_peer_link",
])
def test_ddk_promotion_rejects_draft_link_children_without_flush(seeded, draft_owner):
    engine, (candidate_id, peer_id, candidate_v, peer_v, candidate_link_id, peer_link_id, gxp_id, token) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        candidate_link = db.get(BusinessEligibilityCertificateLink, candidate_link_id)
        peer_link = db.get(BusinessEligibilityCertificateLink, peer_link_id)
        if draft_owner == "candidate_link":
            candidate_link.link_role = "supporting_certificate"
            tracked, draft = candidate_link, "supporting_certificate"
        elif draft_owner == "current_peer_link":
            peer_link.link_role = "supporting_certificate"
            tracked, draft = peer_link, "supporting_certificate"
        else:
            pending_link = BusinessEligibilityCertificateLink(
                business_eligibility_version_id=(
                    candidate_v if draft_owner == "pending_candidate_link" else peer_v
                ),
                certificate_id=gxp_id, link_role="source_certificate",
            )
            db.add(pending_link)
        unrelated = Company(legal_name="Unrelated pending Company")
        db.add(unrelated)
        statements, flushes = [], []

        def observe(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement.lstrip().split(None, 1)[0].upper())

        def reject_flush(*_args):
            flushes.append(True)
            raise AssertionError("DDK promotion admission cannot flush operator drafts")

        event.listen(engine, "before_cursor_execute", observe)
        event.listen(db, "before_flush", reject_flush)
        try:
            with pytest.raises(HTTPException) as exc:
                CaseWorkflowService().promote_business_eligibility_current(
                    db, business_eligibility_certificate_id=candidate_id,
                    expected_version=token, reason="Synthetic link-owner admission",
                    user=USER,
                )
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            event.remove(db, "before_flush", reject_flush)
        assert exc.value.status_code == 409
        assert "Business eligibility link has uncommitted changes" in str(exc.value.detail)
        assert set(statements) <= {"SELECT"} and not flushes
        assert unrelated in db.new
        if draft_owner.startswith("pending"):
            assert pending_link in db.new
        else:
            assert tracked in db.dirty and tracked.link_role == draft
        db.rollback()

    with Session(engine) as check:
        assert check.get(BusinessEligibilityCertificate, candidate_id).latest_flag is False
        assert check.get(BusinessEligibilityCertificate, peer_id).latest_flag is True
        assert check.get(BusinessEligibilityCertificateLink, candidate_link_id).link_role == "source_certificate"
        assert check.get(BusinessEligibilityCertificateLink, peer_link_id).link_role == "source_certificate"
        assert check.scalar(select(func.count(BusinessEligibilityCertificateLink.id))) == 2
        assert check.scalar(select(func.count(AuditEvent.id))) == 0
        assert check.scalar(select(func.count(Company.id))) == 1
