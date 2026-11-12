"""A cached Change Request affected-link FK must not authorize successor issuance.

Two committed PostgreSQL sessions: the issuer caches a valid affected link;
the independent writer rebinds it to an artifact belonging to another Site.
The actual successor issuance must refresh the child FK after parent lock and
reject HTTP 409 without any successor, version change or audit.
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
    AppUser, AuditEvent, BusinessEligibilityCertificate, BusinessEligibilityVersion,
    Certificate, CertificateVersion, ChangeRequest, ChangeRequestAffectedArtifact,
    ChangeRequestIssuedArtifact, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("kind", ["gxp", "business_eligibility"])
def test_change_request_successor_refreshes_cached_affected_link(kind):
    url = make_url(DATABASE_URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.database != "gxp_qlcl_test"
        or url.host not in {"localhost", "127.0.0.1"}
        or url.port != 5432
    ):
        pytest.fail("Only loopback disposable gxp_qlcl_test may be mutated.")

    schema = "change_source_link_" + uuid4().hex
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
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Link rebind " + schema)
            seed.add(company)
            seed.flush()
            own_site = Site(company_id=company.id, site_name="Change Request Site")
            foreign_site = Site(company_id=company.id, site_name="Other Site")
            seed.add_all([own_site, foreign_site])
            seed.flush()
            request = ChangeRequest(
                site_id=own_site.id, state=ChangeRequestState.RECEIVED,
                scope_label="SYNTHETIC", description="Link identity test",
            )
            seed.add(request)
            seed.flush()
            if kind == "gxp":
                own_source = Certificate(
                    site_id=own_site.id, certificate_type="GLP",
                    issuance_basis="administrative_no_inspection", latest_flag=True,
                )
                foreign_source = Certificate(
                    site_id=foreign_site.id, certificate_type="GLP",
                    issuance_basis="administrative_no_inspection", latest_flag=True,
                )
                seed.add_all([own_source, foreign_source])
                seed.flush()
                seed.add(CertificateVersion(
                    certificate_id=own_source.id, version_no=1,
                    certificate_number="GLP-LINK-ORIGINAL", is_latest_version=True,
                ))
                affected = ChangeRequestAffectedArtifact(
                    change_request_id=request.id, certificate_id=own_source.id,
                )
            else:
                own_source = BusinessEligibilityCertificate(
                    site_id=own_site.id, company_id=company.id, latest_flag=True,
                )
                foreign_source = BusinessEligibilityCertificate(
                    site_id=foreign_site.id, company_id=company.id, latest_flag=True,
                )
                seed.add_all([own_source, foreign_source])
                seed.flush()
                seed.add(BusinessEligibilityVersion(
                    business_eligibility_certificate_id=own_source.id,
                    version_no=1, certificate_number="DDK-LINK-ORIGINAL",
                ))
                affected = ChangeRequestAffectedArtifact(
                    change_request_id=request.id,
                    business_eligibility_certificate_id=own_source.id,
                )
            seed.add(affected)
            seed.add(AppUser(
                username="synthetic-cr-link",
                display_name="Synthetic link actor",
                is_active=True,
            ))
            seed.commit()
            request_id, link_id, original_source_id = request.id, affected.id, own_source.id
            foreign_source_id, token = foreign_source.id, request.row_version

        cached = factory()
        old_link = cached.get(ChangeRequestAffectedArtifact, link_id)
        assert (
            old_link.certificate_id if kind == "gxp"
            else old_link.business_eligibility_certificate_id
        ) == original_source_id
        assert cached.get(ChangeRequest, request_id).row_version == token

        writer = factory()
        canonical_link = writer.get(ChangeRequestAffectedArtifact, link_id)
        if kind == "gxp":
            canonical_link.certificate_id = foreign_source_id
        else:
            canonical_link.business_eligibility_certificate_id = foreign_source_id
        writer.commit()
        assert (
            old_link.certificate_id if kind == "gxp"
            else old_link.business_eligibility_certificate_id
        ) == original_source_id, "Precondition: stale affected-link ORM identity"

        actor = build_authenticated_user(
            "synthetic-cr-link", "manager",
            permissions=("change_request.edit", "change_request.approve"),
        )
        params = dict(
            change_request_id=request_id,
            source_affected_artifact_id=link_id,
            expected_version=token,
            reason="Reject re-bound canonical source link",
            user=actor,
        )
        service = CaseWorkflowService()
        with pytest.raises(HTTPException) as denial:
            if kind == "gxp":
                service.issue_change_request_certificate_successor(cached, **params)
            else:
                service.issue_change_request_business_eligibility_successor(cached, **params)
        assert denial.value.status_code == 409
        assert "outside the owning site" in str(denial.value.detail)
        cached.rollback()

        with factory() as verify:
            assert verify.get(ChangeRequest, request_id).row_version == token
            assert verify.scalar(select(func.count(ChangeRequestIssuedArtifact.id))) == 0
            model = Certificate if kind == "gxp" else BusinessEligibilityCertificate
            assert verify.scalar(select(func.count(model.id))) == 2
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
            persisted_link = verify.get(ChangeRequestAffectedArtifact, link_id)
            assert (
                persisted_link.certificate_id if kind == "gxp"
                else persisted_link.business_eligibility_certificate_id
            ) == foreign_source_id
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
