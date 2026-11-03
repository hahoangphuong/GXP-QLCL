"""Disposable PostgreSQL regression: cached Case must not allow approval creation after closure."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Company, InspectionApprovalSubmission, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


def test_approval_creation_rechecks_terminal_case_after_cached_identity():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Disposable gxp_qlcl_test database required; no mutation performed.")
    schema = "approval_create_terminal_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = contender = closing = None
    created_schema = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created_schema = True
        engine = create_engine(
            DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as setup:
            company = Company(legal_name="Synthetic approval " + schema)
            setup.add(company)
            setup.flush()
            site = Site(company_id=company.id, site_name="Synthetic approval site")
            setup.add(site)
            setup.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            setup.add(case)
            setup.commit()
            case_id = case.id

        contender = factory()
        cached = contender.get(Case, case_id)
        assert cached.state == CaseState.INSPECTION_COMPLETED
        closing = factory()
        terminal = closing.get(Case, case_id)
        terminal.state = CaseState.CLOSED
        closing.commit()

        with pytest.raises(HTTPException) as denied:
            CaseWorkflowService().create_approval_submission(
                contender, case_id=case_id, stage="PCT", reference="Must not persist",
                submitted_on=None, submitted_time=None, pct_submission_id=None,
                reason="cached terminal gate regression",
                user=build_authenticated_user("synthetic-approval-gate", "manager"),
            )
        assert denied.value.status_code == 409
        contender.rollback()

        with factory() as verify:
            assert verify.get(Case, case_id).state == CaseState.CLOSED
            assert verify.scalar(select(func.count(InspectionApprovalSubmission.id))) == 0
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        for session in (contender, closing):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created_schema:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
