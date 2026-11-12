"""Change Request successors copy committed source fields and child links.

Two-Session PostgreSQL regression: issuer caches source Version + Scope/Link,
an independent writer commits modifications, then actual successor issuance
must copy the latest committed values without rewriting the original source.
Only isolated synthetic schema in loopback disposable gxp_qlcl_test.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import ChangeRequestState
from backend.app.db.models.phase1 import (
    AppUser, AuditEvent, BusinessEligibilityCertificate,
    BusinessEligibilityCertificateLink, BusinessEligibilityVersion,
    Certificate, CertificateScope, CertificateVersion,
    ChangeRequest, ChangeRequestAffectedArtifact, ChangeRequestIssuedArtifact,
    Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("kind", ["gxp", "business_eligibility"])
def test_successor_copies_committed_version_and_children(kind):
    url = make_url(DATABASE_URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.database != "gxp_qlcl_test"
        or url.host not in {"localhost", "127.0.0.1"}
        or url.port != 5432
    ):
        pytest.fail("Only loopback disposable gxp_qlcl_test may be mutated.")

    schema = "cr_successor_snapshot_" + uuid4().hex
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
            company = Company(legal_name="Source snapshot " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic Site")
            seed.add(site)
            seed.flush()
            request = ChangeRequest(
                site_id=site.id,
                state=ChangeRequestState.RECEIVED,
                scope_label="SOURCE-SNAPSHOT",
            )
            seed.add(request)
            seed.flush()
            if kind == "gxp":
                source = Certificate(
                    site_id=site.id, certificate_type="GLP",
                    issuance_basis="administrative_no_inspection", latest_flag=True,
                )
                seed.add(source)
                seed.flush()
                version = CertificateVersion(
                    certificate_id=source.id, version_no=1, is_latest_version=True,
                    certificate_number="SRC-GXP", applicable_standard="OLD STANDARD",
                    issuing_authority="OLD AUTHORITY",
                )
                seed.add(version)
                seed.flush()
                child = CertificateScope(
                    certificate_version_id=version.id, scope_key="scope-A",
                    scope_text="OLD SCOPE", language_code="vi", sort_order=1,
                )
                affected = ChangeRequestAffectedArtifact(
                    change_request_id=request.id, certificate_id=source.id,
                )
                gxp_id = None
            else:
                gxp = Certificate(
                    site_id=site.id, certificate_type="GLP",
                    issuance_basis="administrative_no_inspection", latest_flag=True,
                )
                seed.add(gxp)
                seed.flush()
                gxp_id = gxp.id
                source = BusinessEligibilityCertificate(
                    site_id=site.id, company_id=company.id, latest_flag=True,
                )
                seed.add(source)
                seed.flush()
                version = BusinessEligibilityVersion(
                    business_eligibility_certificate_id=source.id, version_no=1,
                    certificate_number="SRC-DDK", professional_responsible_person_name="OLD PERSON",
                    notes="OLD NOTES",
                )
                seed.add(version)
                seed.flush()
                child = BusinessEligibilityCertificateLink(
                    business_eligibility_version_id=version.id,
                    certificate_id=gxp_id, link_role="source_certificate",
                )
                affected = ChangeRequestAffectedArtifact(
                    change_request_id=request.id,
                    business_eligibility_certificate_id=source.id,
                )
            seed.add_all([child, affected, AppUser(
                username="synthetic-snapshot", display_name="Snapshot actor",
                is_active=True,
            )])
            seed.commit()
            ids = {
                "request": request.id, "source": source.id,
                "version": version.id, "child": child.id, "affected": affected.id,
                "token": request.row_version, "gxp": gxp_id,
            }

        cached = factory()
        version_model = CertificateVersion if kind == "gxp" else BusinessEligibilityVersion
        child_model = CertificateScope if kind == "gxp" else BusinessEligibilityCertificateLink
        stale_version = cached.get(version_model, ids["version"])
        stale_child = cached.get(child_model, ids["child"])
        cached.get(ChangeRequest, ids["request"])
        cached.get(Certificate if kind == "gxp" else BusinessEligibilityCertificate, ids["source"])

        writer = factory()
        authoritative_version = writer.get(version_model, ids["version"])
        authoritative_child = writer.get(child_model, ids["child"])
        if kind == "gxp":
            authoritative_version.applicable_standard = "COMMITTED STANDARD"
            authoritative_version.issuing_authority = "COMMITTED AUTHORITY"
            authoritative_child.scope_text = "COMMITTED SCOPE"
            authoritative_child.sort_order = 7
        else:
            authoritative_version.professional_responsible_person_name = "COMMITTED PERSON"
            authoritative_version.notes = "COMMITTED NOTES"
            authoritative_child.link_role = "replacement_certificate"
        writer.commit()
        if kind == "gxp":
            assert stale_version.applicable_standard == "OLD STANDARD"
            assert stale_child.scope_text == "OLD SCOPE"
        else:
            assert stale_version.professional_responsible_person_name == "OLD PERSON"
            assert stale_child.link_role == "source_certificate"

        service = CaseWorkflowService()
        # Assert transaction-level source-root locking during the actual
        # successor mutation, after the version and child snapshot is read.
        # Without a coordinating FOR UPDATE root lock this NOWAIT competitor
        # succeeds, making the regression fail instead of silently passing.
        create_method = (
            "_create_certificate_candidate" if kind == "gxp"
            else "_create_business_eligibility_candidate"
        )
        original_create = getattr(service, create_method)
        lock_probes = []

        def create_while_competing_writer_waits(*args, **kwargs):
            with factory() as competitor:
                with pytest.raises(OperationalError):
                    competitor.execute(
                        select(
                            Certificate if kind == "gxp"
                            else BusinessEligibilityCertificate
                        )
                        .where(
                            (
                                Certificate.id if kind == "gxp"
                                else BusinessEligibilityCertificate.id
                            ) == ids["source"]
                        )
                        .with_for_update(nowait=True)
                    ).scalar_one()
                competitor.rollback()
            lock_probes.append(True)
            return original_create(*args, **kwargs)

        setattr(service, create_method, create_while_competing_writer_waits)
        actor = build_authenticated_user(
            "synthetic-snapshot", "manager",
            permissions=["change_request.edit", "change_request.approve"],
        )
        params = dict(
            change_request_id=ids["request"],
            source_affected_artifact_id=ids["affected"],
            expected_version=ids["token"],
            reason="Copy committed source snapshot", user=actor,
        )
        if kind == "gxp":
            issued = service.issue_change_request_certificate_successor(cached, **params)
            successor_id = issued["certificate_id"]
        else:
            issued = service.issue_change_request_business_eligibility_successor(cached, **params)
            successor_id = issued["business_eligibility_certificate_id"]
        cached.commit()
        assert lock_probes == [True]

        # The source-row lock is released when issuer commits.
        with factory() as competitor:
            competitor.execute(
                select(
                    Certificate if kind == "gxp"
                    else BusinessEligibilityCertificate
                )
                .where(
                    (
                        Certificate.id if kind == "gxp"
                        else BusinessEligibilityCertificate.id
                    ) == ids["source"]
                )
                .with_for_update(nowait=True)
            ).scalar_one()
            competitor.rollback()

        with factory() as verify:
            assert verify.get(ChangeRequest, ids["request"]).row_version == issued["row_version"]
            assert issued["row_version"] != ids["token"]
            assert verify.scalar(select(func.count(ChangeRequestIssuedArtifact.id))) == 1
            action = (
                "change_request.certificate_successor.issue" if kind == "gxp"
                else "change_request.business_eligibility_successor.issue"
            )
            assert verify.scalar(select(func.count(AuditEvent.id)).where(AuditEvent.action == action)) == 1
            model = Certificate if kind == "gxp" else BusinessEligibilityCertificate
            assert verify.scalar(select(func.count(model.id))) == 2
            successor_version = verify.scalar(select(version_model).where(
                (CertificateVersion.certificate_id if kind == "gxp"
                 else BusinessEligibilityVersion.business_eligibility_certificate_id) == successor_id,
            ))
            assert successor_version is not None
            # GxP successor is a new draft certificate without a number.
            # DDK intentionally copies certificate_number from its source
            # under the existing BUSINESS_ELIGIBILITY_SUCCESSOR_COPY_FIELDS contract.
            if kind == "gxp":
                assert successor_version.certificate_number is None
                assert successor_version.applicable_standard == "COMMITTED STANDARD"
                assert successor_version.issuing_authority == "COMMITTED AUTHORITY"
                successor_scope = verify.scalar(
                    select(CertificateScope).where(CertificateScope.certificate_version_id == successor_version.id)
                )
                assert successor_scope.scope_text == "COMMITTED SCOPE"
                assert successor_scope.sort_order == 7
                assert verify.get(CertificateScope, ids["child"]).scope_text == "COMMITTED SCOPE"
            else:
                assert successor_version.certificate_number == "SRC-DDK"
                assert successor_version.professional_responsible_person_name == "COMMITTED PERSON"
                assert successor_version.notes == "COMMITTED NOTES"
                successor_link = verify.scalar(
                    select(BusinessEligibilityCertificateLink).where(
                        BusinessEligibilityCertificateLink.business_eligibility_version_id == successor_version.id
                    )
                )
                assert successor_link.certificate_id == ids["gxp"]
                assert successor_link.link_role == "replacement_certificate"
                assert verify.get(BusinessEligibilityCertificateLink, ids["child"]).link_role == "replacement_certificate"
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
