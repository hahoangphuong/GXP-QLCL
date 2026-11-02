"""Fail-closed OIDC identity boundary before GMP evidence intake."""
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import AuthenticatedUser
from backend.app.db.models import Base, AppUser
from backend.app.services.gmp_coverage_review_auth_boundary import (
    append_unresolved_from_authenticated_context,
)
from backend.app.services.gmp_coverage_review_intake import UnresolvedReviewInput


def evidence():
    return UnresolvedReviewInput(
        certificate_version_id=str(uuid4()),
        site_id=str(uuid4()),
        case_id=None,
        source_snapshot_sha256="a" * 64,
        source_document_sha256="b" * 64,
        source_page_reference="synthetic p1",
        rationale="unreviewed synthetic source",
    )


def identity(*, mode="google_oidc", subject="subject-a", email="a@example.test"):
    return AuthenticatedUser(
        username="a@example.test", auth_mode=mode, subject=subject,
        email=email, role_codes=("admin",),
        permissions=frozenset({"gmp.coverage_evidence.intake"}),
    )


@pytest.mark.parametrize("auth", [
    identity(mode="header_stub"),
    identity(mode="google_iap_jwt"),
    identity(subject=""),
    identity(subject="unprovisioned"),
    identity(email="other@example.test"),
])
def test_invalid_or_unprovisioned_oidc_identity_is_denied_before_evidence_write(auth):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add(AppUser(
                username="a", external_subject="subject-a",
                external_email="a@example.test", is_active=True,
            ))
            session.flush()
            with pytest.raises(PermissionError):
                append_unresolved_from_authenticated_context(
                    session, authenticated=auth, evidence=evidence(),
                )
    finally:
        engine.dispose()


def test_provisioned_oidc_identity_still_requires_explicit_database_rbac():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add(AppUser(
                username="a", external_subject="subject-a",
                external_email="a@example.test", is_active=True,
            ))
            session.flush()
            with pytest.raises(PermissionError, match="permission"):
                append_unresolved_from_authenticated_context(
                    session, authenticated=identity(), evidence=evidence(),
                )
    finally:
        engine.dispose()
