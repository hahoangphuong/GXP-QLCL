"""Disposable PostgreSQL proof: concurrent certificate successor attempts roll back atomically.

No production/rehearsal data. This tests existing optimistic-version semantics;
it does not assert a server-side idempotency/operation-receipt capability.
"""
from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import (
    AuditEvent, BusinessEligibilityCertificate, BusinessEligibilityVersion,
    Certificate, CertificateVersion, ChangeRequest,
    ChangeRequestAffectedArtifact, ChangeRequestIssuedArtifact,
    Company, ProductionLine, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


def test_competing_certificate_successors_leave_one_lineage_and_audit():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Disposable gxp_qlcl_test required; no mutations performed.")
    schema = "change_successor_race_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = first = second = None
    created_schema = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created_schema = True
        engine = create_engine(
            DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Synthetic successor " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic GMP site")
            seed.add(site)
            seed.flush()
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
                certificate_number="SYNTHETIC-CURRENT",
                lifecycle_state="GRANTED", is_latest_version=True,
            ))
            seed.commit()
            site_id = site.id
            source_id = source.id

        service = CaseWorkflowService()
        user = build_authenticated_user("synthetic-successor", "manager")
        with factory() as setup:
            created = service.create_change_request(
                setup, site_id=site_id, scope_label="Synthetic adjustment",
                description=None, submitted_on=None, requester_name="Synthetic",
                reason="synthetic race setup", user=user,
            )
            setup.commit()
            change_id = created["change_request_id"]
            version = created["row_version"]
        with factory() as lookup:
            affected_id = lookup.scalars(select(ChangeRequestAffectedArtifact.id).where(
                ChangeRequestAffectedArtifact.change_request_id == change_id,
                ChangeRequestAffectedArtifact.certificate_id == source_id,
            )).one()
            before_certificates = lookup.scalar(select(func.count(Certificate.id)))
            before_audit = lookup.scalar(select(func.count(AuditEvent.id)))

        def issue(session):
            return service.issue_change_request_certificate_successor(
                session, change_request_id=change_id,
                source_affected_artifact_id=affected_id,
                expected_version=version, reason="synthetic competitor", user=user,
            )

        first = factory()
        winner = issue(first)
        assert winner["certificate_id"]

        second = factory()
        second.execute(text("SET LOCAL lock_timeout = '250ms'"))
        with pytest.raises(OperationalError, match="lock timeout"):
            issue(second)
        second.rollback()

        first.commit()
        with pytest.raises(HTTPException) as stale:
            issue(second)
        assert stale.value.status_code == 409
        second.rollback()

        with factory() as verify:
            assert verify.scalar(select(func.count(Certificate.id))) == before_certificates + 1
            assert verify.scalar(select(func.count(ChangeRequestIssuedArtifact.id))) == 1
            assert verify.scalar(select(func.count(AuditEvent.id))) == before_audit + 1
            row = verify.get(ChangeRequest, change_id)
            assert row.row_version == winner["row_version"]
            assert verify.get(Certificate, winner["certificate_id"]).latest_flag is False
            link = verify.scalars(select(ChangeRequestIssuedArtifact).where(
                ChangeRequestIssuedArtifact.change_request_id == change_id,
            )).one()
            assert link.certificate_id == winner["certificate_id"]
            assert link.source_affected_artifact_id == affected_id
            audit = verify.get(AuditEvent, winner["audit_event_id"])
            assert audit.action == "change_request.certificate_successor.issue"
    finally:
        for session in (second, first):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created_schema:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_competing_business_eligibility_successors_leave_one_lineage_and_audit():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Disposable gxp_qlcl_test required; no mutations performed.")
    schema = "dkkd_successor_race_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = first = second = None
    created_schema = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created_schema = True
        engine = create_engine(DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Synthetic DDKD successor " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic DDKD site")
            seed.add(site)
            seed.flush()
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

        service = CaseWorkflowService()
        user = build_authenticated_user("synthetic-dkkd-successor", "manager")
        with factory() as setup:
            created = service.create_change_request(
                setup, site_id=site_id, scope_label="Synthetic DDKD adjustment",
                description=None, submitted_on=None, requester_name="Synthetic",
                reason="synthetic race setup", user=user,
            )
            setup.commit()
            change_id, version = created["change_request_id"], created["row_version"]

        with factory() as lookup:
            affected_id = lookup.scalars(select(ChangeRequestAffectedArtifact.id).where(
                ChangeRequestAffectedArtifact.change_request_id == change_id,
                ChangeRequestAffectedArtifact.business_eligibility_certificate_id == source_id,
            )).one()
            before_dkkd = lookup.scalar(select(func.count(BusinessEligibilityCertificate.id)))
            before_audit = lookup.scalar(select(func.count(AuditEvent.id)))

        def issue(session):
            return service.issue_change_request_business_eligibility_successor(
                session, change_request_id=change_id,
                source_affected_artifact_id=affected_id,
                expected_version=version, reason="synthetic competitor", user=user,
            )

        first = factory()
        winner = issue(first)
        assert winner["business_eligibility_certificate_id"]

        second = factory()
        second.execute(text("SET LOCAL lock_timeout = '250ms'"))
        with pytest.raises(OperationalError, match="lock timeout"):
            issue(second)
        second.rollback()

        first.commit()
        with pytest.raises(HTTPException) as stale:
            issue(second)
        assert stale.value.status_code == 409
        second.rollback()

        with factory() as verify:
            assert verify.scalar(select(func.count(BusinessEligibilityCertificate.id))) == before_dkkd + 1
            assert verify.scalar(select(func.count(ChangeRequestIssuedArtifact.id))) == 1
            assert verify.scalar(select(func.count(AuditEvent.id))) == before_audit + 1
            row = verify.get(ChangeRequest, change_id)
            assert row.row_version == winner["row_version"]
            successor = verify.get(BusinessEligibilityCertificate, winner["business_eligibility_certificate_id"])
            assert successor.latest_flag is False
            link = verify.scalars(select(ChangeRequestIssuedArtifact).where(
                ChangeRequestIssuedArtifact.change_request_id == change_id,
            )).one()
            assert link.business_eligibility_certificate_id == successor.id
            assert link.source_affected_artifact_id == affected_id
            audit = verify.get(AuditEvent, winner["audit_event_id"])
            assert audit.action == "change_request.business_eligibility_successor.issue"
    finally:
        for session in (second, first):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created_schema:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
