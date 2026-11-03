"""Disposable PostgreSQL proof: terminal Case transition owns inspection writes.

Concurrent final evaluation / approval completion must not read a stale
nonterminal Case while another transaction has closed that Case.
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
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Company, InspectionApprovalSubmission, InspectionOutcome, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("kind", ["final_evaluation", "approval_completion"])
def test_inspection_mutation_waits_for_terminal_case_owner(kind):
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Disposable gxp_qlcl_test required; no mutations performed.")
    schema = "inspection_terminal_gate_" + uuid4().hex
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
            company = Company(legal_name="Synthetic inspection " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic inspection Site")
            seed.add(site)
            seed.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            seed.add(case)
            seed.flush()
            if kind == "final_evaluation":
                stage = InspectionOutcome(case_id=case.id)
            else:
                stage = InspectionApprovalSubmission(
                    case_id=case.id, stage="PCT", round_no=1,
                    submitted_on=date(2026, 10, 1),
                )
            seed.add(stage)
            seed.commit()
            case_id, stage_id, version = case.id, stage.id, stage.row_version

        service = CaseWorkflowService()
        user = build_authenticated_user("synthetic-inspection-actor", "manager")

        def mutate(session):
            if kind == "final_evaluation":
                return service.finalize_inspection_outcome(
                    session, case_id=case_id, expected_version=version,
                    final_evaluation="synthetic final", reason="race probe", user=user,
                )
            return service.complete_approval_submission(
                session, approval_submission_id=stage_id, expected_version=version,
                completed_on=date(2026, 10, 2), completed_time=None,
                reason="race probe", user=user,
            )

        first = factory()
        parent = first.get(Case, case_id)
        parent.state = CaseState.CLOSED
        first.flush()

        second = factory()
        second.execute(text("SET LOCAL lock_timeout = '250ms'"))
        contender_connection = second.connection()
        mutations = []

        def observe(conn, cursor, statement, params, context, many):
            if conn is contender_connection and statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                mutations.append(statement)

        event.listen(engine, "before_cursor_execute", observe)
        try:
            with pytest.raises(OperationalError, match="lock timeout"):
                mutate(second)
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            second.rollback()
        assert mutations == []

        first.commit()
        with pytest.raises(HTTPException) as error:
            mutate(second)
        assert error.value.status_code == 409
        second.rollback()

        with factory() as verify:
            assert verify.get(Case, case_id).state == CaseState.CLOSED
            persisted = verify.get(
                InspectionOutcome if kind == "final_evaluation" else InspectionApprovalSubmission,
                stage_id,
            )
            assert persisted.row_version == version
            assert (
                persisted.final_evaluation if kind == "final_evaluation"
                else persisted.completed_on
            ) is None
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
