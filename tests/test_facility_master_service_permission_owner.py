"""Master mutation RBAC is owned by the service, not only HTTP routes.

Direct callers without case.edit must not probe Company/Site/ProductionLine
identity, autoflush unrelated drafts, create actors, or write business/audit.
Synthetic disposable SQLite; no rehearsal or production writes.
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import (
    AppUser, AuditEvent, Case, Certificate, Company, ProductionLine, Site,
)
from backend.app.services.workflow import CaseWorkflowService


@pytest.fixture
def db_fixture(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'master-rbac.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as seed:
        company = Company(legal_name="Synthetic owner Company")
        seed.add(company)
        seed.flush()
        site = Site(company_id=company.id, site_name="Synthetic owner Site")
        seed.add(site)
        seed.commit()
        ids = company.id, site.id
    try:
        yield engine, ids
    finally:
        engine.dispose()


def _params(operation, company_id, site_id, user):
    if operation == "create_company_master":
        return dict(
            company_id=str(uuid4()), legal_name="Denied Company",
            legal_address="Denied address", english_name=None, short_name=None,
            legal_address_en=None, reason="Synthetic", user=user,
        )
    if operation == "create_site_master":
        return dict(
            company_id=company_id, site_id=str(uuid4()),
            site_name="Denied Site", site_address="Denied address",
            site_name_en=None, site_address_en=None, province_name=None,
            short_name=None, reason="Synthetic", user=user,
        )
    if operation == "create_production_line_master":
        return dict(
            site_id=site_id, production_line_id=str(uuid4()),
            code="DENIED", effective_from=date(2026, 11, 16),
            effective_to=None, physical_identity_evidence_reference="SYNTHETIC",
            reason="Synthetic", user=user,
        )
    raise AssertionError(operation)


@pytest.mark.parametrize("operation", [
    "create_company_master", "create_site_master", "create_production_line_master",
])
@pytest.mark.parametrize("permissions", [
    set(), {"certificate.issue"}, {"inspection.edit"}, {"change_request.edit"},
])
def test_direct_master_create_denied_before_any_sql_or_flush(
    db_fixture, operation, permissions,
):
    engine, (company_id, site_id) = db_fixture
    unauthorized = build_authenticated_user(
        "unprivileged-master", "reader", permissions=permissions,
    )
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        # A non-owner business draft is pending in the same Session.
        draft = db.get(Company, company_id)
        draft.legal_name = "Operator local uncommitted draft"
        assert draft in db.dirty
        before = []
        flushes = []

        def observe(_conn, _cursor, statement, _params, _context, _many):
            before.append(statement)

        def forbidden_flush(_session, _context, _instances):
            flushes.append(True)
            raise AssertionError("Forbidden service must not autoflush")

        event.listen(engine, "before_cursor_execute", observe)
        event.listen(db, "before_flush", forbidden_flush)
        try:
            with pytest.raises(HTTPException) as denied:
                getattr(CaseWorkflowService(), operation)(
                    db, **_params(operation, company_id, site_id, unauthorized),
                )
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            event.remove(db, "before_flush", forbidden_flush)
        assert denied.value.status_code == 403
        assert denied.value.detail == "User is missing required permission."
        assert before == []
        assert flushes == []
        assert draft.legal_name == "Operator local uncommitted draft"
        assert draft in db.dirty
        assert not db.new
        db.rollback()

    with Session(engine) as verify:
        assert verify.get(Company, company_id).legal_name == "Synthetic owner Company"
        assert verify.scalar(select(func.count(Company.id))) == 1
        assert verify.scalar(select(func.count(Site.id))) == 1
        assert verify.scalar(select(func.count(ProductionLine.id))) == 0
        assert verify.scalar(select(func.count(Case.id))) == 0
        assert verify.scalar(select(func.count(Certificate.id))) == 0
        assert verify.scalar(select(func.count(AuditEvent.id))) == 0
        assert verify.scalar(select(func.count(AppUser.id))) == 0


@pytest.mark.parametrize("operation", [
    "create_company_master", "create_site_master", "create_production_line_master",
])
def test_authorized_service_owner_still_creates_once_with_canonical_identity(
    db_fixture, operation,
):
    engine, (company_id, site_id) = db_fixture
    actor = build_authenticated_user(
        "master-owner", "operator", permissions={"case.edit"},
    )
    with Session(engine) as db:
        result = getattr(CaseWorkflowService(), operation)(
            db, **_params(operation, company_id, site_id, actor),
        )
        assert result["id"]
        db.commit()
    with Session(engine) as verify:
        if operation == "create_company_master":
            assert verify.get(Company, result["id"]) is not None
        elif operation == "create_site_master":
            site = verify.get(Site, result["id"])
            assert site.company_id == company_id
        else:
            line = verify.get(ProductionLine, result["id"])
            assert line.site_id == site_id
        assert verify.scalar(select(func.count(AuditEvent.id))) == 1
        assert verify.scalar(select(func.count(AppUser.id))) == 1
