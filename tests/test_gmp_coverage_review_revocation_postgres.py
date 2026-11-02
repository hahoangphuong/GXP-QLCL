"""Transaction-level GMP intake/RBAC revocation proof on disposable PostgreSQL only.

Requires migrated disposable database named gxp_qlcl_test. Never connects to rehearsal.
Fixture rows are committed ONLY to the disposable test DB so two independent\ntransactions can see them, then explicitly removed in finally. A lock timeout\nis expected on an outstanding intake transaction.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.app.db.models import (
    AppUser, AppUserRole, RbacPermission, RbacRole, RbacRolePermission,
    Certificate, CertificateVersion, Company, GmpCoverageReviewEvent, Site,
)
from backend.app.services.gmp_coverage_review_intake import (
    UnresolvedReviewInput, append_unresolved_review_event,
)

URL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not URL.startswith("postgresql") or make_url(URL).database != "gxp_qlcl_test",
    reason="Only disposable migrated PostgreSQL gxp_qlcl_test may run this test",
)


def test_revoking_grant_waits_for_outstanding_evidence_intake_transaction():
    engine = create_engine(URL, future=True)
    ids = {}
    try:
        # Commit the synthetic fixture first; an uncommitted grant would be
        # invisible to the second transaction and invalidate this test.
        with Session(engine) as setup:
            suffix = uuid4().hex
            user = AppUser(username=f"synthetic-intake-{suffix}", is_active=True)
            role = RbacRole(role_code=f"synthetic-intake-{suffix}")
            permission = RbacPermission(permission_code="gmp.coverage_evidence.intake")
            company = Company(legal_name=f"Synthetic {suffix}")
            setup.add_all([user, role, permission, company])
            setup.flush()
            grant = RbacRolePermission(rbac_role_id=role.id, rbac_permission_id=permission.id)
            assignment = AppUserRole(app_user_id=user.id, rbac_role_id=role.id)
            setup.add_all([grant, assignment])
            site = Site(company_id=company.id, site_name="Synthetic Site")
            setup.add(site)
            setup.flush()
            cert = Certificate(site_id=site.id, certificate_type="GMP")
            setup.add(cert)
            setup.flush()
            version = CertificateVersion(certificate_id=cert.id, version_no=1)
            setup.add(version)
            setup.flush()
            ids = dict(user=user.id, role=role.id, permission=permission.id,
                       company=company.id, grant=grant.id, assignment=assignment.id,
                       site=site.id, cert=cert.id, version=version.id)
            setup.commit()

        with engine.connect() as intake_conn, engine.connect() as revoke_conn:
            intake_tx = intake_conn.begin()
            try:
                with Session(bind=intake_conn) as session:
                    row_id = append_unresolved_review_event(
                        session,
                        authenticated_user_id=ids["user"],
                        evidence=UnresolvedReviewInput(
                            certificate_version_id=ids["version"],
                            site_id=ids["site"], case_id=None,
                            source_snapshot_sha256="a" * 64,
                            source_document_sha256="b" * 64,
                            source_page_reference="synthetic p1",
                            rationale="Synthetic unresolved evidence only",
                        ),
                    )
                    assert session.get(GmpCoverageReviewEvent, row_id) is not None
                    revoke_tx = revoke_conn.begin()
                    try:
                        revoke_conn.execute(text("SET LOCAL lock_timeout = '250ms'"))
                        with pytest.raises(DBAPIError, match="lock timeout"):
                            revoke_conn.execute(
                                delete(RbacRolePermission).where(
                                    RbacRolePermission.id == ids["grant"]
                                )
                            )
                    finally:
                        revoke_tx.rollback()
            finally:
                intake_tx.rollback()
    finally:
        if ids:
            # Cleanup even when assertions fail. Never target real databases.
            with engine.begin() as cleanup:
                for model, key in (
                    (AppUserRole, "assignment"),
                    (RbacRolePermission, "grant"),
                    (CertificateVersion, "version"),
                    (Certificate, "cert"),
                    (Site, "site"),
                    (Company, "company"),
                    (RbacPermission, "permission"),
                    (RbacRole, "role"),
                    (AppUser, "user"),
                ):
                    cleanup.execute(delete(model).where(model.id == ids[key]))
        engine.dispose()
