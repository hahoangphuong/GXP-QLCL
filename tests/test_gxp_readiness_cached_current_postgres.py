"""PostgreSQL regression: GxP readiness refreshes cached root and version.

Session A caches an eligible certificate. Session B either promotes it or edits
its latest version to be incomplete. Readiness in A must reflect the committed
state, reason and root concurrency token under READ COMMITTED.
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
    AppUser, Certificate, CertificateVersion, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("later_mutation", ["promote_current", "edit_incomplete"])
def test_readiness_refreshes_cached_root_and_version_after_other_session_mutation(later_mutation):
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted.")
    schema = "gxp_readiness_stale_" + uuid4().hex
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
        factory = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False, future=True,
        )
        with factory() as seed:
            company = Company(legal_name="Synthetic GxP readiness " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic GxP readiness site")
            seed.add(site)
            seed.flush()
            certificate = Certificate(
                site_id=site.id, certificate_type="GLP", latest_flag=False,
            )
            seed.add(certificate)
            seed.flush()
            seed.add(CertificateVersion(
                certificate_id=certificate.id, version_no=1,
                certificate_number="SYNTHETIC-GLP-READINESS",
                issue_date=date(2026, 9, 1),
                expiry_date=date(2027, 9, 1),
                is_latest_version=True,
            ))
            seed.add(AppUser(
                username="synthetic-gxp-readiness",
                display_name="Synthetic actor",
                is_active=True,
            ))
            seed.commit()
            certificate_id = certificate.id
            initial_token = certificate.row_version

        service = CaseWorkflowService()
        actor = build_authenticated_user(
            "synthetic-gxp-readiness", "manager",
            permissions=["certificate.edit", "certificate.approve"],
        )
        cached_session = factory()
        cached = cached_session.get(Certificate, certificate_id)
        cached_version = cached_session.scalars(
            select(CertificateVersion).where(CertificateVersion.certificate_id == certificate_id)
        ).one()
        assert cached.latest_flag is False
        assert cached_version.certificate_number == "SYNTHETIC-GLP-READINESS"
        initial_readiness = service.get_certificate_action_readiness(
            cached_session, certificate_id=certificate_id, user=actor,
        )
        initial_promote = next(x for x in initial_readiness if x["action_key"] == "promote_current")
        assert initial_promote["available"] is True
        assert initial_promote["expected_version"] == initial_token

        with factory() as editor:
            if later_mutation == "promote_current":
                result = service.promote_certificate_current(
                    editor, certificate_id=certificate_id,
                    expected_version=initial_token,
                    reason="Another session promotes current", user=actor,
                )
            else:
                result = service.upsert_certificate_latest_version(
                    editor, certificate_id=certificate_id,
                    expected_version=initial_token,
                    certificate_number=None,
                    issue_date=date(2026, 9, 1),
                    expiry_date=date(2027, 9, 1),
                    scopes=[],
                    reason="Another session removes candidate certificate number",
                    user=actor,
                )
            editor.commit()
        current_token = result["row_version"]
        assert current_token != initial_token
        assert cached.latest_flag is False, "Precondition: Session A still holds stale ORM root"
        if later_mutation == "edit_incomplete":
            assert cached_version.certificate_number == "SYNTHETIC-GLP-READINESS", (
                "Precondition: Session A must retain a stale child Version identity"
            )

        readiness = service.get_certificate_action_readiness(
            cached_session, certificate_id=certificate_id, user=actor,
        )
        promote = next(x for x in readiness if x["action_key"] == "promote_current")
        assert promote["available"] is False, "Stale readiness advertises an invalid promotion"
        expected_reason = "already_current" if later_mutation == "promote_current" else "certificate_data_incomplete"
        assert promote["reason_code"] == expected_reason
        assert promote["expected_version"] == current_token
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
