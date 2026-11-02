"""Disposable PostgreSQL Change Approval create-vs-create owner lock."""
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
from backend.app.db.enums import ChangeRequestState
from backend.app.db.models.phase1 import AuditEvent, ChangeApproval, ChangeRequest, Company, Site
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


def test_change_approval_competing_create_blocks_before_insert():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Disposable gxp_qlcl_test database required; no mutations performed.")
    schema = "change_approval_race_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = first = second = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Synthetic approval " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic approval Site")
            seed.add(site)
            seed.flush()
            change = ChangeRequest(site_id=site.id, scope_label="Synthetic", state=ChangeRequestState.UNDER_REVIEW)
            seed.add(change)
            seed.commit()
            change_id, version = change.id, change.row_version

        service = CaseWorkflowService()
        user = build_authenticated_user("synthetic-approval", "manager")
        def write(session, name):
            return service.upsert_change_approval(
                session, change_request_id=change_id, expected_version=version,
                handled_on=None, handled_by_name=name, result_label="synthetic",
                effective_on=None, approval_reference=None, reason="race probe", user=user,
                fields_set={"handled_by_name", "result_label"},
            )

        first = factory()
        winner = write(first, "first")
        assert winner["change_approval_id"]

        second = factory()
        second.execute(text("SET LOCAL lock_timeout = '250ms'"))
        contender_connection = second.connection()
        writes = []

        def observe(conn, cursor, statement, params, context, many):
            if conn is contender_connection and statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                writes.append(statement)

        event.listen(engine, "before_cursor_execute", observe)
        try:
            with pytest.raises(OperationalError, match="lock timeout"):
                write(second, "second")
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            second.rollback()
        assert writes == []

        first.commit()
        with pytest.raises(HTTPException) as stale:
            write(second, "second")
        assert stale.value.status_code == 409
        second.rollback()

        with factory() as verify:
            approvals = list(verify.scalars(select(ChangeApproval).where(ChangeApproval.change_request_id == change_id)))
            assert len(approvals) == 1
            assert approvals[0].handled_by_name == "first"
            assert verify.scalar(select(func.count(AuditEvent.id))) == 1
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
