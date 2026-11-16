"""Read-only Change Request create readiness binds persisted Site identity.

Disposable SQLite regression: do not autoflush/refresh operator drafts, and
never advertise a cached Site deleted in another committed transaction.
"""
from __future__ import annotations

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import AuditEvent, Company, Site, ChangeRequest
from backend.app.services.workflow import CaseWorkflowService


def _seed(engine):
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Synthetic change request")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Synthetic registered Site")
        session.add(site)
        session.commit()
        return company.id, site.id


def _readiness(session, site_id, *, allowed=True):
    return CaseWorkflowService().get_create_change_request_action_readiness(
        session, site_id=site_id,
        user=build_authenticated_user(
            "synthetic-change-request",
            permissions={"change_request.edit"} if allowed else {"document.read"},
        ),
    )


def test_readiness_is_select_only_without_flush_or_refresh_of_operator_drafts(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'draft-site.sqlite').as_posix()}",
        future=True,
    )
    company_id, site_id = _seed(engine)
    try:
        with Session(engine, autoflush=True, expire_on_commit=False) as session:
            company = session.get(Company, company_id)
            site = session.get(Site, site_id)
            company.legal_name = "Uncommitted company draft"
            site.site_name = "Uncommitted Site draft"
            assert company in session.dirty and site in session.dirty
            statements = []

            def capture(_conn, _cursor, query, _params, _context, _many):
                statements.append(query.lstrip().split(None, 1)[0].upper())

            event.listen(engine, "before_cursor_execute", capture)
            try:
                result = _readiness(session, site_id)
            finally:
                event.remove(engine, "before_cursor_execute", capture)
            assert result["readiness_status"] == "available"
            assert result["action_key"] == "create_change_request"
            assert statements and set(statements) == {"SELECT"}
            assert company.legal_name == "Uncommitted company draft"
            assert site.site_name == "Uncommitted Site draft"
            assert company in session.dirty and site in session.dirty
            session.rollback()
        with Session(engine) as verify:
            assert verify.get(Company, company_id).legal_name == "Synthetic change request"
            assert verify.get(Site, site_id).site_name == "Synthetic registered Site"
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
            assert verify.scalar(select(func.count(ChangeRequest.id))) == 0
    finally:
        engine.dispose()


def test_deleted_site_cannot_remain_available_from_stale_orm_cache(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'deleted-site.sqlite').as_posix()}",
        future=True,
    )
    company_id, site_id = _seed(engine)
    try:
        with Session(engine, autoflush=False, expire_on_commit=False) as reader:
            cached = reader.get(Site, site_id)
            assert cached is not None and cached.company_id == company_id
            with Session(engine) as writer:
                writer.delete(writer.get(Site, site_id))
                writer.commit()
            assert _readiness(reader, site_id)["readiness_status"] == "unavailable"
            assert cached.id == site_id  # do not expire/refresh operator identity
            assert not reader.dirty and not reader.new
            reader.rollback()
        with Session(engine) as verify:
            assert verify.get(Site, site_id) is None
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
            assert verify.scalar(select(func.count(ChangeRequest.id))) == 0
    finally:
        engine.dispose()


def test_missing_site_preserves_permission_and_availability_contract(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'missing-site.sqlite').as_posix()}",
        future=True,
    )
    _seed(engine)
    try:
        with Session(engine) as session:
            assert _readiness(session, "missing-site")["readiness_status"] == "unavailable"
            denied = _readiness(session, "missing-site", allowed=False)
            assert denied["readiness_status"] == "unavailable"
            assert denied["required_permissions"] == ["change_request.edit"]
            assert not session.new and not session.dirty
    finally:
        engine.dispose()
