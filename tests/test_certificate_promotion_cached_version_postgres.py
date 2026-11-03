"""PostgreSQL regression: promotion must not trust a cached prior version row.

The caller's Session has an old valid Version object. A separate committed
version editor clears required fields and advances the aggregate root token.
Promotion using that current token must reject the now-incomplete candidate.
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
def test_promotion_refreshes_cached_candidate_version_after_committed_edit(kind):
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted.")
    schema = "promotion_version_refresh_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = contender = editor = None
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
            company = Company(legal_name="Synthetic version refresh " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic promotion site")
            seed.add(site)
            seed.flush()
            if kind == "gxp":
                aggregate = Certificate(
                    site_id=site.id, certificate_type="GLP", latest_flag=False,
                )
                seed.add(aggregate)
                seed.flush()
                version = CertificateVersion(
                    certificate_id=aggregate.id, version_no=1,
                    certificate_number="VALID-GXP", issue_date=date(2026, 9, 1),
                    expiry_date=date(2027, 9, 1), is_latest_version=True,
                )
            else:
                aggregate = BusinessEligibilityCertificate(
                    company_id=company.id, site_id=site.id, latest_flag=False,
                )
                seed.add(aggregate)
                seed.flush()
                version = BusinessEligibilityVersion(
                    business_eligibility_certificate_id=aggregate.id,
                    version_no=1, certificate_number="VALID-DDK",
                    issued_on=date(2026, 9, 1),
                )
            seed.add(version)
            seed.add(AppUser(
                username="synthetic-version-refresh", display_name="Synthetic editor",
                is_active=True,
            ))
            seed.commit()
            agg_id, version_id, original_token = aggregate.id, version.id, aggregate.row_version

        service = CaseWorkflowService()
        actor = build_authenticated_user("synthetic-version-refresh", "manager")
        contender = factory()
        cached = contender.get(
            CertificateVersion if kind == "gxp" else BusinessEligibilityVersion,
            version_id,
        )
        assert cached.certificate_number.startswith("VALID-")

        editor = factory()
        if kind == "gxp":
            edit_result = service.upsert_certificate_latest_version(
                editor, certificate_id=agg_id, expected_version=original_token,
                certificate_number=None, issue_date=date(2026, 9, 1),
                expiry_date=date(2027, 9, 1), scopes=[],
                reason="synthetic invalidate candidate", user=actor,
            )
        else:
            edit_result = service.upsert_business_eligibility_latest_version(
                editor, business_eligibility_certificate_id=agg_id,
                expected_version=original_token, certificate_number=None,
                issued_on=date(2026, 9, 1), expires_on=None,
                professional_responsible_person_name=None, notes=None,
                linked_certificates=[],
                reason="synthetic invalidate candidate", user=actor,
            )
        editor.commit()
        assert edit_result["row_version"] != original_token

        with pytest.raises(HTTPException) as denied:
            if kind == "gxp":
                service.promote_certificate_current(
                    contender, certificate_id=agg_id,
                    expected_version=edit_result["row_version"],
                    reason="reject stale cached version", user=actor,
                )
            else:
                service.promote_business_eligibility_current(
                    contender, business_eligibility_certificate_id=agg_id,
                    expected_version=edit_result["row_version"],
                    reason="reject stale cached version", user=actor,
                )
        assert denied.value.status_code == 409
        assert "requires certificate number" in str(denied.value.detail).lower()
        contender.rollback()

        with factory() as verify:
            if kind == "gxp":
                stored = verify.get(Certificate, agg_id)
                stored_version = verify.get(CertificateVersion, version_id)
            else:
                stored = verify.get(BusinessEligibilityCertificate, agg_id)
                stored_version = verify.get(BusinessEligibilityVersion, version_id)
            assert stored.latest_flag is False
            assert stored_version.certificate_number is None
            assert verify.scalar(select(func.count(AuditEvent.id))) == 1
    finally:
        for session in (contender, editor):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
