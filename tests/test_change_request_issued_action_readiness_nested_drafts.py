"""Issued Change Request action projection must preserve nested GxP/DDK drafts.

Exercise the actual Change Request action endpoint owner rather than isolated
certificate readiness only. SQLite is disposable; no changes committed by GET.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import ChangeRequestState
from backend.app.db.models.phase1 import (
    AuditEvent, BusinessEligibilityCertificate, BusinessEligibilityVersion,
    Certificate, CertificateVersion, ChangeRequest, ChangeRequestAffectedArtifact,
    ChangeRequestIssuedArtifact, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


def test_issued_gxp_and_ddk_action_readiness_preserves_nested_operator_drafts(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'issued-gxp-ddk-drafts.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as seed:
            company = Company(legal_name="Synthetic issued action readiness")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic Site")
            seed.add(site)
            seed.flush()
            request = ChangeRequest(
                site_id=site.id, state=ChangeRequestState.RECEIVED,
                scope_label="SYNTHETIC", description="Synthetic issued action",
            )
            gxp = Certificate(
                site_id=site.id, certificate_type="GLP",
                issuance_basis="administrative_no_inspection", latest_flag=False,
            )
            ddk = BusinessEligibilityCertificate(
                site_id=site.id, company_id=company.id, latest_flag=False,
            )
            seed.add_all([request, gxp, ddk])
            seed.flush()
            gxp_version = CertificateVersion(
                certificate_id=gxp.id, version_no=1, is_latest_version=True,
                certificate_number="SYNTHETIC-GLP",
                issue_date=date(2026, 4, 1),
                expiry_date=date(2027, 4, 1),
            )
            ddk_version = BusinessEligibilityVersion(
                business_eligibility_certificate_id=ddk.id, version_no=1,
                certificate_number="SYNTHETIC-DDK", issued_on=date(2026, 4, 1),
            )
            affected_gxp = ChangeRequestAffectedArtifact(
                change_request_id=request.id, certificate_id=gxp.id,
            )
            affected_ddk = ChangeRequestAffectedArtifact(
                change_request_id=request.id, business_eligibility_certificate_id=ddk.id,
            )
            seed.add_all([gxp_version, ddk_version, affected_gxp, affected_ddk])
            seed.flush()
            issued_gxp = ChangeRequestIssuedArtifact(
                change_request_id=request.id,
                source_affected_artifact_id=affected_gxp.id,
                certificate_id=gxp.id,
            )
            issued_ddk = ChangeRequestIssuedArtifact(
                change_request_id=request.id,
                source_affected_artifact_id=affected_ddk.id,
                business_eligibility_certificate_id=ddk.id,
            )
            seed.add_all([issued_gxp, issued_ddk])
            seed.commit()
            ids = {
                "request": request.id, "gxp": gxp.id,
                "gxp_version": gxp_version.id, "ddk": ddk.id,
                "ddk_version": ddk_version.id, "issued_gxp": issued_gxp.id,
                "issued_ddk": issued_ddk.id,
            }

        actor = build_authenticated_user(
            "synthetic-issued-readiness",
            permissions={
                "change_request.edit", "change_request.approve",
                "certificate.issue", "certificate.edit", "certificate.approve",
            },
        )
        with Session(engine, autoflush=True, expire_on_commit=False) as reader:
            gxp = reader.get(Certificate, ids["gxp"])
            gxp_version = reader.get(CertificateVersion, ids["gxp_version"])
            ddk = reader.get(BusinessEligibilityCertificate, ids["ddk"])
            ddk_version = reader.get(BusinessEligibilityVersion, ids["ddk_version"])
            gxp.latest_flag = True
            gxp_version.certificate_number = None
            ddk.latest_flag = True
            ddk_version.certificate_number = None
            statements = []

            def capture(_conn, _cursor, statement, _params, _ctx, _many):
                statements.append(statement.lstrip().split(None, 1)[0].upper())

            event.listen(engine, "before_cursor_execute", capture)
            try:
                actions = {
                    item["action_key"]: item
                    for item in CaseWorkflowService().get_change_request_action_readiness(
                        reader, change_request_id=ids["request"], user=actor,
                    )
                }
            finally:
                event.remove(engine, "before_cursor_execute", capture)

            assert actions[f"promote_issued_certificate:{ids['issued_gxp']}"]["available"] is True
            assert actions[f"promote_issued_business_eligibility:{ids['issued_ddk']}"]["available"] is True
            assert actions[f"edit_issued_certificate:{ids['issued_gxp']}"]["available"] is True
            assert actions[f"edit_issued_business_eligibility:{ids['issued_ddk']}"]["available"] is True
            assert statements and set(statements) == {"SELECT"}
            assert gxp.latest_flag and ddk.latest_flag
            assert gxp_version.certificate_number is None
            assert ddk_version.certificate_number is None
            assert all(row in reader.dirty for row in (gxp, gxp_version, ddk, ddk_version))
            reader.rollback()

        with Session(engine) as verify:
            assert verify.get(Certificate, ids["gxp"]).latest_flag is False
            assert verify.get(BusinessEligibilityCertificate, ids["ddk"]).latest_flag is False
            assert verify.get(CertificateVersion, ids["gxp_version"]).certificate_number == "SYNTHETIC-GLP"
            assert verify.get(BusinessEligibilityVersion, ids["ddk_version"]).certificate_number == "SYNTHETIC-DDK"
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        engine.dispose()
