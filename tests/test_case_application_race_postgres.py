"""Disposable PostgreSQL create-vs-update ownership gate for CaseApplication."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select, text, func
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, CaseApplication, Company, Site, AuditEvent, InspectionEvent
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("loser_token", [None, 1])
def test_case_application_competing_creation_is_serialized_and_loser_fails_closed(loser_token):
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Disposable gxp_qlcl_test database required; no mutations performed.")
    schema = "case_app_race_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = None
    first = second = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            co = Company(legal_name="Case application race " + schema)
            seed.add(co)
            seed.flush()
            site = Site(company_id=co.id, site_name="Isolated case application")
            seed.add(site)
            seed.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
            seed.add(case)
            seed.commit()
            case_id = case.id

        service = CaseWorkflowService()
        user = build_authenticated_user("race-case-application", "manager")
        def write(session, token, value):
            return service.upsert_case_application(
                session, case_id=case_id, expected_version=token,
                submitted_on=None, dossier_code=value,
                dossier_reference=None, applicant_name=None,
                reason="concurrent create probe", user=user,
                fields_set={"dossier_code"},
            )

        first = factory()
        first_result = write(first, None, "winner")
        assert first_result["dossier_code"] == "winner"

        second = factory()
        second.execute(text("SET LOCAL lock_timeout = '250ms'"))
        second_connection = second.connection()
        contender_mutations = []
        def observe(conn, cursor, statement, params, context, many):
            if conn is second_connection and statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                contender_mutations.append(statement)
        event.listen(engine, "before_cursor_execute", observe)
        try:
            with pytest.raises(OperationalError, match="lock timeout"):
                write(second, loser_token, "uncommitted competitor")
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            second.rollback()
        assert contender_mutations == []

        first.commit()
        with pytest.raises(HTTPException) as error:
            write(second, loser_token, "stale competing draft")
        assert error.value.status_code == 409
        second.rollback()

        with factory() as verify:
            stages = list(verify.scalars(select(CaseApplication).where(CaseApplication.case_id == case_id)))
            assert len(stages) == 1
            assert stages[0].dossier_code == "winner"
            assert stages[0].row_version == first_result["row_version"]
            assert verify.scalar(select(func.count(AuditEvent.id))) == 1
            assert verify.scalar(select(func.count(InspectionEvent.id))) == 0
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
