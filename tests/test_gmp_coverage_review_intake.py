"""UNRESOLVED intake must never confer reviewed GMP coverage authority."""
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.models import AppUser, AppUserRole, RbacRole, RbacPermission, RbacRolePermission, Base, Case, Certificate, CertificateVersion, Company, GmpCoverageReviewEvent, Site
from backend.app.db.enums import CaseState
from backend.app.services.gmp_coverage_review_intake import UnresolvedReviewInput, append_unresolved_review_event


def test_unresolved_intake_bound_to_active_actor_and_real_site():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = AppUser(username="synthetic-operator", is_active=True)
            inactive = AppUser(username="synthetic-inactive", is_active=False)
            company = Company(legal_name="Synthetic company")
            session.add_all([user, inactive, company])
            session.flush()
            site = Site(company_id=company.id, site_name="Synthetic Site")
            other_site = Site(company_id=company.id, site_name="Other Site")
            session.add_all([site, other_site])
            session.flush()
            certificate = Certificate(site_id=site.id, certificate_type="GMP")
            session.add(certificate)
            session.flush()
            version = CertificateVersion(certificate_id=certificate.id, version_no=1)
            session.add(version)
            session.flush()
            role = RbacRole(role_code="synthetic-evidence-operator")
            permission = RbacPermission(permission_code="gmp.coverage_evidence.intake")
            session.add_all([role, permission])
            session.flush()
            session.add(RbacRolePermission(rbac_role_id=role.id, rbac_permission_id=permission.id))
            session.add(AppUserRole(app_user_id=user.id, rbac_role_id=role.id))
            session.flush()
            data = UnresolvedReviewInput(
                certificate_version_id=version.id, site_id=other_site.id,
                case_id=None, source_snapshot_sha256="a"*64,
                source_document_sha256="b"*64, source_page_reference="Synthetic p2",
                rationale="Source needs operator adjudication",
            )
            with pytest.raises(ValueError, match="Active authenticated"):
                append_unresolved_review_event(session, evidence=data, authenticated_user_id=inactive.id)
            with pytest.raises(ValueError, match="SHA256"):
                append_unresolved_review_event(session, evidence=UnresolvedReviewInput(
                    **{**data.__dict__, "source_document_sha256": "x"*64}
                ), authenticated_user_id=user.id)
            session.execute(AppUserRole.__table__.delete().where(AppUserRole.app_user_id == user.id))
            with pytest.raises(PermissionError, match="permission"):
                append_unresolved_review_event(session, evidence=data, authenticated_user_id=user.id)
            session.add(AppUserRole(app_user_id=user.id, rbac_role_id=role.id))
            session.flush()
            row_id = append_unresolved_review_event(session, evidence=data, authenticated_user_id=user.id)
            stored = session.get(GmpCoverageReviewEvent, row_id)
            assert stored.decision_status == "UNRESOLVED"
            assert stored.decision_kind == "SITE_COVERAGE"
            assert stored.recorded_by_user_id == user.id
            assert stored.reviewer_user_id == user.id
            assert stored.site_id == other_site.id
            assert stored.case_id is None
            session.rollback()
        with Session(engine) as session:
            assert session.scalars(select(GmpCoverageReviewEvent)).all() == []
    finally:
        engine.dispose()


def test_intake_requires_canonical_actor_uuid_before_database_access():
    from backend.app.services.gmp_coverage_review_intake import _uuid
    generated = str(uuid4())
    assert _uuid(generated) == generated
    with pytest.raises(ValueError, match="Version 4"):
        _uuid("00000000-0000-0000-0000-000000000001")
    with pytest.raises(ValueError):
        _uuid("not-an-identity")
