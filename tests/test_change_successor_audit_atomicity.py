"""Failure-injection coverage for atomic successor candidate + lineage + audit.

Uses an isolated SQLite test database; no real certificates or operator data.
Service does not commit: the request/session boundary owns rollback on errors.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import (
    AuditEvent, BusinessEligibilityCertificate, BusinessEligibilityVersion,
    Certificate, CertificateVersion, ChangeRequest, ChangeRequestAffectedArtifact,
    ChangeRequestIssuedArtifact, Company, ProductionLine, Site,
)
from backend.app.services.workflow import CaseWorkflowService


@pytest.mark.parametrize("kind", ["gmp", "business_eligibility"])
def test_successor_audit_write_failure_rolls_back_all_candidate_artifacts(
    tmp_path, monkeypatch, kind,
):
    engine = create_engine(f"sqlite:///{(tmp_path / (kind + '.sqlite')).as_posix()}", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    user = build_authenticated_user("rollback-probe", "manager")
    with Session(engine) as seed:
        company = Company(legal_name="Synthetic failure probe")
        seed.add(company)
        seed.flush()
        site = Site(company_id=company.id, site_name="Synthetic site")
        seed.add(site)
        seed.flush()
        if kind == "gmp":
            line = ProductionLine(site_id=site.id, code="A", effective_from=date(2020, 1, 1))
            seed.add(line)
            seed.flush()
            source = Certificate(
                site_id=site.id, certificate_type="GMP",
                production_line_id=line.id, line_code="A",
                issuance_basis="inspection_case", latest_flag=True,
            )
            seed.add(source)
            seed.flush()
            seed.add(CertificateVersion(
                certificate_id=source.id, version_no=1,
                certificate_number="SYNTHETIC-CURRENT", is_latest_version=True,
            ))
        else:
            source = BusinessEligibilityCertificate(
                site_id=site.id, company_id=company.id, latest_flag=True,
            )
            seed.add(source)
            seed.flush()
            seed.add(BusinessEligibilityVersion(
                business_eligibility_certificate_id=source.id,
                version_no=1, certificate_number="SYNTHETIC-DDKD",
            ))
        seed.commit()
        site_id, source_id = site.id, source.id

    with Session(engine) as setup:
        created = service.create_change_request(
            setup, site_id=site_id, scope_label="Synthetic change",
            description=None, submitted_on=None, requester_name="Synthetic",
            reason="setup", user=user,
        )
        setup.commit()
        change_id, version = created["change_request_id"], created["row_version"]

    with Session(engine) as lookup:
        statement = select(ChangeRequestAffectedArtifact.id).where(
            ChangeRequestAffectedArtifact.change_request_id == change_id,
        )
        if kind == "gmp":
            statement = statement.where(ChangeRequestAffectedArtifact.certificate_id == source_id)
        else:
            statement = statement.where(
                ChangeRequestAffectedArtifact.business_eligibility_certificate_id == source_id
            )
        source_link_id = lookup.scalars(statement).one()
        before = {
            "certificate": lookup.scalar(select(func.count(Certificate.id))),
            "dkkd": lookup.scalar(select(func.count(BusinessEligibilityCertificate.id))),
            "issued": lookup.scalar(select(func.count(ChangeRequestIssuedArtifact.id))),
            "audit": lookup.scalar(select(func.count(AuditEvent.id))),
        }

    def fail_audit(*args, **kwargs):
        raise RuntimeError("injected audit persistence failure")

    monkeypatch.setattr(service, "_write_audit_event", fail_audit)
    with Session(engine) as session:
        issue = (
            service.issue_change_request_certificate_successor
            if kind == "gmp" else
            service.issue_change_request_business_eligibility_successor
        )
        with pytest.raises(RuntimeError, match="injected audit persistence failure"):
            issue(
                session, change_request_id=change_id,
                source_affected_artifact_id=source_link_id,
                expected_version=version,
                reason="synthetic failure", user=user,
            )
        # The API request dependency must roll back on the exception.
        session.rollback()

    with Session(engine) as verify:
        after = {
            "certificate": verify.scalar(select(func.count(Certificate.id))),
            "dkkd": verify.scalar(select(func.count(BusinessEligibilityCertificate.id))),
            "issued": verify.scalar(select(func.count(ChangeRequestIssuedArtifact.id))),
            "audit": verify.scalar(select(func.count(AuditEvent.id))),
        }
        assert after == before
        assert verify.get(ChangeRequest, change_id).row_version == version
        assert verify.get(ChangeRequestAffectedArtifact, source_link_id) is not None
    engine.dispose()
