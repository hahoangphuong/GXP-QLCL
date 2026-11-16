"""Change Request create must admit committed Site/Company before affected snapshot.

Synthetic SQLite and disposable loopback PostgreSQL only. A Site row lock
does not refresh an already-cached ORM Site in the caller Session; neither
stale Company nor an uncommitted owner draft can select DDK snapshot.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import (
    AppUser, AuditEvent, BusinessEligibilityCertificate,
    ChangeRequest, ChangeRequestAffectedArtifact, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


USER = build_authenticated_user(
    "synthetic-change-create-owner", "manager",
    permissions={"change_request.edit"},
)


def seed(engine):
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        company_a = Company(legal_name="Synthetic Company A")
        company_b = Company(legal_name="Synthetic Company B")
        db.add_all([company_a, company_b])
        db.flush()
        site = Site(company_id=company_a.id, site_name="Synthetic Site")
        db.add(site)
        db.commit()
        return site.id, company_a.id, company_b.id


def create(session, site_id):
    return CaseWorkflowService().create_change_request(
        session, site_id=site_id, scope_label="Synthetic company change",
        description="Snapshot must use committed Site owner", submitted_on=None,
        requester_name="Synthetic", reason="Synthetic parity regression",
        user=USER,
    )


def counts(session):
    return {
        "requests": session.scalar(select(func.count(ChangeRequest.id))),
        "links": session.scalar(select(func.count(ChangeRequestAffectedArtifact.id))),
        "audit": session.scalar(select(func.count(AuditEvent.id))),
        "actor": session.scalar(select(func.count(AppUser.id))),
    }


def test_cached_site_owner_reparent_rejected_before_create_or_audit(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'cr-create-stale-site.sqlite').as_posix()}",
        future=True,
    )
    site_id, company_a, company_b = seed(engine)
    try:
        with Session(engine, autoflush=False, expire_on_commit=False) as reader:
            cached_site = reader.get(Site, site_id)
            assert cached_site.company_id == company_a
            with Session(engine) as writer:
                writer.get(Site, site_id).company_id = company_b
                writer.commit()
            assert cached_site.company_id == company_a
            with pytest.raises(HTTPException) as denied:
                create(reader, site_id)
            assert denied.value.status_code == 409
            assert "Site/Company owner changed" in denied.value.detail
            assert cached_site.company_id == company_a
            reader.rollback()
        with Session(engine) as verify:
            assert verify.get(Site, site_id).company_id == company_b
            assert counts(verify) == {
                "requests": 0, "links": 0, "audit": 0, "actor": 0,
            }
    finally:
        engine.dispose()


def test_dirty_site_company_draft_not_autoflushed_or_refreshed(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'cr-create-dirty-site.sqlite').as_posix()}",
        future=True,
    )
    site_id, company_a, company_b = seed(engine)
    try:
        with Session(engine, autoflush=True, expire_on_commit=False) as reader:
            site = reader.get(Site, site_id)
            site.company_id = company_b
            assert site in reader.dirty
            statements = []
            flushed = []

            def observe(_conn, _cursor, statement, _params, _context, _many):
                statements.append(statement.lstrip().split(None, 1)[0].upper())

            def flush(*_args):
                flushed.append(True)
                raise AssertionError("Must not flush draft before owner admission")

            event.listen(engine, "before_cursor_execute", observe)
            event.listen(reader, "before_flush", flush)
            try:
                with pytest.raises(HTTPException) as denied:
                    create(reader, site_id)
            finally:
                event.remove(engine, "before_cursor_execute", observe)
                event.remove(reader, "before_flush", flush)
            assert denied.value.status_code == 409
            assert statements and set(statements) == {"SELECT"}
            assert flushed == []
            assert site.company_id == company_b
            assert site in reader.dirty
            reader.rollback()
        with Session(engine) as verify:
            assert verify.get(Site, site_id).company_id == company_a
            assert counts(verify) == {
                "requests": 0, "links": 0, "audit": 0, "actor": 0,
            }
    finally:
        engine.dispose()


def test_valid_site_owner_creates_one_request_and_audit(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'cr-create-valid-site.sqlite').as_posix()}",
        future=True,
    )
    site_id, company_a, _ = seed(engine)
    try:
        with Session(engine) as db:
            result = create(db, site_id)
            assert result["change_request_id"]
            db.commit()
        with Session(engine) as verify:
            assert verify.get(Site, site_id).company_id == company_a
            assert counts(verify) == {
                "requests": 1, "links": 0, "audit": 1, "actor": 1,
            }
    finally:
        engine.dispose()


@pytest.mark.parametrize("reparent", [False, True])
def test_postgres_site_lock_serializes_create_with_owner_writer(reparent):
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL")
    parsed = make_url(url)
    if (
        parsed.database != "gxp_qlcl_test"
        or parsed.host not in {"localhost", "127.0.0.1"}
        or parsed.port != 5432
    ):
        pytest.fail("Only disposable loopback gxp_qlcl_test may be modified.")

    schema = "change_create_site_owner_" + uuid4().hex
    admin = create_engine(url, future=True)
    engine = writer = contender = None
    created_schema = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created_schema = True
        engine = create_engine(
            url, connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        site_id, company_a, company_b = seed(engine)
        factory = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False,
            future=True,
        )
        writer, contender = factory(), factory()
        writer_site = writer.scalar(
            select(Site).where(Site.id == site_id).with_for_update()
        )
        assert writer_site is not None
        if reparent:
            writer_site.company_id = company_b
        else:
            writer_site.site_name = "Synthetic concurrent Site edit"
        writer.flush()

        contender.execute(text("SET LOCAL lock_timeout = '250ms'"))
        writes = []
        contender_connection = contender.connection()

        def observe(conn, _cursor, statement, _params, _ctx, _many):
            if conn is contender_connection and statement.lstrip().upper().startswith(
                ("INSERT", "UPDATE", "DELETE")
            ):
                writes.append(statement)

        event.listen(engine, "before_cursor_execute", observe)
        try:
            with pytest.raises(OperationalError, match="lock timeout"):
                create(contender, site_id)
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            contender.rollback()
        assert writes == [], "No ChangeRequest/actor/audit DML before Site lock"

        writer.commit()
        # A fresh Session has no stale Site identity and can adopt the
        # committed Site context, even if another writer changed Company.
        outcome = create(contender, site_id)
        assert outcome["change_request_id"]
        contender.commit()
        with factory() as verify:
            assert verify.get(Site, site_id).company_id == (
                company_b if reparent else company_a
            )
            assert counts(verify) == {
                "requests": 1, "links": 0, "audit": 1, "actor": 1,
            }
    finally:
        for session in (contender, writer):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created_schema:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
