"""Creation readiness must be a committed-data advisory read, not an ORM refresh.

Synthetic disposable SQLite only. Both initial Case and reassessment views
must preserve caller drafts while reflecting canonical persisted owner values.
"""
from __future__ import annotations

from datetime import date
from sqlalchemy import create_engine, event, func, select, update
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Company, ProductionLine, Site,
)
from backend.app.services.workflow import CaseWorkflowService


def seed(engine, *, reassessment: bool):
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Synthetic owner company")
        inactive = Company(legal_name="Synthetic inactive company", is_inactive=True)
        session.add_all([company, inactive])
        session.flush()
        site = Site(company_id=company.id, site_name="Registered Site")
        foreign_site = Site(company_id=company.id, site_name="Foreign Site")
        session.add_all([site, foreign_site])
        session.flush()
        line = ProductionLine(
            site_id=site.id, code="L1", effective_from=date(2026, 1, 1),
        )
        session.add(line)
        session.flush()
        if reassessment:
            session.add(Case(
                site_id=site.id, gxp_type="GMP",
                production_line_id=line.id, scope_code="L1",
                state=CaseState.CLOSED,
            ))
        session.commit()
        return company.id, inactive.id, site.id, foreign_site.id, line.id


def ready(session, *, site_id: str, line_id: str, reassessment: bool):
    service = CaseWorkflowService()
    kwargs = dict(
        site_id=site_id, gxp_type="GMP", line_code="L1",
        production_line_id=line_id,
        user=build_authenticated_user("synthetic-editor", permissions={"case.edit"}),
    )
    method = (
        service.get_create_reassessment_case_action_readiness
        if reassessment else service.get_create_initial_case_action_readiness
    )
    return method(session, **kwargs)


def test_creation_readiness_never_flushes_or_overwrites_pending_facility_drafts(tmp_path):
    for reassessment in (False, True):
        engine = create_engine(
            f"sqlite:///{(tmp_path / ('reassessment' if reassessment else 'initial')).as_posix()}.sqlite",
            future=True,
        )
        company_id, inactive_id, site_id, other_site_id, line_id = seed(
            engine, reassessment=reassessment,
        )
        try:
            with Session(engine, autoflush=True, expire_on_commit=False) as session:
                company = session.get(Company, company_id)
                site = session.get(Site, site_id)
                line = session.get(ProductionLine, line_id)
                company.is_inactive = True
                site.company_id = inactive_id
                line.site_id = other_site_id
                line.code = "PENDING-NOT-L1"
                statements = []

                def observe(_conn, _cursor, stmt, _params, _context, _many):
                    statements.append(stmt.lstrip().split(None, 1)[0].upper())

                event.listen(engine, "before_cursor_execute", observe)
                try:
                    view = ready(
                        session, site_id=site_id, line_id=line_id,
                        reassessment=reassessment,
                    )
                finally:
                    event.remove(engine, "before_cursor_execute", observe)
                assert view["readiness_status"] == "available"
                assert statements and set(statements) == {"SELECT"}
                assert company.is_inactive is True
                assert site.company_id == inactive_id
                assert line.site_id == other_site_id
                assert line.code == "PENDING-NOT-L1"
                assert company in session.dirty
                assert site in session.dirty
                assert line in session.dirty
                session.rollback()
            with Session(engine) as verify:
                assert verify.get(Company, company_id).is_inactive is False
                assert verify.get(Site, site_id).company_id == company_id
                assert verify.get(ProductionLine, line_id).site_id == site_id
                assert verify.scalar(select(func.count(AuditEvent.id))) == 0
        finally:
            engine.dispose()


def test_initial_readiness_uses_committed_deactivation_not_cached_company(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'stale-company.sqlite').as_posix()}", future=True)
    company_id, _inactive_id, site_id, _other_site_id, line_id = seed(engine, reassessment=False)
    try:
        with Session(engine, autoflush=False, expire_on_commit=False) as reader:
            cached = reader.get(Company, company_id)
            assert cached.is_inactive is False
            with Session(engine) as writer:
                writer.execute(
                    update(Company).where(Company.id == company_id).values(is_inactive=True)
                )
                writer.commit()
            view = ready(reader, site_id=site_id, line_id=line_id, reassessment=False)
            assert view["readiness_status"] == "unavailable"
            assert cached.is_inactive is False
            assert not reader.new and not reader.dirty
            reader.rollback()
    finally:
        engine.dispose()


def test_reassessment_readiness_uses_committed_reparent_not_cached_line(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'stale-line.sqlite').as_posix()}", future=True)
    _company, _inactive, site_id, other_site_id, line_id = seed(engine, reassessment=True)
    try:
        with Session(engine, autoflush=False, expire_on_commit=False) as reader:
            cached = reader.get(ProductionLine, line_id)
            assert cached.site_id == site_id
            with Session(engine) as writer:
                writer.execute(
                    update(ProductionLine).where(ProductionLine.id == line_id)
                    .values(site_id=other_site_id)
                )
                writer.commit()
            view = ready(reader, site_id=site_id, line_id=line_id, reassessment=True)
            assert view["readiness_status"] == "unavailable"
            assert cached.site_id == site_id
            assert not reader.new and not reader.dirty
            reader.rollback()
    finally:
        engine.dispose()
