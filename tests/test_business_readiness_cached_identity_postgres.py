"""PostgreSQL regression: Business Eligibility readiness cannot trust a cached root/version.

Session A holds already-loaded ORM identities. Session B commits promotion
or removes the candidate number. A's next readiness call must report the
committed reason and aggregate-root concurrency token.
"""
from __future__ import annotations

from datetime import date
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import (
    AppUser, BusinessEligibilityCertificate, BusinessEligibilityVersion, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("other_writer", ["promote_current", "edit_incomplete"])
def test_business_readiness_refreshes_cached_root_and_version(other_writer):
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted.")
    schema = "business_readiness_stale_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = None
    cached_session = None
    created = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            DATABASE_URL,
            connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Synthetic business readiness " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic business readiness site")
            seed.add(site)
            seed.flush()
            cert = BusinessEligibilityCertificate(
                site_id=site.id, company_id=company.id, latest_flag=False,
            )
            seed.add(cert)
            seed.flush()
            seed.add(BusinessEligibilityVersion(
                business_eligibility_certificate_id=cert.id,
                version_no=1,
                certificate_number="SYNTHETIC-BUSINESS-READINESS",
                issued_on=date(2026, 9, 1),
            ))
            seed.add(AppUser(
                username="synthetic-business-readiness",
                display_name="Synthetic actor", is_active=True,
            ))
            seed.commit()
            certificate_id, initial_token = cert.id, cert.row_version

        service = CaseWorkflowService()
        actor = build_authenticated_user(
            "synthetic-business-readiness", "manager",
            permissions=["certificate.edit", "certificate.approve"],
        )
        cached_session = factory()
        cached = cached_session.get(BusinessEligibilityCertificate, certificate_id)
        cached_version = cached_session.scalars(select(BusinessEligibilityVersion).where(
            BusinessEligibilityVersion.business_eligibility_certificate_id == certificate_id,
        )).one()
        assert cached.latest_flag is False
        assert cached_version.certificate_number == "SYNTHETIC-BUSINESS-READINESS"
        initial = service.get_business_eligibility_action_readiness(
            cached_session, business_eligibility_certificate_id=certificate_id, user=actor,
        )
        initial_promote = next(x for x in initial if x["action_key"] == "promote_current")
        assert initial_promote["available"] is True
        assert initial_promote["expected_version"] == initial_token

        with factory() as editor:
            if other_writer == "promote_current":
                result = service.promote_business_eligibility_current(
                    editor, business_eligibility_certificate_id=certificate_id,
                    expected_version=initial_token, reason="Another session promotes current",
                    user=actor,
                )
            else:
                result = service.upsert_business_eligibility_latest_version(
                    editor, business_eligibility_certificate_id=certificate_id,
                    expected_version=initial_token, certificate_number=None,
                    issued_on=date(2026, 9, 1), expires_on=None,
                    professional_responsible_person_name=None,
                    notes=None, linked_certificates=[],
                    reason="Another session removes certificate number", user=actor,
                )
            editor.commit()
        token = result["row_version"]
        assert token != initial_token
        assert cached.latest_flag is False, "Precondition: stale root held in Session A"
        if other_writer == "edit_incomplete":
            assert cached_version.certificate_number == "SYNTHETIC-BUSINESS-READINESS"

        readiness = service.get_business_eligibility_action_readiness(
            cached_session, business_eligibility_certificate_id=certificate_id, user=actor,
        )
        promote = next(x for x in readiness if x["action_key"] == "promote_current")
        assert promote["available"] is False
        assert promote["reason_code"] == (
            "already_current" if other_writer == "promote_current"
            else "certificate_data_incomplete"
        )
        assert promote["expected_version"] == token
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
