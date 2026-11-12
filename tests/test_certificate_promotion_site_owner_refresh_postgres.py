"""Do not promote a Certificate while holding a stale Site owner lock.

Two committed Sessions and disposable loopback PostgreSQL only: if the
candidate was reparented after it was cached, neither GxP nor DDK current
promotion may proceed using the previous Site's lock.
"""
from __future__ import annotations

from datetime import date
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import (
    AuditEvent, BusinessEligibilityCertificate, BusinessEligibilityVersion,
    Certificate, CertificateVersion, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("kind", ["gxp", "ddk"])
def test_certificate_promotion_refuses_reassigned_cached_site_owner(kind):
    url = make_url(DATABASE_URL)
    if url.get_backend_name() != "postgresql" or url.host not in {"127.0.0.1", "localhost"} or url.port != 5432 or url.database != "gxp_qlcl_test":
        pytest.fail("Only loopback disposable gxp_qlcl_test is permitted; no mutations performed.")

    schema = "cert_site_owner_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = contender = editor = None
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
        with factory() as setup:
            company = Company(legal_name="Certificate Site owner " + schema)
            setup.add(company)
            setup.flush()
            site_a = Site(company_id=company.id, site_name="Old certificate Site")
            site_b = Site(company_id=company.id, site_name="New certificate Site")
            setup.add_all([site_a, site_b])
            setup.flush()
            if kind == "gxp":
                cert = Certificate(
                    site_id=site_a.id, certificate_type="GLP", latest_flag=False,
                )
            else:
                cert = BusinessEligibilityCertificate(
                    company_id=company.id, site_id=site_a.id, latest_flag=False,
                )
            setup.add(cert)
            setup.flush()
            if kind == "gxp":
                setup.add(CertificateVersion(
                    certificate_id=cert.id, version_no=1,
                    certificate_number="CI-SITE-OWNER-GLP",
                    issue_date=date(2026, 11, 12), expiry_date=date(2027, 11, 12),
                    is_latest_version=True,
                ))
            else:
                setup.add(BusinessEligibilityVersion(
                    business_eligibility_certificate_id=cert.id,
                    version_no=1, certificate_number="CI-SITE-OWNER-DDK",
                    issued_on=date(2026, 11, 12),
                ))
            setup.commit()
            cert_id, old_site, new_site = cert.id, site_a.id, site_b.id

        entity = Certificate if kind == "gxp" else BusinessEligibilityCertificate
        contender = factory()
        cached = contender.get(entity, cert_id)
        assert cached.site_id == old_site
        assert cached.latest_flag is False

        editor = factory()
        canonical = editor.get(entity, cert_id)
        canonical.site_id = new_site
        editor.commit()
        new_token = canonical.row_version

        user = build_authenticated_user("site-owner-regression", "manager")
        service = CaseWorkflowService()
        with pytest.raises(HTTPException) as denied:
            if kind == "gxp":
                service.promote_certificate_current(
                    contender, certificate_id=cert_id, expected_version=new_token,
                    reason="reject stale Site owner lock", user=user,
                )
            else:
                service.promote_business_eligibility_current(
                    contender, business_eligibility_certificate_id=cert_id,
                    expected_version=new_token,
                    reason="reject stale Site owner lock", user=user,
                )
        assert denied.value.status_code == 409
        assert "Site owner changed" in str(denied.value.detail)
        contender.rollback()

        with factory() as verify:
            persisted = verify.get(entity, cert_id)
            assert persisted.site_id == new_site
            assert persisted.latest_flag is False
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        for session in (contender, editor):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
