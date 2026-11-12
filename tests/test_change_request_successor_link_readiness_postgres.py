"""DDK successor action readiness must reject committed invalid GxP link graph.

Use disposable loopback gxp_qlcl_test and a private synthetic schema only.
A long-lived Session caches valid links/targets; independent writer changes
the committed FK or GxP ownership. Readiness becomes unavailable and the
actual mutation fails closed without successor/audit. Fixing the link restores
readiness and permits exactly one real issuance.
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
    AppUser, AuditEvent, BusinessEligibilityCertificate,
    BusinessEligibilityCertificateLink, BusinessEligibilityVersion,
    Certificate, ChangeRequest, ChangeRequestAffectedArtifact,
    ChangeRequestIssuedArtifact, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("scenario", ["linked_gxp_reparented", "linked_fk_rebound"])
def test_ddk_successor_readiness_rejects_invalid_committed_gxp_link(scenario):
    url = make_url(DATABASE_URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.database != "gxp_qlcl_test"
        or url.host not in {"localhost", "127.0.0.1"}
        or url.port != 5432
    ):
        pytest.fail("Only loopback disposable gxp_qlcl_test may be mutated.")

    schema = "cr_ddk_link_readiness_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = reader = None
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
        with factory() as seed:
            company = Company(legal_name="Synthetic DDK link " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Owner Site")
            foreign_site = Site(company_id=company.id, site_name="Foreign Site")
            seed.add_all([site, foreign_site])
            seed.flush()
            request = ChangeRequest(
                site_id=site.id, state=ChangeRequestState.RECEIVED,
                scope_label="LINK", description="Synthetic DDK link",
            )
            gxp = Certificate(
                site_id=site.id, certificate_type="GLP",
                issuance_basis="administrative_no_inspection", latest_flag=True,
            )
            foreign_gxp = Certificate(
                site_id=foreign_site.id, certificate_type="GLP",
                issuance_basis="administrative_no_inspection", latest_flag=False,
            )
            seed.add_all([request, gxp, foreign_gxp])
            seed.flush()
            ddk = BusinessEligibilityCertificate(
                site_id=site.id, company_id=company.id, latest_flag=True,
            )
            seed.add(ddk)
            seed.flush()
            version = BusinessEligibilityVersion(
                business_eligibility_certificate_id=ddk.id, version_no=1,
                certificate_number="SYNTHETIC-DDK",
                professional_responsible_person_name="Synthetic person",
            )
            seed.add(version)
            seed.flush()
            source_link = BusinessEligibilityCertificateLink(
                business_eligibility_version_id=version.id,
                certificate_id=gxp.id, link_role="source_certificate",
            )
            affected = ChangeRequestAffectedArtifact(
                change_request_id=request.id,
                business_eligibility_certificate_id=ddk.id,
            )
            seed.add_all([
                source_link, affected,
                AppUser(
                    username="synthetic-ddk-link", display_name="Synthetic DDK",
                    is_active=True,
                ),
            ])
            seed.commit()
            ids = {
                "request": request.id, "token": request.row_version,
                "gxp": gxp.id, "foreign_gxp": foreign_gxp.id,
                "site": site.id, "foreign_site": foreign_site.id,
                "source_link": source_link.id, "affected": affected.id,
                "ddk": ddk.id,
            }

        reader = factory()
        # Preload the identities that can mislead a stale ORM readiness read.
        cached_gxp = reader.get(Certificate, ids["gxp"])
        cached_link = reader.get(
            BusinessEligibilityCertificateLink, ids["source_link"],
        )
        assert cached_gxp.site_id == ids["site"]
        assert cached_link.certificate_id == ids["gxp"]
        service = CaseWorkflowService()
        actor = build_authenticated_user(
            "synthetic-ddk-link", "manager",
            permissions=[
                "change_request.edit", "change_request.approve",
                "certificate.issue",
            ],
        )
        action_key = f"issue_business_eligibility_successor:{ids['affected']}"

        def readiness():
            return {
                action["action_key"]: action
                for action in service.get_change_request_action_readiness(
                    reader, change_request_id=ids["request"], user=actor,
                )
            }[action_key]

        assert readiness()["available"] is True

        with factory() as writer:
            if scenario == "linked_gxp_reparented":
                writer.get(Certificate, ids["gxp"]).site_id = ids["foreign_site"]
            else:
                writer.get(
                    BusinessEligibilityCertificateLink, ids["source_link"],
                ).certificate_id = ids["foreign_gxp"]
            writer.commit()

        assert cached_gxp.site_id == ids["site"]
        assert cached_link.certificate_id == ids["gxp"]
        unavailable = readiness()
        assert unavailable["available"] is False
        assert unavailable["reason_code"] == "invalid_source_links"
        assert unavailable["expected_version"] == ids["token"]
        params = dict(
            change_request_id=ids["request"],
            source_affected_artifact_id=ids["affected"],
            expected_version=ids["token"],
            reason="Synthetic DDK successor", user=actor,
        )
        with pytest.raises(HTTPException) as denied:
            service.issue_change_request_business_eligibility_successor(
                reader, **params,
            )
        assert denied.value.status_code == 409
        reader.rollback()

        with factory() as verify:
            assert verify.scalar(
                select(func.count(BusinessEligibilityCertificate.id))
            ) == 1
            assert verify.scalar(
                select(func.count(ChangeRequestIssuedArtifact.id))
            ) == 0
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
            assert verify.get(ChangeRequest, ids["request"]).row_version == ids["token"]

        with factory() as writer:
            if scenario == "linked_gxp_reparented":
                writer.get(Certificate, ids["gxp"]).site_id = ids["site"]
            else:
                writer.get(
                    BusinessEligibilityCertificateLink, ids["source_link"],
                ).certificate_id = ids["gxp"]
            writer.commit()

        recovered = readiness()
        assert recovered["available"] is True
        assert recovered["reason_code"] is None
        assert recovered["expected_version"] == ids["token"]
        issued = service.issue_change_request_business_eligibility_successor(
            reader, **params,
        )
        reader.commit()

        with factory() as verify:
            assert verify.get(ChangeRequest, ids["request"]).row_version == issued["row_version"]
            assert issued["row_version"] != ids["token"]
            assert verify.scalar(
                select(func.count(BusinessEligibilityCertificate.id))
            ) == 2
            assert verify.scalar(
                select(func.count(ChangeRequestIssuedArtifact.id))
            ) == 1
            assert verify.scalar(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.action == "change_request.business_eligibility_successor.issue"
                )
            ) == 1
            successor_links = list(verify.scalars(
                select(BusinessEligibilityCertificateLink)
                .join(
                    BusinessEligibilityVersion,
                    BusinessEligibilityCertificateLink.business_eligibility_version_id
                    == BusinessEligibilityVersion.id,
                )
                .where(
                    BusinessEligibilityVersion.business_eligibility_certificate_id
                    == issued["business_eligibility_certificate_id"]
                )
            ))
            assert len(successor_links) == 1
            assert successor_links[0].certificate_id == ids["gxp"]
            assert successor_links[0].link_role == "source_certificate"
    finally:
        if reader is not None:
            reader.rollback()
            reader.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
