"""PostgreSQL regression for concurrent CAPA creation and Case transition.

The transition must lock the owning Case *before* reading the CAPA gate;
otherwise a just-created but uncommitted CAPA is invisible to the transition.
Only disposable gxp_qlcl_test schemas are allowed.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import AuditEvent, CapaCycle, Case, Company, Site
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


def test_transition_serializes_against_newly_created_uncommitted_capa():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Disposable gxp_qlcl_test required; no writes performed.")
    schema = "transition_capa_owner_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = first = second = None
    created_schema = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created_schema = True
        engine = create_engine(
            DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Synthetic transition CAPA " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic transition site")
            seed.add(site)
            seed.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            seed.add(case)
            seed.commit()
            case_id, version = case.id, case.row_version

        service = CaseWorkflowService()
        user = build_authenticated_user("synthetic-case-transition-race", "manager")
        first = factory()
        created = service.create_capa_cycle(
            first, case_id=case_id, expected_case_version=version,
            requested_on=None, incoming_reference=None,
            notes="synthetic uncommitted CAPA", reason="race probe", user=user,
        )
        assert created["status"] == "requested"
        assert first.scalar(select(func.count(CapaCycle.id))) == 1

        second = factory()
        second.execute(text("SET LOCAL lock_timeout = '250ms'"))
        contender_connection = second.connection()
        contender_dml = []

        def observe(conn, cursor, statement, params, context, many):
            if conn is contender_connection and statement.lstrip().upper().startswith(
                ("INSERT", "UPDATE", "DELETE")
            ):
                contender_dml.append(statement)

        event.listen(engine, "before_cursor_execute", observe)
        try:
            with pytest.raises(OperationalError, match="lock timeout"):
                service.transition_case(
                    second, case_id=case_id,
                    target_state=CaseState.AWAITING_CERTIFICATE_DECISION.value,
                    expected_version=version, reason="competing transition",
                    user=user,
                )
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            second.rollback()
        assert contender_dml == [], "Transition must not write audit/Case before owner-lock."

        first.commit()
        with pytest.raises(HTTPException) as conflict:
            service.transition_case(
                second, case_id=case_id,
                target_state=CaseState.AWAITING_CERTIFICATE_DECISION.value,
                expected_version=version, reason="stale snapshot must be blocked",
                user=user,
            )
        assert conflict.value.status_code == 409
        second.rollback()

        with factory() as verify:
            assert verify.get(Case, case_id).state == CaseState.INSPECTION_COMPLETED
            assert verify.scalar(select(func.count(CapaCycle.id))) == 1
            assert verify.scalar(select(func.count(AuditEvent.id))) == 1
    finally:
        for session in (second, first):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created_schema:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
