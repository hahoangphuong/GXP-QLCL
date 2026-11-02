"""Case identity must stay stable until UNRESOLVED intake transaction completes.

Only disposable migrated PostgreSQL 'gxp_qlcl_test' is permitted. Synthetic
setup is committed for two-connection visibility and removed in finally.
No Certificate/Case linkage or approval is ever changed by intake.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.app.db.enums import CaseState
from backend.app.db.models import (
    AppUser, AppUserRole, Case, Certificate, CertificateVersion, Company,
    GmpCoverageReviewEvent, RbacPermission, RbacRole, RbacRolePermission, Site,
)
from backend.app.services.gmp_coverage_review_intake import (
    UnresolvedReviewInput, append_unresolved_review_event,
)

URL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not URL.startswith("postgresql") or make_url(URL).database != "gxp_qlcl_test",
    reason="Only disposable PostgreSQL gxp_qlcl_test may run this test",
)


def test_case_rebind_and_certificate_reparent_wait_for_unresolved_intake():
    engine = create_engine(URL, future=True)
    ids = {}
    try:
        with Session(engine) as setup:
            suffix = uuid4().hex
            user = AppUser(username=f"synthetic-coverage-{suffix}", is_active=True)
            role = RbacRole(role_code=f"synthetic-coverage-{suffix}")
            permission = RbacPermission(permission_code="gmp.coverage_evidence.intake")
            company = Company(legal_name=f"Synthetic {suffix}")
            setup.add_all([user, role, permission, company])
            setup.flush()
            assignment = AppUserRole(app_user_id=user.id, rbac_role_id=role.id)
            grant = RbacRolePermission(rbac_role_id=role.id, rbac_permission_id=permission.id)
            setup.add_all([assignment, grant])
            site = Site(company_id=company.id, site_name="Intake Site")
            second_site = Site(company_id=company.id, site_name="Other Site")
            setup.add_all([site, second_site])
            setup.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.__members__[next(iter(CaseState.__members__))])
            certificate = Certificate(site_id=site.id, certificate_type="GMP")
            setup.add_all([case, certificate])
            setup.flush()
            version = CertificateVersion(certificate_id=certificate.id, version_no=1)
            setup.add(version)
            setup.flush()
            ids = dict(user=user.id, role=role.id, permission=permission.id,
                       company=company.id, assignment=assignment.id, grant=grant.id,
                       site=site.id, other_site=second_site.id,
                       case=case.id, cert=certificate.id, version=version.id)
            setup.commit()

        with engine.connect() as writer, engine.connect() as concurrent:
            intake_tx = writer.begin()
            try:
                with Session(bind=writer) as session:
                    event_id = append_unresolved_review_event(
                        session, authenticated_user_id=ids["user"],
                        evidence=UnresolvedReviewInput(
                            certificate_version_id=ids["version"],
                            site_id=ids["site"], case_id=ids["case"],
                            source_snapshot_sha256="a" * 64,
                            source_document_sha256="b" * 64,
                            source_page_reference="synthetic page",
                            rationale="unresolved identity review",
                        ),
                    )
                    assert session.get(GmpCoverageReviewEvent, event_id) is not None
                    for model, predicate, values in (
                        (Case, Case.id == ids["case"], {"site_id": ids["other_site"]}),
                        (Certificate, Certificate.id == ids["cert"], {"site_id": ids["other_site"]}),
                        (CertificateVersion, CertificateVersion.id == ids["version"], {"version_no": 2}),
                    ):
                        tx = concurrent.begin()
                        try:
                            concurrent.execute(text("SET LOCAL lock_timeout = '250ms'"))
                            with pytest.raises(DBAPIError, match="lock timeout"):
                                concurrent.execute(update(model).where(predicate).values(**values))
                        finally:
                            tx.rollback()
            finally:
                intake_tx.rollback()
    finally:
        if ids:
            with engine.begin() as cleanup:
                for model, key in (
                    (AppUserRole, "assignment"),
                    (RbacRolePermission, "grant"),
                    (CertificateVersion, "version"),
                    (Certificate, "cert"),
                    (Case, "case"),
                    (Site, "site"),
                ):
                    cleanup.execute(delete(model).where(model.id == ids[key]))
                cleanup.execute(delete(Site).where(Site.id == ids["other_site"]))
                for model, key in (
                    (Company, "company"),
                    (RbacPermission, "permission"),
                    (RbacRole, "role"),
                    (AppUser, "user"),
                ):
                    cleanup.execute(delete(model).where(model.id == ids[key]))
        engine.dispose()
