"""Change Request workspace must expose committed canonical state, not ORM cache.

The regression retains stale root, Site, Company, approval, detail, affected
and issued-link identities in Session A. Session B commits source changes.
Session A's actual workspace read must either display the committed snapshot
or fail closed when a link points outside the owning Site.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.db.enums import ChangeRequestState
from backend.app.db.models.phase1 import (
    AuditEvent, Certificate, ChangeApproval, ChangeRequest,
    ChangeRequestAffectedArtifact, ChangeRequestDetail,
    ChangeRequestIssuedArtifact, Company, Site,
)
from backend.app.services.catalog import CatalogReadService


DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("scenario", ["fresh_values", "foreign_affected", "foreign_issued"])
def test_change_request_workspace_rechecks_committed_parent_and_link_state(scenario):
    url = make_url(DATABASE_URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.database != "gxp_qlcl_test"
        or url.host not in {"127.0.0.1", "localhost"}
        or url.port != 5432
    ):
        pytest.fail("Only loopback disposable gxp_qlcl_test may be mutated.")

    schema = "cr_workspace_canonical_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = stale = writer = None
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
        with factory() as seed:
            company = Company(legal_name="Original Company")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Original Site")
            other_site = Site(company_id=company.id, site_name="Other Site")
            seed.add_all([site, other_site])
            seed.flush()
            row = ChangeRequest(
                site_id=site.id, state=ChangeRequestState.RECEIVED,
                scope_label="OLD SCOPE", description="Original description",
            )
            seed.add(row)
            seed.flush()
            own_cert = Certificate(
                site_id=site.id, certificate_type="GLP",
                issuance_basis="administrative_no_inspection", latest_flag=False,
            )
            second_cert = Certificate(
                site_id=site.id, certificate_type="GLP",
                issuance_basis="administrative_no_inspection", latest_flag=False,
            )
            foreign_cert = Certificate(
                site_id=other_site.id, certificate_type="GLP",
                issuance_basis="administrative_no_inspection", latest_flag=False,
            )
            seed.add_all([own_cert, second_cert, foreign_cert])
            seed.flush()
            affected = ChangeRequestAffectedArtifact(
                change_request_id=row.id, certificate_id=own_cert.id,
            )
            seed.add(affected)
            seed.flush()
            issued = ChangeRequestIssuedArtifact(
                change_request_id=row.id, source_affected_artifact_id=affected.id,
                certificate_id=own_cert.id,
            )
            approval = ChangeApproval(
                change_request_id=row.id, handled_by_name="OLD REVIEWER",
            )
            detail = ChangeRequestDetail(
                change_request_id=row.id, classification_label="OLD CLASS",
                new_value="OLD VALUE",
            )
            seed.add_all([issued, approval, detail])
            seed.commit()
            ids = {
                "root": row.id, "site": site.id, "company": company.id,
                "affected": affected.id, "issued": issued.id,
                "approval": approval.id, "detail": detail.id,
                "old_cert": own_cert.id, "new_cert": second_cert.id,
                "foreign_cert": foreign_cert.id, "original_version": row.row_version,
            }

        stale = factory()
        models = [
            (ChangeRequest, "root"), (Site, "site"), (Company, "company"),
            (ChangeApproval, "approval"), (ChangeRequestDetail, "detail"),
            (ChangeRequestAffectedArtifact, "affected"),
            (ChangeRequestIssuedArtifact, "issued"),
        ]
        cached = {key: stale.get(model, ids[key]) for model, key in models}
        assert cached["affected"].certificate_id == ids["old_cert"]
        assert cached["root"].scope_label == "OLD SCOPE"
        assert cached["approval"].handled_by_name == "OLD REVIEWER"

        writer = factory()
        writer.get(ChangeRequest, ids["root"]).scope_label = "COMMITTED SCOPE"
        writer.get(ChangeRequest, ids["root"]).row_version += 1
        writer.get(Site, ids["site"]).site_name = "Committed Site"
        writer.get(Company, ids["company"]).legal_name = "Committed Company"
        writer.get(ChangeApproval, ids["approval"]).handled_by_name = "COMMITTED REVIEWER"
        writer.get(ChangeRequestDetail, ids["detail"]).new_value = "COMMITTED VALUE"
        target = ids["foreign_cert"] if scenario != "fresh_values" else ids["new_cert"]
        if scenario == "foreign_affected" or scenario == "fresh_values":
            writer.get(ChangeRequestAffectedArtifact, ids["affected"]).certificate_id = target
        if scenario == "foreign_issued" or scenario == "fresh_values":
            writer.get(ChangeRequestIssuedArtifact, ids["issued"]).certificate_id = target
        writer.commit()
        assert cached["root"].scope_label == "OLD SCOPE"
        assert cached["site"].site_name == "Original Site"

        if scenario == "fresh_values":
            payload = CatalogReadService().get_change_request_workspace(
                stale, change_request_id=ids["root"],
            )
            assert payload["row_version"] == ids["original_version"] + 1
            assert payload["scope_label"] == "COMMITTED SCOPE"
            assert payload["facility_name"] == "Committed Site"
            assert payload["company_name"] == "Committed Company"
            assert payload["handled_by_name"] == "COMMITTED REVIEWER"
            assert payload["details"][0]["new_value"] == "COMMITTED VALUE"
            assert payload["affected_artifacts"][0]["artifact_id"] == ids["new_cert"]
            assert payload["issued_artifacts"][0]["artifact_id"] == ids["new_cert"]
        else:
            with pytest.raises(HTTPException) as denied:
                CatalogReadService().get_change_request_workspace(
                    stale, change_request_id=ids["root"],
                )
            assert denied.value.status_code == 409
            assert "outside the owning site" in str(denied.value.detail)
        stale.rollback()
        with factory() as verify:
            persisted = verify.get(ChangeRequest, ids["root"])
            assert persisted.scope_label == "COMMITTED SCOPE"
            assert persisted.row_version == ids["original_version"] + 1
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        for session in (stale, writer):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
