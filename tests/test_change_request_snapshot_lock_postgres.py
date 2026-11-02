"""Disposable PostgreSQL Site-owner gate for Change Request snapshot creation.

A concurrent certificate/business-eligibility promotion uses the same Site
lock. The Change Request must not snapshot current artifacts or write audit
records before that owner lock is acquired.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import AuditEvent, ChangeRequest, Company, Site
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


def test_change_request_snapshot_waits_for_site_owner_before_any_mutation():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Disposable gxp_qlcl_test database required; no mutation performed.")
    schema = "change_snapshot_lock_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = owner = contender = None
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
            company = Company(legal_name="Synthetic change lock " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic Change Site")
            seed.add(site)
            seed.commit()
            site_id = site.id

        service = CaseWorkflowService()
        user = build_authenticated_user("synthetic-change-editor", "manager")

        def create(session):
            return service.create_change_request(
                session, site_id=site_id, scope_label="Synthetic change",
                description="Source snapshot concurrency probe", submitted_on=None,
                requester_name="Synthetic", reason="isolated transaction test",
                user=user,
            )

        owner = factory()
        owner.execute(
            select(Site.id).where(Site.id == site_id).with_for_update()
        ).scalar_one()
        contender = factory()
        contender.execute(text("SET LOCAL lock_timeout = '250ms'"))
        contender_connection = contender.connection()
        writes = []

        def observe(conn, cursor, statement, params, context, many):
            if conn is contender_connection and statement.lstrip().upper().startswith(
                ("INSERT", "UPDATE", "DELETE")
            ):
                writes.append(statement)

        event.listen(engine, "before_cursor_execute", observe)
        try:
            with pytest.raises(OperationalError, match="lock timeout"):
                create(contender)
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            contender.rollback()
        assert writes == []

        owner.commit()
        created_row = create(contender)
        assert created_row["change_request_id"]
        contender.commit()
        with factory() as verify:
            rows = list(verify.scalars(select(ChangeRequest).where(ChangeRequest.site_id == site_id)))
            assert len(rows) == 1
            assert rows[0].id == created_row["change_request_id"]
            assert verify.scalar(select(func.count(AuditEvent.id))) == 1
    finally:
        for session in (contender, owner):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
