"""DDK issue readiness is advisory and requires a persisted owning Site.

Disposable synthetic SQLite; GET cannot flush operator drafts or trust a
Site identity cached before a concurrent deletion.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import AuditEvent, BusinessEligibilityCertificate, Company, Site
from backend.app.services.workflow import CaseWorkflowService


def _seed(engine):
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        company = Company(legal_name="Synthetic DDK issue readiness")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Persisted DDK Site")
        session.add(site)
        session.commit()
        return company.id, site.id


def _readiness(session, site_id, permissions):
    return CaseWorkflowService().get_business_eligibility_issue_readiness(
        session, site_id=site_id,
        user=build_authenticated_user(
            "synthetic-ddk-issue-readiness", permissions=permissions,
        ),
    )


def test_ddk_issue_readiness_preserves_cached_site_and_company_drafts(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'ddk-issue-draft.sqlite').as_posix()}", future=True,
    )
    company_id, site_id = _seed(engine)
    try:
        with Session(engine, autoflush=True, expire_on_commit=False) as session:
            company = session.get(Company, company_id)
            site = session.get(Site, site_id)
            company.legal_name = "Uncommitted Company draft"
            site.site_name = "Uncommitted Site draft"
            commands = []

            def capture(_conn, _cursor, statement, _params, _ctx, _many):
                commands.append(statement.lstrip().split(None, 1)[0].upper())

            event.listen(engine, "before_cursor_execute", capture)
            try:
                allowed = _readiness(session, site_id, {"certificate.issue"})
                forbidden = _readiness(session, site_id, {"certificate.edit"})
            finally:
                event.remove(engine, "before_cursor_execute", capture)
            assert allowed["available"] is True
            assert allowed["reason_code"] is None
            assert forbidden["available"] is False
            assert forbidden["reason_code"] == "missing_permission"
            assert allowed["required_permissions"] == ["certificate.issue"]
            assert commands and set(commands) == {"SELECT"}
            assert company.legal_name == "Uncommitted Company draft"
            assert site.site_name == "Uncommitted Site draft"
            assert company in session.dirty and site in session.dirty
            session.rollback()

        with Session(engine) as verify:
            assert verify.get(Company, company_id).legal_name == "Synthetic DDK issue readiness"
            assert verify.get(Site, site_id).site_name == "Persisted DDK Site"
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
            assert verify.scalar(select(func.count(BusinessEligibilityCertificate.id))) == 0
    finally:
        engine.dispose()


def test_ddk_issue_readiness_rejects_deleted_site_cached_by_operator(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'ddk-issue-deleted.sqlite').as_posix()}", future=True,
    )
    _, site_id = _seed(engine)
    try:
        with Session(engine, autoflush=False, expire_on_commit=False) as reader:
            cached = reader.get(Site, site_id)
            assert cached is not None
            with Session(engine) as writer:
                writer.delete(writer.get(Site, site_id))
                writer.commit()
            with pytest.raises(HTTPException) as denied:
                _readiness(reader, site_id, {"certificate.issue"})
            assert denied.value.status_code == 404
            assert cached.id == site_id
            assert not reader.dirty and not reader.new
            reader.rollback()

        with Session(engine) as verify:
            assert verify.get(Site, site_id) is None
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        engine.dispose()
