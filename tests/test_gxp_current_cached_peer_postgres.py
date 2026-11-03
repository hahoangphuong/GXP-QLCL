"""PostgreSQL regression: stale cached GxP peer must be demoted.

SQL selects a DB-current certificate, but a previously loaded ORM identity may
still have latest_flag=False; assigning False must not be silently ignored.
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
    AppUser, AuditEvent, Certificate, CertificateVersion, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


def test_gxp_promotion_demotes_current_peer_cached_noncurrent_before_other_commit():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test allowed.")
    schema = "gxp_peer_refresh_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = first = stale = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Synthetic GxP cached peer " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic GxP current peer")
            seed.add(site)
            seed.flush()
            pairs = []
            for number, issued in (("GXP-CANDIDATE-B", date(2026, 8, 1)), ("GXP-CANDIDATE-C", date(2026, 9, 1))):
                cert = Certificate(
                    site_id=site.id, certificate_type="GLP", latest_flag=False,
                )
                seed.add(cert)
                seed.flush()
                seed.add(CertificateVersion(
                    certificate_id=cert.id, version_no=1, certificate_number=number,
                    issue_date=issued, expiry_date=date(2027, 9, 1), is_latest_version=True,
                ))
                pairs.append((cert.id, cert.row_version))
            seed.add(AppUser(username="synthetic-gxp-peer", display_name="Synthetic GxP actor", is_active=True))
            seed.commit()
            b_id, b_token = pairs[0]
            c_id, c_token = pairs[1]

        service = CaseWorkflowService()
        actor = build_authenticated_user("synthetic-gxp-peer", "manager")
        stale = factory()
        cached_b = stale.get(Certificate, b_id)
        assert cached_b is not None and cached_b.latest_flag is False

        first = factory()
        service.promote_certificate_current(
            first, certificate_id=b_id, expected_version=b_token,
            reason="Make B current", user=actor,
        )
        first.commit()
        assert cached_b.latest_flag is False

        service.promote_certificate_current(
            stale, certificate_id=c_id, expected_version=c_token,
            reason="Make C current", user=actor,
        )
        stale.commit()

        with factory() as verify:
            currents = list(verify.scalars(select(Certificate).where(
                Certificate.site_id == site.id,
                Certificate.certificate_type == "GLP",
                Certificate.latest_flag.is_(True),
            )))
            assert [cert.id for cert in currents] == [c_id], (
                "GxP promotion retained stale current peer: "
                f"{[cert.id for cert in currents]}"
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
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
