"""Restricted, transaction-owned intake of UNRESOLVED GMP review evidence.

This is NOT an approval endpoint. Trusted identity is derived by the caller from
authenticated server context, never from review payload fields. No Case
certificate link, current flag, or adjudication is modified.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import (
    AppUser, AppUserRole, RbacPermission, RbacRolePermission,
    Case, Certificate, CertificateVersion, GmpCoverageReviewEvent, Site,
)


@dataclass(frozen=True)
class UnresolvedReviewInput:
    certificate_version_id: str
    site_id: str
    case_id: str | None
    source_snapshot_sha256: str
    source_document_sha256: str
    source_page_reference: str
    rationale: str


def _uuid(value: str) -> str:
    parsed = UUID(value)
    if parsed.version != 4:
        raise ValueError('Version 4 UUID required for canonical identity.')
    return str(parsed)


def _digest(value: str) -> str:
    if len(value) != 64 or any(c not in "0123456789abcdefABCDEF" for c in value):
        raise ValueError("Evidence requires a SHA256 hexadecimal digest.")
    return value.lower()


def append_unresolved_review_event(
    session: Session,
    *,
    evidence: UnresolvedReviewInput,
    authenticated_user_id: str,
) -> str:
    """Insert only UNRESOLVED source intake; caller owns commit and RBAC.

    No caller-supplied reviewer, status, or timestamp is accepted. Even an
    authenticated user cannot issue a VERIFIED decision through this method.
    """
    actor_id = _uuid(authenticated_user_id)
    if actor_id != authenticated_user_id:
        raise ValueError('Authenticated identity must be canonical UUID.')
    # Lock the actor row until the intake transaction commits or rolls back.
    # PostgreSQL deactivation updates must then serialize with this intake.
    user = session.scalars(
        select(AppUser).where(AppUser.id == actor_id).with_for_update(of=AppUser)
    ).one_or_none()
    if user is None or not user.is_active:
        raise ValueError("Active authenticated AppUser required.")
    # Permission is read from canonical DB grants, not a caller-supplied role.
    # Fail closed until an administrator explicitly provisions this permission.
    permitted = session.execute(
        select(AppUserRole.id)
        .join(RbacRolePermission, AppUserRole.rbac_role_id == RbacRolePermission.rbac_role_id)
        .join(RbacPermission, RbacRolePermission.rbac_permission_id == RbacPermission.id)
        .where(
            AppUserRole.app_user_id == actor_id,
            RbacPermission.permission_code == "gmp.coverage_evidence.intake",
        )
        # Hold the grant rows while inserting evidence. A concurrent role
        # assignment or role-permission revocation cannot commit between this
        # authorization check and the transaction-owned evidence INSERT.
        .with_for_update(of=(AppUserRole, RbacRolePermission))
        .limit(1)
    ).scalar_one_or_none()
    if permitted is None:
        raise PermissionError("GMP evidence intake permission required.")
    version = session.get(CertificateVersion, _uuid(evidence.certificate_version_id))
    site = session.get(Site, _uuid(evidence.site_id))
    if version is None or site is None:
        raise ValueError("Certificate version and Site must exist.")
    certificate = session.get(Certificate, version.certificate_id)
    if certificate is None or certificate.certificate_type != "GMP":
        raise ValueError("GMP CertificateVersion required.")
    case_id = _uuid(evidence.case_id) if evidence.case_id is not None else None
    if case_id is not None:
        linked_case = session.get(Case, case_id)
        if linked_case is None or linked_case.site_id != site.id or linked_case.gxp_type != "GMP":
            raise ValueError("Case must belong to the evidenced GMP Site.")
    if not evidence.source_page_reference.strip() or not evidence.rationale.strip():
        raise ValueError("Source page and rationale required.")
    row = GmpCoverageReviewEvent(
        certificate_version_id=version.id,
        site_id=site.id,
        case_id=case_id,
        decision_kind="CASE_LINK" if case_id is not None else "SITE_COVERAGE",
        decision_status="UNRESOLVED",
        source_snapshot_sha256=_digest(evidence.source_snapshot_sha256),
        source_document_sha256=_digest(evidence.source_document_sha256),
        source_page_reference=evidence.source_page_reference,
        rationale=evidence.rationale,
        reviewer_user_id=actor_id,
        recorded_by_user_id=actor_id,
        reviewed_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.flush()
    return row.id
