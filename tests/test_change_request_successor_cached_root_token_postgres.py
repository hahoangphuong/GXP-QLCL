"""PostgreSQL: successor issuance must validate the committed Change Request owner.

A caches the parent, B commits a real header mutation, then A uses a stale
or fresh request token. Check business rows and audit, not just the exception.
Only run against disposable gxp_qlcl_test and an isolated synthetic schema.
"""
from __future__ import annotations

from datetime import date
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


@pytest.mark.parametrize("kind", ["certificate", "business_eligibility"])
@pytest.mark.parametrize("request_token", ["stale", "fresh"])
def test_successor_uses_committed_change_request_token(kind, request_token):
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted.")
    schema = "change_successor_token_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = cached_session = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Synthetic successor " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic successor Site")
            seed.add(site)
            seed.flush()
            row = ChangeRequest(
                site_id=site.id, state=ChangeRequestState.RECEIVED,
                scope_label="ORIGINAL", description="Synthetic source",
            )
            seed.add(row)
            seed.flush()
            if kind == "certificate":
                source = Certificate(
                    site_id=site.id, certificate_type="GLP",
                    issuance_basis="administrative_no_inspection", latest_flag=True,
                )
                seed.add(source)
                seed.flush()
                seed.add(CertificateVersion(
                    certificate_id=source.id, version_no=1,
                    certificate_number="GLP-SOURCE", is_latest_version=True,
                ))
                affected = ChangeRequestAffectedArtifact(
                    change_request_id=row.id, certificate_id=source.id,
                )
            else:
                source = BusinessEligibilityCertificate(
                    site_id=site.id, company_id=company.id, latest_flag=True,
                )
                seed.add(source)
                seed.flush()
                seed.add(BusinessEligibilityVersion(
                    business_eligibility_certificate_id=source.id,
                    version_no=1, certificate_number="BE-SOURCE",
                ))
                affected = ChangeRequestAffectedArtifact(
                    change_request_id=row.id,
                    business_eligibility_certificate_id=source.id,
                )
            seed.add(affected)
            seed.add(AppUser(
                username="synthetic-successor", display_name="Synthetic actor", is_active=True,
            ))
            seed.commit()
            row_id, affected_id, initial_token = row.id, affected.id, row.row_version

        service = CaseWorkflowService()
        actor = build_authenticated_user(
            "synthetic-successor", "manager",
            permissions=["change_request.edit", "change_request.approve"],
        )
        cached_session = factory()
        cached_parent = cached_session.get(ChangeRequest, row_id)
        assert cached_parent.row_version == initial_token
        assert cached_parent.state == ChangeRequestState.RECEIVED

        with factory() as writer:
            committed = service.update_change_request(
                writer, change_request_id=row_id, expected_version=initial_token,
                scope_label="COMMITTED", description="Synthetic source",
                submitted_on=date(2026, 11, 5), requester_name="Synthetic",
                reason="Independent committed header mutation", user=actor,
            )
            writer.commit()
        committed_token = committed["row_version"]
        assert committed_token != initial_token
        assert cached_parent.row_version == initial_token, "Precondition: stale ORM identity"

        def issue(token):
            args = dict(
                change_request_id=row_id, source_affected_artifact_id=affected_id,
                expected_version=token, reason="Synthetic successor issuance", user=actor,
            )
            if kind == "certificate":
                return service.issue_change_request_certificate_successor(cached_session, **args)
            return service.issue_change_request_business_eligibility_successor(cached_session, **args)

        if request_token == "stale":
            with pytest.raises(HTTPException) as denied:
                issue(initial_token)
            assert denied.value.status_code == 409
            assert "Stale change_request update" in str(denied.value.detail)
            cached_session.rollback()
        else:
            issued = issue(committed_token)
            cached_session.commit()
            assert issued["row_version"] != committed_token

        with factory() as verify:
            persisted = verify.get(ChangeRequest, row_id)
            assert persisted.scope_label == "COMMITTED"
            assert persisted.row_version == (
                committed_token if request_token == "stale" else issued["row_version"]
            )
            assert verify.scalar(select(func.count(ChangeRequestIssuedArtifact.id))) == (
                0 if request_token == "stale" else 1
            )
            root_model = Certificate if kind == "certificate" else BusinessEligibilityCertificate
            assert verify.scalar(select(func.count(root_model.id))) == (
                1 if request_token == "stale" else 2
            )
            action = (
                "change_request.certificate_successor.issue" if kind == "certificate"
                else "change_request.business_eligibility_successor.issue"
            )
            assert verify.scalar(select(func.count(AuditEvent.id)).where(
                AuditEvent.action == "change_request.update"
            )) == 1
            assert verify.scalar(select(func.count(AuditEvent.id)).where(
                AuditEvent.action == action
            )) == (0 if request_token == "stale" else 1)
    finally:
        if cached_session is not None:
            cached_session.rollback()
            cached_session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
