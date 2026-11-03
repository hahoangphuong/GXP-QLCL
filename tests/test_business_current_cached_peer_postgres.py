"""PostgreSQL regression: cached noncurrent peer must be demoted after promotion.

A Session cached B.latest_flag=False; another Session commits B as current.
The first Session promotes C. SQL peer lookup sees B as current but the
identity-map object may still report False, so writing False may be a no-op.
"""
from __future__ import annotations

from datetime import date
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import (
    AppUser, AuditEvent, BusinessEligibilityCertificate, BusinessEligibilityVersion,
    Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


def test_business_promotion_demotes_peer_cached_as_noncurrent_before_other_commit():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted.")
    schema = "business_peer_refresh_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = first = stale = None
    created = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Synthetic business peer refresh " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic business promotion")
            seed.add(site)
            seed.flush()
            pairs = []
            for number, issued in (("CANDIDATE-B", date(2026, 8, 1)), ("CANDIDATE-C", date(2026, 9, 1))):
                row = BusinessEligibilityCertificate(
                    site_id=site.id, company_id=company.id, latest_flag=False,
                )
                seed.add(row)
                seed.flush()
                seed.add(BusinessEligibilityVersion(
                    business_eligibility_certificate_id=row.id, version_no=1,
                    certificate_number=number, issued_on=issued,
                ))
                pairs.append((row.id, row.row_version))
            seed.add(AppUser(username="business-peer-refresh", display_name="Synthetic actor", is_active=True))
            seed.commit()
            b_id, b_token = pairs[0]
            c_id, c_token = pairs[1]

        service = CaseWorkflowService()
        actor = build_authenticated_user("business-peer-refresh", "manager")
        stale = factory()
        cached_b = stale.get(BusinessEligibilityCertificate, b_id)
        assert cached_b is not None and cached_b.latest_flag is False

        first = factory()
        service.promote_business_eligibility_current(
            first, business_eligibility_certificate_id=b_id,
            expected_version=b_token, reason="Make B current", user=actor,
        )
        first.commit()
        assert cached_b.latest_flag is False, "Precondition: cached identity stays stale"

        service.promote_business_eligibility_current(
            stale, business_eligibility_certificate_id=c_id,
            expected_version=c_token, reason="Make C current", user=actor,
        )
        stale.commit()

        with factory() as verify:
            current = list(verify.scalars(select(BusinessEligibilityCertificate).where(
                BusinessEligibilityCertificate.site_id == site.id,
                BusinessEligibilityCertificate.latest_flag.is_(True),
            )))
            assert [row.id for row in current] == [c_id], (
                "Promotion retained stale previously-current peer; "
                f"unexpected current IDs: {[row.id for row in current]}"
            )
            assert verify.scalar(select(func.count(AuditEvent.id))) == 2
    finally:
        for session in (stale, first):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
