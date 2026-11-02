"""Locked GMP intake queries must refresh preloaded SQLAlchemy identity-map rows."""
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from backend.app.db.enums import CaseState
from backend.app.db.models import (
    Base, AppUser, AppUserRole, Case, Certificate, CertificateVersion,
    Company, GmpCoverageReviewEvent, RbacPermission, RbacRole,
    RbacRolePermission, Site,
)
from backend.app.services.gmp_coverage_review_intake import (
    UnresolvedReviewInput, append_unresolved_review_event,
)


def test_preloaded_case_must_refresh_after_database_rebind(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'identity-refresh.db'}", future=True)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as setup:
            suffix = uuid4().hex
            actor = AppUser(username=f"stale-map-{suffix}", is_active=True)
            role = RbacRole(role_code=f"stale-map-{suffix}")
            permission = RbacPermission(permission_code="gmp.coverage_evidence.intake")
            company = Company(legal_name="Synthetic map owner")
            setup.add_all([actor, role, permission, company])
            setup.flush()
            setup.add_all([
                AppUserRole(app_user_id=actor.id, rbac_role_id=role.id),
                RbacRolePermission(rbac_role_id=role.id, rbac_permission_id=permission.id),
            ])
            site_a = Site(company_id=company.id, site_name="Originally linked")
            site_b = Site(company_id=company.id, site_name="Rebound")
            setup.add_all([site_a, site_b])
            setup.flush()
            case = Case(site_id=site_a.id, gxp_type="GMP", state=CaseState.DRAFT)
            cert = Certificate(site_id=site_a.id, certificate_type="GMP")
            setup.add_all([case, cert])
            setup.flush()
            version = CertificateVersion(certificate_id=cert.id, version_no=1)
            setup.add(version)
            setup.commit()
            actor_id, case_id, site_id, moved_site_id, version_id = (
                actor.id, case.id, site_a.id, site_b.id, version.id,
            )

        with Session(engine, expire_on_commit=False) as intake:
            loaded_case = intake.get(Case, case_id)
            assert loaded_case.site_id == site_id
            # Another actor changes the Case in the database before intake.
            with Session(engine) as concurrent:
                concurrent.execute(
                    update(Case).where(Case.id == case_id)
                    .values(site_id=moved_site_id)
                )
                concurrent.commit()
            # The old object is still held in this caller-owned identity map.
            assert loaded_case.site_id == site_id
            with pytest.raises(ValueError, match="Case must belong"):
                append_unresolved_review_event(
                    intake,
                    authenticated_user_id=actor_id,
                    evidence=UnresolvedReviewInput(
                        certificate_version_id=version_id,
                        site_id=site_id, case_id=case_id,
                        source_snapshot_sha256="a" * 64,
                        source_document_sha256="b" * 64,
                        source_page_reference="synthetic p1",
                        rationale="must not accept stale Case ownership",
                    ),
                )
            assert intake.scalars(select(GmpCoverageReviewEvent)).all() == []
            assert loaded_case.site_id == moved_site_id
            intake.rollback()
    finally:
        engine.dispose()


def test_preloaded_oidc_email_must_refresh_before_authenticated_handoff(tmp_path, monkeypatch):
    from backend.app.auth import AuthenticatedUser
    from backend.app.services import gmp_coverage_review_auth_boundary as boundary

    engine = create_engine(f"sqlite:///{tmp_path / 'oidc-refresh.db'}", future=True)
    Base.metadata.create_all(engine)
    try:
        subject = f"synthetic-{uuid4().hex}"
        with Session(engine) as setup:
            actor = AppUser(
                username=subject, external_subject=subject,
                external_email="original@example.test", is_active=True,
            )
            setup.add(actor)
            setup.commit()
            actor_id = actor.id

        with Session(engine, expire_on_commit=False) as session:
            cached = session.get(AppUser, actor_id)
            assert cached.external_email == "original@example.test"
            with Session(engine) as concurrent:
                concurrent.execute(
                    update(AppUser).where(AppUser.id == actor_id)
                    .values(external_email="changed@example.test")
                )
                concurrent.commit()
            assert cached.external_email == "original@example.test"

            downstream_calls = []
            monkeypatch.setattr(
                boundary, "append_unresolved_review_event",
                lambda *_args, **_kwargs: downstream_calls.append(True),
            )
            with pytest.raises(PermissionError, match="email and subject"):
                boundary.append_unresolved_from_authenticated_context(
                    session,
                    authenticated=AuthenticatedUser(
                        username=subject, auth_mode="google_oidc",
                        subject=subject, email="original@example.test",
                    ),
                    evidence=UnresolvedReviewInput(
                        certificate_version_id=str(uuid4()),
                        site_id=str(uuid4()), case_id=None,
                        source_snapshot_sha256="a" * 64,
                        source_document_sha256="b" * 64,
                        source_page_reference="synthetic", rationale="synthetic",
                    ),
                )
            assert downstream_calls == []
            assert cached.external_email == "changed@example.test"
            session.rollback()
    finally:
        engine.dispose()
