"""PostgreSQL: business promotion must compare candidate against committed current issue date.

Session A caches the current record's old issue date; Session B edits that
current version and commits; A promotes a now-backdated candidate.
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
    AppUser, AuditEvent, BusinessEligibilityCertificate,
    BusinessEligibilityVersion, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


def test_business_promotion_rejects_backdate_against_updated_cached_current_version():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted.")
    schema = "business_current_version_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = contender = editor = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Synthetic business current-version " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic current-date site")
            seed.add(site)
            seed.flush()
            current = BusinessEligibilityCertificate(
                site_id=site.id, company_id=company.id, latest_flag=True,
            )
            candidate = BusinessEligibilityCertificate(
                site_id=site.id, company_id=company.id, latest_flag=False,
            )
            seed.add_all([current, candidate])
            seed.flush()
            current_version = BusinessEligibilityVersion(
                business_eligibility_certificate_id=current.id, version_no=1,
                certificate_number="CURRENT-B", issued_on=date(2026, 8, 1),
            )
            candidate_version = BusinessEligibilityVersion(
                business_eligibility_certificate_id=candidate.id, version_no=1,
                certificate_number="CANDIDATE-C", issued_on=date(2026, 9, 1),
            )
            seed.add_all([current_version, candidate_version])
            seed.add(AppUser(username="synthetic-current-date", display_name="Synthetic actor", is_active=True))
            seed.commit()
            site_id = site.id
            current_id, current_version_id, current_token = current.id, current_version.id, current.row_version
            candidate_id, candidate_token = candidate.id, candidate.row_version

        service = CaseWorkflowService()
        actor = build_authenticated_user("synthetic-current-date", "manager")
        contender = factory()
        cached_current_version = contender.get(BusinessEligibilityVersion, current_version_id)
        assert cached_current_version.issued_on == date(2026, 8, 1)

        editor = factory()
        service.upsert_business_eligibility_latest_version(
            editor, business_eligibility_certificate_id=current_id,
            expected_version=current_token,
            certificate_number="CURRENT-B", issued_on=date(2026, 10, 1),
            expires_on=None, professional_responsible_person_name=None,
            notes=None, linked_certificates=[], reason="Correct current issue date",
            user=actor,
        )
        editor.commit()
        assert cached_current_version.issued_on == date(2026, 8, 1), "Precondition: cached issue date remains stale"

        with pytest.raises(HTTPException) as denied:
            service.promote_business_eligibility_current(
                contender, business_eligibility_certificate_id=candidate_id,
                expected_version=candidate_token,
                reason="Candidate is now backdated against current",
                user=actor,
            )
        assert denied.value.status_code == 409
        assert "older than the current" in str(denied.value.detail).lower()
        contender.rollback()

        with factory() as verify:
            current_rows = list(verify.scalars(select(BusinessEligibilityCertificate).where(
                BusinessEligibilityCertificate.site_id == site_id,
                BusinessEligibilityCertificate.latest_flag.is_(True),
            )))
            assert [row.id for row in current_rows] == [current_id]
            assert verify.get(BusinessEligibilityVersion, current_version_id).issued_on == date(2026, 10, 1)
            assert verify.scalar(select(func.count(AuditEvent.id))) == 1
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
