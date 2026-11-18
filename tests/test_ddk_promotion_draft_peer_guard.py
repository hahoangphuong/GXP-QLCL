"""ĐĐK current promotion preserves unsaved candidate, Site and current-peer drafts.

Synthetic isolated SQLite; no rehearsal/production access.
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
    AuditEvent, BusinessEligibilityCertificate, BusinessEligibilityVersion, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


USER = build_authenticated_user(
    "ddk-promote-draft", "manager", permissions={"certificate.approve"},
)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'ddk-promote-draft.sqlite').as_posix()}", future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Persisted Company")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Persisted Site")
        db.add(site)
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
        db.commit()
        identifiers = (site.id, peer.id, candidate.id, peer_version.id, candidate_version.id, candidate.row_version)
    try:
        yield engine, identifiers
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "dirty_owner",
    ["site", "candidate", "candidate_version", "current_peer", "current_peer_version"],
)
def test_ddk_promotion_rejects_unsaved_owner_without_any_sql_write(seeded, dirty_owner):
    engine, (site_id, peer_id, candidate_id, peer_version_id, candidate_version_id, token) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        site = db.get(Site, site_id)
        candidate = db.get(BusinessEligibilityCertificate, candidate_id)
        candidate_version = db.get(BusinessEligibilityVersion, candidate_version_id)
        peer = db.get(BusinessEligibilityCertificate, peer_id)
        peer_version = db.get(BusinessEligibilityVersion, peer_version_id)
        if dirty_owner == "site":
            site.site_name = "Unsaved Site"
            tracked, attribute, draft = site, "site_name", "Unsaved Site"
        elif dirty_owner == "candidate":
            candidate.latest_flag = True
            tracked, attribute, draft = candidate, "latest_flag", True
        elif dirty_owner == "candidate_version":
            candidate_version.notes = "Unsaved candidate notes"
            tracked, attribute, draft = candidate_version, "notes", "Unsaved candidate notes"
        elif dirty_owner == "current_peer":
            peer.latest_flag = False
            tracked, attribute, draft = peer, "latest_flag", False
        else:
            peer_version.notes = "Unsaved current notes"
            tracked, attribute, draft = peer_version, "notes", "Unsaved current notes"
        pending = Company(legal_name="Unrelated pending Company")
        db.add(pending)
        statements, flushes = [], []

        def observe(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement.lstrip().split(None, 1)[0].upper())

        def reject_flush(*_args):
            flushes.append(True)
            raise AssertionError("DDK promotion may not flush operator drafts")

        event.listen(engine, "before_cursor_execute", observe)
        event.listen(db, "before_flush", reject_flush)
        try:
            with pytest.raises(HTTPException) as exc:
                CaseWorkflowService().promote_business_eligibility_current(
                    db, business_eligibility_certificate_id=candidate_id,
                    expected_version=token, reason="Synthetic draft admission", user=USER,
                )
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            event.remove(db, "before_flush", reject_flush)
        assert exc.value.status_code == 409
        assert "uncommitted changes" in str(exc.value.detail)
        assert set(statements) <= {"SELECT"}
        assert not flushes and pending in db.new
        assert tracked in db.dirty
        assert getattr(tracked, attribute) == draft
        db.rollback()

    with Session(engine) as check:
        assert check.get(Site, site_id).site_name == "Persisted Site"
        assert check.get(BusinessEligibilityCertificate, peer_id).latest_flag is True
        assert check.get(BusinessEligibilityCertificate, candidate_id).latest_flag is False
        assert check.get(BusinessEligibilityVersion, peer_version_id).notes is None
        assert check.get(BusinessEligibilityVersion, candidate_version_id).notes is None
        assert check.scalar(select(func.count(AuditEvent.id))) == 0
        assert check.scalar(select(func.count(Company.id))) == 1
