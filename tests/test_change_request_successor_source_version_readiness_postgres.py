"""Successor readiness agrees with issuance when a source lacks a version.

Two PostgreSQL Sessions: a long-lived readiness Session first observes a source
with no persisted Version, then sees a separately committed Version and can
issue the successor. All writes use synthetic isolated disposable PostgreSQL.
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
def test_successor_readiness_requires_persisted_source_version(kind):
    url = make_url(DATABASE_URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.database != "gxp_qlcl_test"
        or url.host not in {"localhost", "127.0.0.1"}
        or url.port != 5432
    ):
        pytest.fail("Only loopback disposable gxp_qlcl_test may be mutated.")

    schema = "cr_source_readiness_" + uuid4().hex
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
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

        with factory() as seed:
            company = Company(legal_name="Source readiness " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic Site")
            seed.add(site)
            seed.flush()
            request = ChangeRequest(
                site_id=site.id, state=ChangeRequestState.RECEIVED,
                scope_label="READINESS", description="Synthetic missing-version source",
            )
            seed.add(request)
            seed.flush()
            if kind == "gxp":
                source = Certificate(
                    site_id=site.id, certificate_type="GLP",
                    issuance_basis="administrative_no_inspection", latest_flag=True,
                )
            else:
                source = BusinessEligibilityCertificate(
                    site_id=site.id, company_id=company.id, latest_flag=True,
                )
            seed.add(source)
            seed.flush()
            affected = ChangeRequestAffectedArtifact(
                change_request_id=request.id,
                certificate_id=source.id if kind == "gxp" else None,
                business_eligibility_certificate_id=source.id if kind != "gxp" else None,
            )
            seed.add_all([
                affected,
                AppUser(username="synthetic-source-readiness",
                        display_name="Synthetic issuer", is_active=True),
            ])
            seed.commit()
            ids = {
                "request": request.id,
                "source": source.id,
                "affected": affected.id,
                "version": request.row_version,
            }

        actor = build_authenticated_user(
            "synthetic-source-readiness", "manager",
            permissions=["change_request.edit", "change_request.approve", "certificate.issue"],
        )
        service = CaseWorkflowService()
        action_key = (
            f"issue_certificate_successor:{ids['affected']}"
            if kind == "gxp"
            else f"issue_business_eligibility_successor:{ids['affected']}"
        )
        reader = factory()
        # Readiness must not claim success when mutation has no source version.
        actions = {
            action["action_key"]: action
            for action in service.get_change_request_action_readiness(
                reader, change_request_id=ids["request"], user=actor,
            )
        }
        assert actions[action_key]["available"] is False
        assert actions[action_key]["reason_code"] == "source_version_missing"
        assert actions[action_key]["expected_version"] == ids["version"]

        params = dict(
            change_request_id=ids["request"],
            source_affected_artifact_id=ids["affected"],
            expected_version=ids["version"],
            reason="Synthetic source readiness", user=actor,
        )
        with pytest.raises(HTTPException) as denied:
            if kind == "gxp":
                service.issue_change_request_certificate_successor(reader, **params)
            else:
                service.issue_change_request_business_eligibility_successor(reader, **params)
        assert denied.value.status_code == 409
        reader.rollback()

        # An independent transaction adds the missing version. Reusing the
        # readiness Session must now advertise the real executable action.
        with factory() as writer:
            if kind == "gxp":
                writer.add(CertificateVersion(
                    certificate_id=ids["source"], version_no=1,
                    is_latest_version=True, certificate_number="GLP-SRC",
                    applicable_standard="SYNTHETIC STANDARD",
                ))
            else:
                writer.add(BusinessEligibilityVersion(
                    business_eligibility_certificate_id=ids["source"],
                    version_no=1, certificate_number="DDK-SRC",
                    professional_responsible_person_name="Synthetic person",
                ))
            writer.commit()

        actions = {
            action["action_key"]: action
            for action in service.get_change_request_action_readiness(
                reader, change_request_id=ids["request"], user=actor,
            )
        }
        assert actions[action_key]["available"] is True
        assert actions[action_key]["reason_code"] is None
        if kind == "gxp":
            result = service.issue_change_request_certificate_successor(reader, **params)
        else:
            result = service.issue_change_request_business_eligibility_successor(reader, **params)
        reader.commit()

        with factory() as verify:
            assert verify.get(ChangeRequest, ids["request"]).row_version == result["row_version"]
            assert result["row_version"] != ids["version"]
            assert verify.scalar(select(func.count(ChangeRequestIssuedArtifact.id))) == 1
            action = (
                "change_request.certificate_successor.issue" if kind == "gxp"
                else "change_request.business_eligibility_successor.issue"
            )
            assert verify.scalar(
                select(func.count(AuditEvent.id)).where(AuditEvent.action == action)
            ) == 1
            model = Certificate if kind == "gxp" else BusinessEligibilityCertificate
            assert verify.scalar(select(func.count(model.id))) == 2
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
