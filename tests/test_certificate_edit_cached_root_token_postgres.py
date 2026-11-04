"""PostgreSQL regression: certificate edit must validate committed aggregate-root version.

A long-lived Session A caches the certificate root. Session B commits an edit
and increments its root token. A subsequently submits either the old token
(which must be HTTP 409, not a late ORM StaleDataError) or the fresh committed
token (which must succeed without a false 409).
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
    AppUser, AuditEvent, BusinessEligibilityCertificate, BusinessEligibilityVersion,
    Certificate, CertificateVersion, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("kind", ["gxp", "business_eligibility"])
@pytest.mark.parametrize("request_token", ["stale", "fresh"])
def test_edit_revalidates_cached_certificate_root_before_writes(kind, request_token):
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Only disposable gxp_qlcl_test is permitted.")
    schema = "edit_cached_root_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = stale_session = None
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
        root_class = Certificate if kind == "gxp" else BusinessEligibilityCertificate
        version_class = CertificateVersion if kind == "gxp" else BusinessEligibilityVersion
        action = ("certificate.latest_version.upsert" if kind == "gxp"
                  else "business_eligibility.latest_version.upsert")
        with factory() as seed:
            company = Company(legal_name="Synthetic root token " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic cached root token")
            seed.add(site)
            seed.flush()
            if kind == "gxp":
                root = Certificate(site_id=site.id, certificate_type="GLP", latest_flag=False)
                seed.add(root)
                seed.flush()
                version = CertificateVersion(
                    certificate_id=root.id, version_no=1,
                    certificate_number="ORIGINAL", issue_date=date(2026, 8, 1),
                    expiry_date=date(2027, 8, 1), is_latest_version=True,
                )
            else:
                root = BusinessEligibilityCertificate(
                    company_id=company.id, site_id=site.id, latest_flag=False,
                )
                seed.add(root)
                seed.flush()
                version = BusinessEligibilityVersion(
                    business_eligibility_certificate_id=root.id, version_no=1,
                    certificate_number="ORIGINAL", issued_on=date(2026, 8, 1),
                )
            seed.add(version)
            seed.add(AppUser(
                username="synthetic-root-token", display_name="Synthetic actor", is_active=True,
            ))
            seed.commit()
            root_id, original_token = root.id, root.row_version

        service = CaseWorkflowService()
        actor = build_authenticated_user("synthetic-root-token", "manager")
        def edit(session, expected_version, number):
            if kind == "gxp":
                return service.upsert_certificate_latest_version(
                    session, certificate_id=root_id, expected_version=expected_version,
                    certificate_number=number, issue_date=date(2026, 8, 1),
                    expiry_date=date(2027, 8, 1), scopes=[],
                    reason="Synthetic root concurrency test", user=actor,
                )
            return service.upsert_business_eligibility_latest_version(
                session, business_eligibility_certificate_id=root_id,
                expected_version=expected_version,
                certificate_number=number, issued_on=date(2026, 8, 1),
                expires_on=None, professional_responsible_person_name=None,
                notes=None, linked_certificates=[],
                reason="Synthetic root concurrency test", user=actor,
            )

        stale_session = factory()
        cached_root = stale_session.get(root_class, root_id)
        assert cached_root.row_version == original_token
        assert cached_root.latest_flag is False

        with factory() as concurrent:
            first = edit(concurrent, original_token, "FIRST_COMMITTED")
            concurrent.commit()
        committed_token = first["row_version"]
        assert committed_token != original_token
        assert cached_root.row_version == original_token, (
            "Precondition: Session A still holds stale root concurrency token"
        )

        if request_token == "stale":
            with pytest.raises(HTTPException) as denied:
                edit(stale_session, original_token, "MUST_NOT_COMMIT")
            assert denied.value.status_code == 409
            stale_session.rollback()
        else:
            second = edit(stale_session, committed_token, "SECOND_COMMITTED")
            stale_session.commit()
            assert second["row_version"] != committed_token

        with factory() as verify:
            persisted_root = verify.get(root_class, root_id)
            persisted_version = verify.scalars(select(version_class).where(
                (version_class.certificate_id == root_id) if kind == "gxp"
                else (version_class.business_eligibility_certificate_id == root_id)
            )).one()
            expected_number = "FIRST_COMMITTED" if request_token == "stale" else "SECOND_COMMITTED"
            assert persisted_version.certificate_number == expected_number
            expected_audits = 1 if request_token == "stale" else 2
            assert verify.scalar(select(func.count(AuditEvent.id)).where(
                AuditEvent.action == action
            )) == expected_audits
            assert persisted_root.row_version == (
                committed_token if request_token == "stale" else second["row_version"]
            )
    finally:
        if stale_session is not None:
            stale_session.rollback()
            stale_session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
