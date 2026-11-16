"""DDK Change Request successor must lock the owning Site before copying.

Synthetic-only SQLite and disposable loopback PostgreSQL. A Change Request
row lock cannot serialize reparenting of its independently owned Site.
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
from backend.app.db.enums import ChangeRequestState
from backend.app.db.models.phase1 import (
    AppUser, AuditEvent, BusinessEligibilityCertificate,
    BusinessEligibilityVersion, ChangeRequest,
    ChangeRequestAffectedArtifact, ChangeRequestIssuedArtifact, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


ACTOR = build_authenticated_user(
    "synthetic-ddk-successor-owner", "manager",
    permissions={"change_request.edit", "certificate.issue"},
)


def _seed(engine):
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        a = Company(legal_name="Synthetic source Company")
        b = Company(legal_name="Synthetic successor Company")
        db.add_all([a, b])
        db.flush()
        site = Site(company_id=a.id, site_name="Synthetic Site")
        db.add(site)
        db.flush()
        request = ChangeRequest(
            site_id=site.id, state=ChangeRequestState.RECEIVED,
            scope_label="Synthetic successor source",
        )
        source = BusinessEligibilityCertificate(
            site_id=site.id, company_id=a.id, latest_flag=False,
        )
        db.add_all([request, source])
        db.flush()
        version = BusinessEligibilityVersion(
            business_eligibility_certificate_id=source.id,
            version_no=1, certificate_number="SYNTHETIC-SOURCE",
        )
        affected = ChangeRequestAffectedArtifact(
            change_request_id=request.id,
            business_eligibility_certificate_id=source.id,
        )
        db.add_all([
            version, affected,
            AppUser(username="synthetic-ddk-successor-owner",
                    display_name="Synthetic actor", is_active=True),
        ])
        db.commit()
        return {
            "site": site.id,
            "source_company": a.id,
            "successor_company": b.id,
            "request": request.id,
            "source": source.id,
            "affected": affected.id,
            "token": request.row_version,
        }


def _issue(session, ids):
    return CaseWorkflowService().issue_change_request_business_eligibility_successor(
        session,
        change_request_id=ids["request"],
        source_affected_artifact_id=ids["affected"],
        expected_version=ids["token"],
        reason="Synthetic owner race", user=ACTOR,
    )


def test_cached_site_reparent_blocks_ddk_successor_without_audit(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'ddk-successor-reparent.sqlite').as_posix()}",
        future=True,
    )
    ids = _seed(engine)
    try:
        with Session(engine, autoflush=False, expire_on_commit=False) as reader:
            cached_site = reader.get(Site, ids["site"])
            cached_request = reader.get(ChangeRequest, ids["request"])
            assert cached_site.company_id == ids["source_company"]
            with Session(engine) as writer:
                writer.get(Site, ids["site"]).company_id = ids["successor_company"]
                writer.commit()

            assert cached_site.company_id == ids["source_company"]
            with pytest.raises(HTTPException) as denied:
                _issue(reader, ids)
            assert denied.value.status_code == 409
            assert "Site/Company owner changed" in denied.value.detail
            assert cached_site.company_id == ids["source_company"]
            assert cached_request.row_version == ids["token"]
            reader.rollback()

        with Session(engine) as verify:
            assert verify.get(Site, ids["site"]).company_id == ids["successor_company"]
            assert verify.scalar(select(func.count(BusinessEligibilityCertificate.id))) == 1
            assert verify.scalar(select(func.count(ChangeRequestIssuedArtifact.id))) == 0
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize("reparent", [False, True])
def test_site_lock_serializes_ddk_successor_against_independent_writer_postgres(reparent):
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL")
    parsed = make_url(url)
    if (
        parsed.database != "gxp_qlcl_test"
        or parsed.host not in {"127.0.0.1", "localhost"}
        or parsed.port != 5432
    ):
        pytest.fail("Only loopback disposable gxp_qlcl_test may be mutated.")

    schema = "ddk_successor_site_lock_" + uuid4().hex
    admin = create_engine(url, future=True)
    engine = writer = contender = None
    created = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            url, connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        ids = _seed(engine)
        factory = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False, future=True,
        )
        writer = factory()
        contender = factory()

        # A transaction in the Site owner holds its independent row lock.
        site = writer.scalar(
            select(Site).where(Site.id == ids["site"]).with_for_update()
        )
        assert site is not None
        if reparent:
            site.company_id = ids["successor_company"]
        else:
            site.site_name = "Concurrently updated registered Site"
        writer.flush()

        contender.execute(text("SET LOCAL lock_timeout = '250ms'"))
        inserts = []

        def observe(_conn, _cursor, sql, _params, _ctx, _many):
            if sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                inserts.append(sql)

        event.listen(engine, "before_cursor_execute", observe)
        try:
            with pytest.raises(OperationalError, match="lock timeout"):
                _issue(contender, ids)
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            contender.rollback()
        assert inserts == [], "No successor, actor, audit or version DML before Site lock."

        writer.commit()
        if reparent:
            with pytest.raises(HTTPException) as denied:
                _issue(contender, ids)
            assert denied.value.status_code == 409
            contender.rollback()
        else:
            result = _issue(contender, ids)
            assert result["business_eligibility_certificate_id"] != ids["source"]
            contender.commit()

        with factory() as verify:
            assert verify.get(Site, ids["site"]).company_id == (
                ids["successor_company"] if reparent else ids["source_company"]
            )
            assert verify.scalar(select(func.count(BusinessEligibilityCertificate.id))) == (
                1 if reparent else 2
            )
            assert verify.scalar(select(func.count(ChangeRequestIssuedArtifact.id))) == (
                0 if reparent else 1
            )
            assert verify.scalar(select(func.count(AuditEvent.id))) == (
                0 if reparent else 1
            )
    finally:
        for db in (contender, writer):
            if db is not None:
                db.rollback()
                db.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
