"""Synthetic PostgreSQL: a non-GMP Case-backed certificate cannot bypass terminal lock.

A concurrent terminal Case mutation must serialize before certificate candidate
or audit DML. No real issuance, production DB, migration or storage.
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
from backend.app.db.models.phase1 import AuditEvent, Case, Certificate, Company, Site
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


def test_non_gmp_case_backed_issuance_waits_for_terminal_case_owner():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Disposable gxp_qlcl_test required; no writes performed.")
    schema = "nongmp_case_issuance_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = first = second = None
    schema_created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        schema_created = True
        engine = create_engine(
            DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Synthetic non-GMP issuance " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic GSP site")
            seed.add(site)
            seed.flush()
            case = Case(
                site_id=site.id, gxp_type="GSP",
                state=CaseState.AWAITING_CERTIFICATE_DECISION,
            )
            seed.add(case)
            seed.commit()
            site_id, case_id = site.id, case.id

        service = CaseWorkflowService()
        user = build_authenticated_user("synthetic-gsp-issuer", "manager")

        def issue(session):
            return service.issue_certificate(
                session, site_id=site_id, case_id=case_id,
                certificate_type="GSP", issuance_basis="inspection_case",
                certificate_number=None, issue_date=None, expiry_date=None,
                scopes=[], reason="synthetic race probe", user=user,
            )

        first = factory()
        parent = first.get(Case, case_id)
        parent.state = CaseState.CLOSED
        first.flush()

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
                issue(second)
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            second.rollback()
        assert contender_dml == [], "Issuance cannot write before Case owner lock."

        first.commit()
        with pytest.raises(HTTPException) as terminal:
            issue(second)
        assert terminal.value.status_code == 409
        second.rollback()

        with factory() as verify:
            assert verify.get(Case, case_id).state == CaseState.CLOSED
            assert verify.scalar(select(func.count(Certificate.id))) == 0
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        for session in (second, first):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if schema_created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
