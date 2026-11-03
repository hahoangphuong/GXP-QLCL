"""Disposable PostgreSQL CAPA terminal-Case race: update/submit/assess.

Regression-first: a concurrent terminal Case transition must serialize against
every child CAPA mutation before any DML/audit is generated.
"""
from __future__ import annotations

import os
from datetime import date
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


@pytest.mark.parametrize("operation", ["update", "submit", "assess"])
def test_capa_child_mutation_waits_for_terminal_case_owner(operation):
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Disposable gxp_qlcl_test required; no mutations performed.")
    schema = "capa_terminal_gate_" + uuid4().hex
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
            company = Company(legal_name="Synthetic CAPA terminal " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic CAPA site")
            seed.add(site)
            seed.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            seed.add(case)
            seed.flush()
            cycle = CapaCycle(
                case_id=case.id, round_no=1,
                status="submitted" if operation == "assess" else "requested",
            )
            seed.add(cycle)
            seed.commit()
            case_id, cycle_id, version = case.id, cycle.id, cycle.row_version

        service = CaseWorkflowService()
        user = build_authenticated_user("synthetic-capa-actor", "manager")

        def mutate(session):
            if operation == "update":
                return service.update_capa_cycle(
                    session, capa_cycle_id=cycle_id, expected_version=version,
                    requested_on=None, incoming_reference=None, notes="synthetic update",
                    reason="race probe", user=user, fields_set={"notes"},
                )
            if operation == "submit":
                return service.submit_capa_cycle(
                    session, capa_cycle_id=cycle_id, expected_version=version,
                    submitted_on=date(2026, 10, 2), notes="synthetic submission",
                    reason="race probe", user=user,
                )
            return service.assess_capa_cycle(
                session, capa_cycle_id=cycle_id, expected_version=version,
                assessed_on=date(2026, 10, 3), assessor_name="synthetic",
                result="accepted", notes="synthetic assessment",
                reason="race probe", user=user,
            )

        first = factory()
        parent = first.get(Case, case_id)
        parent.state = CaseState.CLOSED
        first.flush()

        second = factory()
        second.execute(text("SET LOCAL lock_timeout = '250ms'"))
        contender_connection = second.connection()
        dml = []

        def observe(conn, cursor, statement, params, context, many):
            if conn is contender_connection and statement.lstrip().upper().startswith(
                ("INSERT", "UPDATE", "DELETE")
            ):
                dml.append(statement)

        event.listen(engine, "before_cursor_execute", observe)
        try:
            with pytest.raises(OperationalError, match="lock timeout"):
                mutate(second)
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            second.rollback()
        assert dml == []

        first.commit()
        with pytest.raises(HTTPException) as terminal:
            mutate(second)
        assert terminal.value.status_code == 409
        second.rollback()

        with factory() as verify:
            assert verify.get(Case, case_id).state == CaseState.CLOSED
            persisted = verify.get(CapaCycle, cycle_id)
            assert persisted.row_version == version
            assert persisted.status == ("submitted" if operation == "assess" else "requested")
            assert persisted.submitted_on is None
            assert persisted.assessed_on is None
            assert persisted.notes is None
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
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
