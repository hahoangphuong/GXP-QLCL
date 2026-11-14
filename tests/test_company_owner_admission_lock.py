"""Admission serialization for new physical lines and initial Cases.

Locks must protect both the Site identity and its owning Company from a
concurrent inactive-state transition; tests inspect the actual SQLAlchemy
statement because SQLite intentionally does not execute FOR UPDATE.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import AuditEvent, Case, Company, ProductionLine, Site
from backend.app.services.workflow import CaseWorkflowService


def actor():
    return build_authenticated_user("synthetic-lock-reviewer", permissions={"case.edit"})


@pytest.fixture
def owner_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Company with mutable active state")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Physical Site")
        db.add(site)
        db.flush()
        ids = company.id, site.id
        db.commit()
    try:
        yield engine, ids
    finally:
        engine.dispose()


def do_create(db, site_id, kind):
    workflow = CaseWorkflowService()
    if kind == "physical_line":
        return workflow.create_production_line_master(
            db, site_id=site_id, production_line_id=str(uuid4()),
            code="A", effective_from=date(2026, 1, 1), effective_to=None,
            physical_identity_evidence_reference="PHYSICAL-EVIDENCE-001",
            reason="Physical identity reviewed", user=actor(),
        )
    return workflow.create_initial_inspection_case(
        db, site_id=site_id, case_id=str(uuid4()), gxp_type="GMP",
        production_line_id=None, inspection_type="Mới",
        applicable_standard="WHO-GMP", reason="New initial application", user=actor(),
    )


@pytest.mark.parametrize("kind", ["physical_line", "initial_case"])
def test_create_locks_company_owner_after_site_lock(owner_db, kind):
    engine, (_, site_id) = owner_db
    visited = []
    with Session(engine) as db:
        original_scalars = db.scalars

        def track(statement, *args, **kwargs):
            if any(entry.get("entity") is Company for entry in statement.column_descriptions):
                visited.append(statement._for_update_arg is not None)
            return original_scalars(statement, *args, **kwargs)

        with patch.object(db, "scalars", side_effect=track):
            created = do_create(db, site_id, kind)
        assert created["site_id"] == site_id
        assert visited == [True], "The Company owner must be selected FOR UPDATE"
        db.commit()


@pytest.mark.parametrize("kind", ["physical_line", "initial_case"])
def test_cached_company_does_not_override_new_inactive_state(owner_db, kind):
    engine, (company_id, site_id) = owner_db
    with Session(engine) as db:
        cached_company = db.get(Company, company_id)
        assert cached_company is not None and cached_company.is_inactive is False
        # Simulate an authoritative state change that bypasses this Session's
        # stale identity map. Admission must re-read under the owner lock.
        db.execute(
            update(Company).where(Company.id == company_id).values(is_inactive=True),
            execution_options={"synchronize_session": False},
        )
        assert cached_company.is_inactive is False
        before = tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (ProductionLine, Case, AuditEvent)
        )
        with pytest.raises(HTTPException) as error:
            do_create(db, site_id, kind)
        assert error.value.status_code == 409
        db.rollback()
        with Session(engine) as check:
            assert tuple(
                check.scalar(select(func.count()).select_from(model))
                for model in (ProductionLine, Case, AuditEvent)
            ) == before
