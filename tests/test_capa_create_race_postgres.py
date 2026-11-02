"""Disposable PostgreSQL CAPA create race: serialize round allocation on Case.

No real/rehearsal/production data; isolated synthetic schema is dropped.
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


@pytest.mark.parametrize("loser_token", [None, 1])
def test_concurrent_capa_round_creation_loser_blocks_before_insert(loser_token):
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Disposable gxp_qlcl_test database required; no mutation performed.")
    schema = "capa_round_race_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = first = second = None
    created = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Synthetic CAPA lock " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic CAPA Site")
            seed.add(site)
            seed.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            seed.add(case)
            seed.commit()
            case_id = case.id

        service = CaseWorkflowService()
        user = build_authenticated_user("synthetic-capa-actor", "manager")
        def create(session, token, value):
            return service.create_capa_cycle(
                session, case_id=case_id, expected_case_version=token,
                requested_on=None, incoming_reference=value,
                notes="isolated concurrency test", reason="synthetic concurrent create",
                user=user,
            )

        first = factory()
        winner = create(first, None, "winner")
        assert winner["round_no"] == 1

        second = factory()
        second.execute(text("SET LOCAL lock_timeout = '250ms'"))
        contender_connection = second.connection()
        contender_writes = []

        def observe(conn, cursor, statement, params, context, many):
            if conn is contender_connection and statement.lstrip().upper().startswith(
                ("INSERT", "UPDATE", "DELETE")
            ):
                contender_writes.append(statement)

        event.listen(engine, "before_cursor_execute", observe)
        try:
            with pytest.raises(OperationalError, match="lock timeout"):
                create(second, loser_token, "loser")
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            second.rollback()
        assert contender_writes == []

        first.commit()
        with pytest.raises(HTTPException) as conflict:
            create(second, loser_token, "stale")
        assert conflict.value.status_code == 409
        second.rollback()

        with factory() as verify:
            rows = list(verify.scalars(select(CapaCycle).where(CapaCycle.case_id == case_id)))
            assert len(rows) == 1
            assert rows[0].round_no == 1
            assert rows[0].incoming_reference == "winner"
            assert verify.scalar(select(func.count(AuditEvent.id))) == 1
    finally:
        for session in (second, first):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
