"""DDK must reject a linked GxP whose Site changed after Session cache.

Two committed SQLAlchemy Sessions, isolated disposable PostgreSQL schema.
Both DDK version edit and Current promotion must revalidate the linked GxP
from canonical storage, without creating DDK audit/current writes on rejection.
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
    AuditEvent, BusinessEligibilityCertificate,
    BusinessEligibilityCertificateLink, BusinessEligibilityVersion,
    Certificate, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("operation", ["replace_links", "promote_current"])
def test_ddk_revalidates_linked_gxp_after_committed_site_move(operation):
    url = make_url(DATABASE_URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.database != "gxp_qlcl_test"
        or url.host not in {"127.0.0.1", "localhost"}
        or url.port != 5432
    ):
        pytest.fail("Only local disposable gxp_qlcl_test may be used; no mutations made.")

    schema = "ddk_link_site_refresh_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = contender = writer = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False, future=True,
        )
        with factory() as setup:
            company = Company(legal_name="Synthetic DDK linked Site " + schema)
            setup.add(company)
            setup.flush()
            site_a = Site(company_id=company.id, site_name="DDK Site A")
            site_b = Site(company_id=company.id, site_name="GxP moved Site B")
            setup.add_all([site_a, site_b])
            setup.flush()
            gxp = Certificate(
                site_id=site_a.id, certificate_type="GMP", latest_flag=False,
            )
            ddk = BusinessEligibilityCertificate(
                company_id=company.id, site_id=site_a.id, latest_flag=False,
            )
            setup.add_all([gxp, ddk])
            setup.flush()
            version = BusinessEligibilityVersion(
                business_eligibility_certificate_id=ddk.id,
                version_no=1, certificate_number="CI-DDK-LINK",
                issued_on=date(2026, 11, 12),
            )
            setup.add(version)
            setup.flush()
            if operation == "promote_current":
                setup.add(BusinessEligibilityCertificateLink(
                    business_eligibility_version_id=version.id,
                    certificate_id=gxp.id, link_role="source_certificate",
                ))
            setup.commit()
            gxp_id, ddk_id, version_id = gxp.id, ddk.id, version.id
            original_token = ddk.row_version
            site_a_id, site_b_id = site_a.id, site_b.id

        contender = factory()
        previously_linked = contender.get(Certificate, gxp_id)
        assert previously_linked.site_id == site_a_id
        cached_ddk = contender.get(BusinessEligibilityCertificate, ddk_id)
        assert cached_ddk.site_id == site_a_id

        writer = factory()
        changed = writer.get(Certificate, gxp_id)
        changed.site_id = site_b_id
        writer.commit()

        actor = build_authenticated_user("ci-ddk-link-site", "manager")
        service = CaseWorkflowService()
        with pytest.raises(HTTPException) as denied:
            if operation == "replace_links":
                service.upsert_business_eligibility_latest_version(
                    contender,
                    business_eligibility_certificate_id=ddk_id,
                    expected_version=original_token,
                    certificate_number="CI-DDK-LINK-EDIT",
                    issued_on=date(2026, 11, 12),
                    expires_on=None,
                    professional_responsible_person_name=None,
                    notes="synthetic edit should roll back",
                    linked_certificates=[{
                        "certificate_id": gxp_id,
                        "link_role": "source_certificate",
                    }],
                    reason="cross-site stale link gate",
                    user=actor,
                )
            else:
                service.promote_business_eligibility_current(
                    contender,
                    business_eligibility_certificate_id=ddk_id,
                    expected_version=original_token,
                    reason="cross-site stale promotion gate",
                    user=actor,
                )
        assert denied.value.status_code == 409
        assert (
            "different site" in str(denied.value.detail).lower()
            if operation == "replace_links"
            else "invalid linked" in str(denied.value.detail).lower()
        )
        contender.rollback()

        with factory() as verify:
            assert verify.get(Certificate, gxp_id).site_id == site_b_id
            persisted_ddk = verify.get(BusinessEligibilityCertificate, ddk_id)
            assert persisted_ddk.site_id == site_a_id
            assert persisted_ddk.latest_flag is False
            assert persisted_ddk.row_version == original_token
            persisted_version = verify.get(BusinessEligibilityVersion, version_id)
            assert persisted_version.certificate_number == "CI-DDK-LINK"
            assert verify.scalar(select(func.count(BusinessEligibilityCertificateLink.id))) == (
                1 if operation == "promote_current" else 0
            )
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        for session in (contender, writer):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_ddk_promotion_rechecks_cached_link_target_after_committed_rebind():
    """A stale link FK must not validate the previously linked same-site GxP."""
    url = make_url(DATABASE_URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.database != "gxp_qlcl_test"
        or url.host not in {"127.0.0.1", "localhost"}
        or url.port != 5432
    ):
        pytest.fail("Only disposable loopback PostgreSQL; no mutations made.")
    schema = "ddk_rebound_link_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = contender = writer = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False, future=True,
        )
        with factory() as setup:
            company = Company(legal_name="DDK reassigned link " + schema)
            setup.add(company)
            setup.flush()
            site_a = Site(company_id=company.id, site_name="DDK original Site")
            site_b = Site(company_id=company.id, site_name="DDK forbidden Site")
            setup.add_all([site_a, site_b])
            setup.flush()
            same = Certificate(site_id=site_a.id, certificate_type="GMP", latest_flag=False)
            wrong = Certificate(site_id=site_b.id, certificate_type="GMP", latest_flag=False)
            ddk = BusinessEligibilityCertificate(
                company_id=company.id, site_id=site_a.id, latest_flag=False,
            )
            setup.add_all([same, wrong, ddk])
            setup.flush()
            version = BusinessEligibilityVersion(
                business_eligibility_certificate_id=ddk.id, version_no=1,
                certificate_number="CI-DDK-REBOUND-LINK",
                issued_on=date(2026, 11, 12),
            )
            setup.add(version)
            setup.flush()
            link = BusinessEligibilityCertificateLink(
                business_eligibility_version_id=version.id,
                certificate_id=same.id,
                link_role="source_certificate",
            )
            setup.add(link)
            setup.commit()
            ddk_id, link_id, same_id, wrong_id = ddk.id, link.id, same.id, wrong.id
            ddk_token = ddk.row_version

        contender = factory()
        cached_link = contender.get(BusinessEligibilityCertificateLink, link_id)
        assert cached_link.certificate_id == same_id
        assert contender.get(Certificate, same_id) is not None

        writer = factory()
        canonical_link = writer.get(BusinessEligibilityCertificateLink, link_id)
        canonical_link.certificate_id = wrong_id
        writer.commit()

        with pytest.raises(HTTPException) as denied:
            CaseWorkflowService().promote_business_eligibility_current(
                contender,
                business_eligibility_certificate_id=ddk_id,
                expected_version=ddk_token,
                reason="stale DDK link target should not promote",
                user=build_authenticated_user("ci-ddk-rebound-link", "manager"),
            )
        assert denied.value.status_code == 409
        assert "invalid linked" in str(denied.value.detail).lower()
        contender.rollback()

        with factory() as verify:
            assert verify.get(BusinessEligibilityCertificateLink, link_id).certificate_id == wrong_id
            assert verify.get(BusinessEligibilityCertificate, ddk_id).latest_flag is False
            assert verify.get(BusinessEligibilityCertificate, ddk_id).row_version == ddk_token
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        for session in (contender, writer):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
