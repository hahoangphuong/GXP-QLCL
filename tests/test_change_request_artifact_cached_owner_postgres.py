"""Change Request successors must reject committed artifact owner reparenting.

A long-lived Session caches the GxP/eligibility certificate, then another
Session commits a Site or Company owner change. The actual successor issuance
must reject the stale identity before inserting a certificate, link or audit.
Disposable PostgreSQL schema only; never a rehearsal/production database.
"""
from __future__ import annotations

from uuid import uuid4
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import ChangeRequestState
from backend.app.db.models.phase1 import (
    AppUser,
    AuditEvent,
    BusinessEligibilityCertificate,
    BusinessEligibilityVersion,
    Certificate,
    CertificateVersion,
    ChangeRequest,
    ChangeRequestAffectedArtifact,
    ChangeRequestIssuedArtifact,
    Company,
    Site,
)
from backend.app.services.workflow import CaseWorkflowService


DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("changed_owner", [
    "gxp_site",
    "business_site",
    "business_company",
])
def test_change_request_successor_checks_committed_artifact_owner(changed_owner):
    url = make_url(DATABASE_URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.database != "gxp_qlcl_test"
        or url.host not in {"localhost", "127.0.0.1"}
        or url.port != 5432
    ):
        pytest.fail("Only loopback disposable gxp_qlcl_test may be mutated.")

    schema = "change_artifact_owner_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = cached = writer = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
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
        kind = "gxp" if changed_owner == "gxp_site" else "business"
        with factory() as seed:
            company = Company(legal_name="Original Company " + schema)
            other_company = Company(legal_name="Other Company " + schema)
            seed.add_all([company, other_company])
            seed.flush()
            site = Site(company_id=company.id, site_name="Original Site")
            other_site = Site(company_id=company.id, site_name="Other Site")
            seed.add_all([site, other_site])
            seed.flush()
            request = ChangeRequest(
                site_id=site.id, state=ChangeRequestState.RECEIVED,
                scope_label="SYNTHETIC", description="Synthetic owner fixture",
            )
            seed.add(request)
            seed.flush()
            if kind == "gxp":
                source = Certificate(
                    site_id=site.id,
                    certificate_type="GLP",
                    issuance_basis="administrative_no_inspection",
                    latest_flag=True,
                )
                seed.add(source)
                seed.flush()
                seed.add(CertificateVersion(
                    certificate_id=source.id,
                    version_no=1,
                    certificate_number="GLP-ORIGINAL",
                    is_latest_version=True,
                ))
                affected = ChangeRequestAffectedArtifact(
                    change_request_id=request.id,
                    certificate_id=source.id,
                )
            else:
                source = BusinessEligibilityCertificate(
                    site_id=site.id, company_id=company.id, latest_flag=True,
                )
                seed.add(source)
                seed.flush()
                seed.add(BusinessEligibilityVersion(
                    business_eligibility_certificate_id=source.id,
                    version_no=1, certificate_number="DDK-ORIGINAL",
                ))
                affected = ChangeRequestAffectedArtifact(
                    change_request_id=request.id,
                    business_eligibility_certificate_id=source.id,
                )
            seed.add(affected)
            seed.add(AppUser(
                username="synthetic-cr-artifact-owner",
                display_name="Synthetic owner actor",
                is_active=True,
            ))
            seed.commit()
            request_id, link_id, source_id = request.id, affected.id, source.id
            site_id, other_site_id = site.id, other_site.id
            company_id, other_company_id = company.id, other_company.id
            original_token = request.row_version

        cached = factory()
        stale_source = cached.get(
            Certificate if kind == "gxp" else BusinessEligibilityCertificate,
            source_id,
        )
        cached_request = cached.get(ChangeRequest, request_id)
        assert stale_source.site_id == site_id
        assert cached_request.row_version == original_token
        if kind == "business":
            assert stale_source.company_id == company_id

        writer = factory()
        committed_source = writer.get(
            Certificate if kind == "gxp" else BusinessEligibilityCertificate,
            source_id,
        )
        if changed_owner == "business_company":
            committed_source.company_id = other_company_id
        else:
            committed_source.site_id = other_site_id
        writer.commit()
        # Verify two committed Sessions still disagree through A's identity map.
        assert stale_source.site_id == site_id
        if kind == "business":
            assert stale_source.company_id == company_id

        actor = build_authenticated_user(
            "synthetic-cr-artifact-owner",
            "manager",
            permissions=("change_request.edit", "change_request.approve"),
        )
        arguments = dict(
            change_request_id=request_id,
            source_affected_artifact_id=link_id,
            expected_version=original_token,
            reason="Reject committed artifact owner reparent",
            user=actor,
        )
        service = CaseWorkflowService()
        with pytest.raises(HTTPException) as denial:
            if kind == "gxp":
                service.issue_change_request_certificate_successor(cached, **arguments)
            else:
                service.issue_change_request_business_eligibility_successor(cached, **arguments)
        assert denial.value.status_code == 409
        assert "outside the owning site" in str(denial.value.detail)
        cached.rollback()

        with factory() as verify:
            request = verify.get(ChangeRequest, request_id)
            assert request.row_version == original_token
            assert verify.scalar(select(func.count(ChangeRequestIssuedArtifact.id))) == 0
            model = Certificate if kind == "gxp" else BusinessEligibilityCertificate
            assert verify.scalar(select(func.count(model.id))) == 1
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
            authoritative_source = verify.get(model, source_id)
            if changed_owner == "business_company":
                assert authoritative_source.company_id == other_company_id
                assert authoritative_source.site_id == site_id
            else:
                assert authoritative_source.site_id == other_site_id
    finally:
        for session in (cached, writer):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
