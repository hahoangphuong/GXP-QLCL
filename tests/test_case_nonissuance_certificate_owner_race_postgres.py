"""PostgreSQL owner-lock regression: certificate issuance versus nonissuance.

Synthetic-only disposable schema. This test never writes rehearsal or
production data and never creates a legally authoritative decision.
Both competing operations must lock the same Case before business/audit DML.
"""
from __future__ import annotations

from datetime import date
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
from backend.app.db.models.phase1 import (
    AuditEvent, Case, CaseCertificateNonissuanceDecision, Certificate,
    Company, InspectionOutcome, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("first_action", ["nonissuance", "issuance"])
def test_same_case_issuance_and_nonissuance_serialize_without_duplicate_effects(first_action):
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Only disposable gxp_qlcl_test database is allowed; no writes performed.")
    schema = "nonissuance_race_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = first = second = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Synthetic nonissuance race " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic GMP site")
            seed.add(site)
            seed.flush()
            case = Case(
                site_id=site.id, gxp_type="GMP",
                state=CaseState.AWAITING_CERTIFICATE_DECISION,
            )
            seed.add(case)
            seed.flush()
            seed.add(InspectionOutcome(case_id=case.id, final_evaluation="Synthetic final assessment"))
            seed.commit()
            case_id, site_id, case_version = case.id, site.id, case.row_version

        service = CaseWorkflowService()
        user = build_authenticated_user("synthetic-nonissuance-race", "manager")

        def nonissuance(session):
            return service.record_case_nonissuance_decision(
                session, case_id=case_id, expected_case_version=case_version,
                decided_on=date(2026, 11, 15), decision_reference="SYNTHETIC-NO-ISSUE",
                explanation="Synthetic, explicit decision for concurrency regression",
                reason="synthetic lock probe", user=user,
            )

        def issuance(session):
            return service.issue_certificate(
                session, site_id=site_id, case_id=case_id,
                certificate_type="GMP", issuance_basis="inspection_case",
                certificate_number="SYNTHETIC-GMP", issue_date=date(2026, 11, 15),
                expiry_date=date(2028, 11, 15), scopes=[],
                reason="synthetic lock probe", user=user,
            )

        operations = {"nonissuance": nonissuance, "issuance": issuance}
        second_action = "issuance" if first_action == "nonissuance" else "nonissuance"

        # Deliberately pre-cache the owner in the losing Session: a stale ORM
        # identity must never bypass the Case row lock/current database state.
        second = factory()
        assert second.get(Case, case_id).state == CaseState.AWAITING_CERTIFICATE_DECISION
        second.rollback()

        first = factory()
        winning = operations[first_action](first)
        assert winning
        assert first.scalar(select(func.count(AuditEvent.id))) == 1

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
                operations[second_action](second)
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            second.rollback()
        assert contender_dml == [], "Loser must not write before acquiring the Case owner lock."

        first.commit()
        with pytest.raises(HTTPException) as conflict:
            operations[second_action](second)
        assert conflict.value.status_code == 409
        second.rollback()

        with factory() as verify:
            assert verify.scalar(select(func.count(Certificate.id))) == (first_action == "issuance")
            assert verify.scalar(select(func.count(CaseCertificateNonissuanceDecision.id))) == (
                first_action == "nonissuance"
            )
            assert verify.scalar(select(func.count(AuditEvent.id))) == 1
            assert verify.get(Case, case_id).state == CaseState.AWAITING_CERTIFICATE_DECISION
            assert not verify.new and not verify.dirty
    finally:
        for session in (second, first):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
