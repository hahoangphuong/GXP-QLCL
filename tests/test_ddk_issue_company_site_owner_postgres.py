"""DDK issuance must lock committed Site/Company before inserting candidate.

The test uses synthetic disposable databases only. The Company stamped on a
new DDK is legally distinct from the Site identity; a stale Session must not
issue or audit a certificate under a former Company.
"""
from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import (
    AuditEvent, BusinessEligibilityCertificate, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


def _actor():
    return build_authenticated_user(
        "synthetic-ddk-company-issuance", "manager",
        permissions={"certificate.issue"},
    )


def _issue(session, site_id):
    return CaseWorkflowService().issue_business_eligibility(
        session, site_id=site_id,
        certificate_number="SYNTHETIC-DDK-COMPANY",
        issued_on=date(2026, 11, 16), expires_on=None,
        professional_responsible_person_name=None, notes=None,
        linked_certificates=[], reason="synthetic owner check", user=_actor(),
    )


def _seed(engine):
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        original = Company(legal_name="Original synthetic Company")
        successor = Company(legal_name="Successor synthetic Company")
        session.add_all([original, successor])
        session.flush()
        site = Site(company_id=original.id, site_name="Synthetic DDK owner Site")
        session.add(site)
        session.commit()
        return site.id, original.id, successor.id


def test_pending_site_company_draft_is_not_flushed_or_refreshed_by_ddk_issue(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'ddk-company-draft.sqlite').as_posix()}",
        future=True,
    )
    site_id, original_company_id, successor_company_id = _seed(engine)
    try:
        with Session(engine, autoflush=True, expire_on_commit=False) as reader:
            site = reader.get(Site, site_id)
            site.company_id = successor_company_id
            assert site in reader.dirty
            statements = []

            def observe(_conn, _cursor, sql, _params, _ctx, _many):
                statements.append(sql.lstrip().split(None, 1)[0].upper())

            event.listen(engine, "before_cursor_execute", observe)
            try:
                with pytest.raises(HTTPException) as denied:
                    _issue(reader, site_id)
            finally:
                event.remove(engine, "before_cursor_execute", observe)
            assert denied.value.status_code == 409
            assert "Site/Company owner changed" in denied.value.detail
            assert statements and set(statements) == {"SELECT"}
            assert site.company_id == successor_company_id
            assert site in reader.dirty
            assert not reader.new
            reader.rollback()

        with Session(engine) as verify:
            assert verify.get(Site, site_id).company_id == original_company_id
            assert verify.scalar(select(func.count(BusinessEligibilityCertificate.id))) == 0
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        engine.dispose()


def test_stale_site_reparent_by_other_writer_denied_then_fresh_issue_succeeds_postgres():
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

    schema = "ddk_issue_company_owner_" + uuid4().hex
    admin = create_engine(url, future=True)
    engine = stale = None
    created = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            url, connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        site_id, original_company_id, successor_company_id = _seed(engine)
        factory = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False, future=True,
        )

        # The issuing operator keeps the old Site identity across a commit
        # performed by an independent writer.
        stale = factory()
        cached_site = stale.get(Site, site_id)
        assert cached_site.company_id == original_company_id

        with factory() as reparent:
            reparent.get(Site, site_id).company_id = successor_company_id
            reparent.commit()
        assert cached_site.company_id == original_company_id

        with pytest.raises(HTTPException) as denied:
            _issue(stale, site_id)
        assert denied.value.status_code == 409
        assert "Site/Company owner changed" in denied.value.detail
        assert cached_site.company_id == original_company_id
        assert not stale.dirty and not stale.new
        stale.rollback()

        with factory() as check:
            assert check.get(Site, site_id).company_id == successor_company_id
            assert check.scalar(select(func.count(BusinessEligibilityCertificate.id))) == 0
            assert check.scalar(select(func.count(AuditEvent.id))) == 0

        # Fresh canonical owner admission uses the new persisted Company,
        # never the old cached Company and never a fallback guessed from name.
        with factory() as fresh:
            result = _issue(fresh, site_id)
            assert result["site_id"] == site_id
            assert result["company_id"] == successor_company_id
            fresh.commit()
        with factory() as verify:
            certificates = verify.scalars(select(BusinessEligibilityCertificate)).all()
            assert len(certificates) == 1
            assert certificates[0].site_id == site_id
            assert certificates[0].company_id == successor_company_id
            assert verify.scalar(select(func.count(AuditEvent.id))) == 1
    finally:
        if stale is not None:
            stale.rollback()
            stale.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
