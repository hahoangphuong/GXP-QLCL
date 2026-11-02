"""Transaction-level GMP intake/RBAC revocation proof on disposable PostgreSQL only.

Requires migrated disposable database named gxp_qlcl_test. Never connects to rehearsal.
No test rows are committed. A lock timeout is expected when another transaction
attempts to revoke the exact grant that authorized an outstanding intake.
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
    try:
        with engine.connect() as intake_conn, engine.connect() as revoke_conn:
            intake_tx = intake_conn.begin()
            try:
                with Session(bind=intake_conn) as session:
                    suffix = uuid4().hex
                    user = AppUser(username=f"synthetic-intake-{suffix}", is_active=True)
                    role = RbacRole(role_code=f"synthetic-intake-{suffix}")
                    permission = RbacPermission(permission_code="gmp.coverage_evidence.intake")
                    company = Company(legal_name=f"Synthetic {suffix}")
                    session.add_all([user, role, permission, company])
                    session.flush()
                    grant = RbacRolePermission(
                        rbac_role_id=role.id, rbac_permission_id=permission.id
                    )
                    session.add_all([grant, AppUserRole(app_user_id=user.id, rbac_role_id=role.id)])
                    site = Site(company_id=company.id, site_name="Synthetic Site")
                    session.add(site)
                    session.flush()
                    cert = Certificate(site_id=site.id, certificate_type="GMP")
                    session.add(cert)
                    session.flush()
                    version = CertificateVersion(certificate_id=cert.id, version_no=1)
                    session.add(version)
                    session.flush()
                    row_id = append_unresolved_review_event(
                        session,
                        authenticated_user_id=user.id,
                        evidence=UnresolvedReviewInput(
                            certificate_version_id=version.id,
                            site_id=site.id,
                            case_id=None,
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
                                delete(RbacRolePermission).where(RbacRolePermission.id == grant.id)
                            )
                    finally:
                        revoke_tx.rollback()
            finally:
                intake_tx.rollback()
    finally:
        engine.dispose()
