"""Canonical Change Request action readiness rejects stale source/link/Site identities.

Actual read-only action projection is exercised after independent writer commits.
No misleading successor action may be offered from a long-lived ORM Session.
Only synthetic isolated schema in loopback disposable PostgreSQL.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import ChangeRequestState
from backend.app.db.models.phase1 import (
    AuditEvent, BusinessEligibilityCertificate, Certificate, ChangeRequest,
    ChangeRequestAffectedArtifact, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("scenario", ["gxp_link_rebound", "business_link_rebound", "business_site_company"])
def test_change_request_readiness_rejects_cached_invalid_source_owner(scenario):
    url = make_url(DATABASE_URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.database != "gxp_qlcl_test"
        or url.host not in {"127.0.0.1", "localhost"}
        or url.port != 5432
    ):
        pytest.fail("Only loopback disposable gxp_qlcl_test may be mutated.")

    schema = "cr_readiness_owner_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = cached = writer = None
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
        kind = "gxp" if scenario == "gxp_link_rebound" else "business"
        with factory() as seed:
            company = Company(legal_name="Original Company " + schema)
            other_company = Company(legal_name="Other Company " + schema)
            seed.add_all([company, other_company])
            seed.flush()
            site = Site(company_id=company.id, site_name="Change Request Site")
            other_site = Site(company_id=company.id, site_name="Foreign Site")
            seed.add_all([site, other_site])
            seed.flush()
            request = ChangeRequest(
                site_id=site.id, state=ChangeRequestState.RECEIVED,
                scope_label="SYNTHETIC", description="Readiness owner regression",
            )
            seed.add(request)
            seed.flush()
            if kind == "gxp":
                original = Certificate(
                    site_id=site.id, certificate_type="GLP",
                    issuance_basis="administrative_no_inspection", latest_flag=False,
                )
                foreign = Certificate(
                    site_id=other_site.id, certificate_type="GLP",
                    issuance_basis="administrative_no_inspection", latest_flag=False,
                )
            else:
                original = BusinessEligibilityCertificate(
                    site_id=site.id, company_id=company.id, latest_flag=False,
                )
                foreign = BusinessEligibilityCertificate(
                    site_id=other_site.id, company_id=company.id, latest_flag=False,
                )
            seed.add_all([original, foreign])
            seed.flush()
            affected = ChangeRequestAffectedArtifact(
                change_request_id=request.id,
                certificate_id=original.id if kind == "gxp" else None,
                business_eligibility_certificate_id=original.id if kind == "business" else None,
            )
            seed.add(affected)
            seed.commit()
            ids = dict(
                request=request.id, site=site.id,
                link=affected.id, original=original.id, foreign=foreign.id,
                other_company=other_company.id, token=request.row_version,
            )

        cached = factory()
        cached_site = cached.get(Site, ids["site"])
        cached_link = cached.get(ChangeRequestAffectedArtifact, ids["link"])
        cached_request = cached.get(ChangeRequest, ids["request"])
        assert cached_site.company_id != ids["other_company"]
        assert cached_request.row_version == ids["token"]
        assert (cached_link.certificate_id if kind == "gxp" else cached_link.business_eligibility_certificate_id) == ids["original"]

        writer = factory()
        if scenario == "business_site_company":
            writer.get(Site, ids["site"]).company_id = ids["other_company"]
        else:
            link = writer.get(ChangeRequestAffectedArtifact, ids["link"])
            if kind == "gxp":
                link.certificate_id = ids["foreign"]
            else:
                link.business_eligibility_certificate_id = ids["foreign"]
        writer.commit()
        # The old Session still has the pre-commit ORM identities.
        assert cached_site.company_id != ids["other_company"]
        assert (cached_link.certificate_id if kind == "gxp" else cached_link.business_eligibility_certificate_id) == ids["original"]

        actor = build_authenticated_user(
            "synthetic-readiness-link", "manager",
            permissions=["change_request.edit", "change_request.approve", "certificate.issue"],
        )
        with pytest.raises(HTTPException) as denied:
            CaseWorkflowService().get_change_request_action_readiness(
                cached, change_request_id=ids["request"], user=actor,
            )
        assert denied.value.status_code == 409
        assert "outside the owning site" in str(denied.value.detail)
        cached.rollback()

        with factory() as verify:
            request = verify.get(ChangeRequest, ids["request"])
            assert request.row_version == ids["token"]
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
            persisted_link = verify.get(ChangeRequestAffectedArtifact, ids["link"])
            if scenario == "business_site_company":
                assert verify.get(Site, ids["site"]).company_id == ids["other_company"]
                assert persisted_link.business_eligibility_certificate_id == ids["original"]
            elif kind == "gxp":
                assert persisted_link.certificate_id == ids["foreign"]
            else:
                assert persisted_link.business_eligibility_certificate_id == ids["foreign"]
    finally:
        for session in (cached, writer):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
