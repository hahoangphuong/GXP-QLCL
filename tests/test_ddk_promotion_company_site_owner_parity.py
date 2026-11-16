"""DDK Current promotion must never cross a changed Site/Company owner.

Readiness uses committed SQL while mutation locks Site before authorization to
mutate. The synthetic tests distinguish pending drafts from externally
committed reparenting and verify no unlawful Current/audit effects.
"""
from __future__ import annotations

from datetime import date
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import (
    AuditEvent, BusinessEligibilityCertificate, BusinessEligibilityVersion,
    Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


SERVICE = CaseWorkflowService()
USER = build_authenticated_user(
    "synthetic-ddk-promotion-owner", "manager",
    permissions={"certificate.approve", "certificate.edit"},
)


def _seed(engine):
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        first_company = Company(legal_name="DDK owner Company A")
        second_company = Company(legal_name="DDK owner Company B")
        session.add_all([first_company, second_company])
        session.flush()
        site = Site(company_id=first_company.id, site_name="Reparentable DDK Site")
        session.add(site)
        session.flush()
        ddk = BusinessEligibilityCertificate(
            site_id=site.id, company_id=first_company.id, latest_flag=False,
        )
        session.add(ddk)
        session.flush()
        session.add(BusinessEligibilityVersion(
            business_eligibility_certificate_id=ddk.id, version_no=1,
            certificate_number="SYNTHETIC-DDK-A",
            issued_on=date(2026, 10, 1),
        ))
        session.commit()
        return site.id, first_company.id, second_company.id, ddk.id, ddk.row_version


def _actions(session, ddk_id):
    return {
        row["action_key"]: row
        for row in SERVICE.get_business_eligibility_action_readiness(
            session, business_eligibility_certificate_id=ddk_id, user=USER,
        )
    }


def _promote(session, ddk_id, token):
    return SERVICE.promote_business_eligibility_current(
        session, business_eligibility_certificate_id=ddk_id,
        expected_version=token, reason="synthetic Company/Site validation", user=USER,
    )


def test_committed_reparent_blocks_old_company_ddk_readiness_and_promotion(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'ddk-promote-reparent.sqlite').as_posix()}",
        future=True,
    )
    site_id, original_company, successor_company, ddk_id, token = _seed(engine)
    try:
        with Session(engine) as writer:
            writer.get(Site, site_id).company_id = successor_company
            writer.commit()

        with Session(engine) as reader:
            candidate = reader.get(BusinessEligibilityCertificate, ddk_id)
            actions = _actions(reader, ddk_id)
            assert actions["edit_latest_version"]["available"] is True
            assert actions["promote_current"]["available"] is False
            assert actions["promote_current"]["reason_code"] == "site_company_owner_mismatch"
            assert actions["promote_current"]["expected_version"] == token
            with pytest.raises(HTTPException) as denied:
                _promote(reader, ddk_id, token)
            assert denied.value.status_code == 409
            assert "Site/Company owner mismatch" in denied.value.detail
            assert candidate.latest_flag is False
            reader.rollback()

        with Session(engine) as verify:
            assert verify.get(Site, site_id).company_id == successor_company
            assert verify.get(BusinessEligibilityCertificate, ddk_id).company_id == original_company
            assert verify.get(BusinessEligibilityCertificate, ddk_id).latest_flag is False
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        engine.dispose()


def test_pending_site_owner_draft_not_flushed_on_readiness_or_denied_promotion(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'ddk-promote-dirty-site.sqlite').as_posix()}",
        future=True,
    )
    site_id, original_company, successor_company, ddk_id, token = _seed(engine)
    try:
        with Session(engine, autoflush=True, expire_on_commit=False) as reader:
            cached_site = reader.get(Site, site_id)
            cached_site.company_id = successor_company
            assert cached_site in reader.dirty
            statements = []

            def capture(_conn, _cursor, sql, _params, _ctx, _many):
                statements.append(sql.lstrip().split(None, 1)[0].upper())

            event.listen(engine, "before_cursor_execute", capture)
            try:
                # Advisory GET must consult persisted A, not the dirty B draft.
                actions = _actions(reader, ddk_id)
                assert actions["promote_current"]["available"] is True
                assert actions["promote_current"]["reason_code"] is None
                with pytest.raises(HTTPException) as denied:
                    _promote(reader, ddk_id, token)
            finally:
                event.remove(engine, "before_cursor_execute", capture)
            assert denied.value.status_code == 409
            assert "Site/Company owner mismatch" in denied.value.detail
            assert statements and set(statements) == {"SELECT"}
            assert cached_site.company_id == successor_company
            assert cached_site in reader.dirty
            assert not reader.new
            reader.rollback()

        with Session(engine) as verify:
            assert verify.get(Site, site_id).company_id == original_company
            assert verify.get(BusinessEligibilityCertificate, ddk_id).latest_flag is False
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        engine.dispose()


def test_reparented_candidate_stale_cached_session_fails_closed_postgres():
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
    schema = "ddk_promote_company_owner_" + uuid4().hex
    admin = create_engine(url, future=True)
    engine = cached_session = None
    created = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            url, connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        site_id, original_company, successor_company, ddk_id, token = _seed(engine)
        factory = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False, future=True,
        )
        cached_session = factory()
        stale_site = cached_session.get(Site, site_id)
        stale_ddk = cached_session.get(BusinessEligibilityCertificate, ddk_id)
        assert stale_site.company_id == original_company

        with factory() as writer:
            writer.get(Site, site_id).company_id = successor_company
            writer.commit()

        # READ COMMITTED scalar SELECT must not trust either cached identity.
        actions = _actions(cached_session, ddk_id)
        assert actions["promote_current"]["reason_code"] == "site_company_owner_mismatch"
        assert stale_site.company_id == original_company
        with pytest.raises(HTTPException) as denied:
            _promote(cached_session, ddk_id, token)
        assert denied.value.status_code == 409
        assert "Site/Company owner mismatch" in denied.value.detail
        assert stale_ddk.latest_flag is False
        cached_session.rollback()

        with factory() as verify:
            assert verify.get(Site, site_id).company_id == successor_company
            assert verify.get(BusinessEligibilityCertificate, ddk_id).company_id == original_company
            assert verify.get(BusinessEligibilityCertificate, ddk_id).latest_flag is False
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        if cached_session is not None:
            cached_session.rollback()
            cached_session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_unchanged_company_promotes_current_with_one_success_audit(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'ddk-promote-valid-company.sqlite').as_posix()}",
        future=True,
    )
    site_id, original_company, _, ddk_id, token = _seed(engine)
    try:
        with Session(engine) as session:
            readiness = _actions(session, ddk_id)["promote_current"]
            assert readiness["available"] is True
            assert readiness["reason_code"] is None
            assert readiness["expected_version"] == token
            result = _promote(session, ddk_id, readiness["expected_version"])
            assert result["latest_flag"] is True
            assert result["company_id"] == original_company
            session.commit()

        with Session(engine) as verify:
            assert verify.get(Site, site_id).company_id == original_company
            assert verify.get(BusinessEligibilityCertificate, ddk_id).latest_flag is True
            assert verify.scalar(select(func.count(AuditEvent.id))) == 1
    finally:
        engine.dispose()
