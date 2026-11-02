"""Non-routed authenticated boundary for GMP UNRESOLVED evidence intake.

Requires a trusted Google OIDC identity and matching provisioned AppUser.
Not exposed as a public HTTP endpoint and never records VERIFIED decisions.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.auth import AuthenticatedUser
from backend.app.db.models import AppUser
from backend.app.services.gmp_coverage_review_intake import (
    UnresolvedReviewInput, append_unresolved_review_event,
)


def append_unresolved_from_authenticated_context(
    session: Session,
    *,
    authenticated: AuthenticatedUser,
    evidence: UnresolvedReviewInput,
) -> str:
    """Bind server-authenticated OIDC subject to exactly one active AppUser.

    No caller-supplied database user id is allowed across this boundary.
    The lower-level service enforces the current DB RBAC grant in the same session.
    """
    # ORM SELECT triggers autoflush by default. Reject pending state
    # before the OIDC lookup, not just in the downstream intake service.
    if session.new or session.dirty or session.deleted:
        raise ValueError("GMP evidence intake requires a clean Session.")
    if authenticated.auth_mode != "google_oidc" or not authenticated.subject:
        raise PermissionError("Verified Google OIDC subject required for GMP intake.")
    matches = session.scalars(
        select(AppUser).where(
            AppUser.external_subject == authenticated.subject,
            AppUser.is_active.is_(True),
        )
    ).all()
    if len(matches) != 1:
        raise PermissionError("Exactly one active provisioned subject required.")
    user = matches[0]
    if authenticated.email and (
        not user.external_email or
        user.external_email.strip().lower() != authenticated.email.strip().lower()
    ):
        raise PermissionError("OIDC email and subject provisioning mismatch.")
    return append_unresolved_review_event(
        session, evidence=evidence, authenticated_user_id=user.id,
    )
