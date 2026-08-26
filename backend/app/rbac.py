from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import AppUser, AppUserRole, RbacPermission, RbacRole, RbacRolePermission


@dataclass(frozen=True)
class RoleDefinition:
    role_code: str
    description: str
    permission_codes: tuple[str, ...]


@dataclass(frozen=True)
class PermissionDefinition:
    permission_code: str
    description: str


@dataclass(frozen=True)
class RbacBaselineSummary:
    roles_created: int
    roles_verified: int
    permissions_created: int
    permissions_verified: int
    role_permissions_created: int
    role_permissions_verified: int


@dataclass(frozen=True)
class AppUserProvisioningSummary:
    user_created: bool
    user_updated: bool
    role_assignment_created: bool
    username: str
    external_email: str
    external_subject: str | None
    role_code: str


class RbacBaselineError(RuntimeError):
    """Raised when the canonical RBAC baseline is missing or inconsistent."""


class AppUserProvisioningError(RuntimeError):
    """Raised when explicit app-user provisioning is invalid or conflicts."""


ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "reader": frozenset({"case.view", "certificate.view", "document.read", "capa.view"}),
    "inspector": frozenset(
        {
            "case.view",
            "case.edit",
            "inspection.plan",
            "inspection.edit",
            "capa.view",
            "capa.edit",
            "certificate.view",
            "document.read",
            "document.write",
            "document.move",
            "document.rename",
        }
    ),
    "manager": frozenset(
        {
            "case.view",
            "case.edit",
            "case.assign",
            "inspection.plan",
            "inspection.edit",
            "capa.view",
            "capa.edit",
            "capa.assess",
            "certificate.view",
            "certificate.edit",
            "certificate.approve",
            "document.read",
            "document.write",
            "document.move",
            "document.rename",
            "document.archive",
        }
    ),
    "admin": frozenset(
        {
            "case.view",
            "case.edit",
            "case.assign",
            "inspection.plan",
            "inspection.edit",
            "capa.view",
            "capa.edit",
            "capa.assess",
            "certificate.view",
            "certificate.edit",
            "certificate.approve",
            "certificate.issue",
            "document.read",
            "document.write",
            "document.move",
            "document.rename",
            "document.archive",
            "admin.users",
            "admin.roles",
        }
    ),
}

ROLE_DESCRIPTIONS: dict[str, str] = {
    "reader": "Read-only access to cases, certificates, and documents.",
    "inspector": "Operational inspection user who can update cases and documents.",
    "manager": "Supervisory user who can assess CAPA and approve certificates.",
    "admin": "Administrative user who can manage application users and roles.",
}

PERMISSION_DESCRIPTIONS: dict[str, str] = {
    "admin.roles": "Manage RBAC role assignments and role definitions.",
    "admin.users": "Manage application users and their active assignments.",
    "capa.assess": "Assess and resolve CAPA review outcomes.",
    "capa.edit": "Create or update CAPA workflow details.",
    "capa.view": "View CAPA workflow details.",
    "case.assign": "Assign case ownership or responsibility.",
    "case.edit": "Create or update case details.",
    "case.view": "View case details.",
    "certificate.approve": "Approve certificate decisions.",
    "certificate.edit": "Create or update certificate details.",
    "certificate.issue": "Issue certificates and promote current state.",
    "certificate.view": "View certificate details.",
    "document.archive": "Archive or retire document variants.",
    "document.move": "Move documents within approved storage boundaries.",
    "document.read": "Read document metadata and binary references.",
    "document.rename": "Rename documents within approved storage boundaries.",
    "document.write": "Create or update document metadata and renditions.",
    "inspection.edit": "Update inspection planning and outcomes.",
    "inspection.plan": "Plan inspections and related workflow activities.",
}

ROLE_DEFINITIONS: tuple[RoleDefinition, ...] = tuple(
    RoleDefinition(
        role_code=role_code,
        description=ROLE_DESCRIPTIONS[role_code],
        permission_codes=tuple(sorted(ROLE_PERMISSIONS[role_code])),
    )
    for role_code in ("reader", "inspector", "manager", "admin")
)

PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = tuple(
    PermissionDefinition(permission_code=permission_code, description=PERMISSION_DESCRIPTIONS[permission_code])
    for permission_code in sorted(PERMISSION_DESCRIPTIONS)
)

BUILTIN_ROLE_CODES: tuple[str, ...] = tuple(role.role_code for role in ROLE_DEFINITIONS)
BUILTIN_PERMISSION_CODES: tuple[str, ...] = tuple(permission.permission_code for permission in PERMISSION_DEFINITIONS)


def _single_row(
    session: Session,
    model: type[RbacRole] | type[RbacPermission] | type[AppUser],
    field_name: str,
    value: str,
) -> object | None:
    field = getattr(model, field_name)
    rows = session.scalars(select(model).where(field == value)).all()
    if len(rows) > 1:
        raise RbacBaselineError(f"Expected unique {model.__tablename__}.{field_name}={value!r}, found {len(rows)} rows.")
    return rows[0] if rows else None


def _normalize_email(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    return normalized or None


def _normalize_subject(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _normalize_username(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise AppUserProvisioningError("username must not be blank.")
    return normalized


def _normalize_role_code(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise AppUserProvisioningError("role must not be blank.")
    return normalized


def _ensure_builtin_rbac_baseline(
    session: Session,
    *,
    allow_create: bool,
) -> RbacBaselineSummary:
    permissions_created = 0
    permissions_verified = 0
    roles_created = 0
    roles_verified = 0
    role_permissions_created = 0
    role_permissions_verified = 0

    permission_rows_by_code: dict[str, RbacPermission] = {}
    for definition in PERMISSION_DEFINITIONS:
        existing = _single_row(session, RbacPermission, "permission_code", definition.permission_code)
        if existing is None:
            if not allow_create:
                raise RbacBaselineError(f"Missing required RBAC permission: {definition.permission_code}")
            existing = RbacPermission(
                permission_code=definition.permission_code,
                description=definition.description,
            )
            session.add(existing)
            permissions_created += 1
        else:
            if (existing.description or "") != definition.description:
                raise RbacBaselineError(
                    f"RBAC permission {definition.permission_code!r} has conflicting description."
                )
            permissions_verified += 1
        permission_rows_by_code[definition.permission_code] = existing

    session.flush()

    role_rows_by_code: dict[str, RbacRole] = {}
    for definition in ROLE_DEFINITIONS:
        existing = _single_row(session, RbacRole, "role_code", definition.role_code)
        if existing is None:
            if not allow_create:
                raise RbacBaselineError(f"Missing required RBAC role: {definition.role_code}")
            existing = RbacRole(
                role_code=definition.role_code,
                description=definition.description,
            )
            session.add(existing)
            roles_created += 1
        else:
            if (existing.description or "") != definition.description:
                raise RbacBaselineError(f"RBAC role {definition.role_code!r} has conflicting description.")
            roles_verified += 1
        role_rows_by_code[definition.role_code] = existing

    session.flush()

    for definition in ROLE_DEFINITIONS:
        role = role_rows_by_code[definition.role_code]
        current_permission_codes = session.execute(
            select(RbacPermission.permission_code)
            .join(RbacRolePermission, RbacRolePermission.rbac_permission_id == RbacPermission.id)
            .where(RbacRolePermission.rbac_role_id == role.id)
        ).scalars().all()
        if len(current_permission_codes) != len(set(current_permission_codes)):
            raise RbacBaselineError(f"RBAC role {definition.role_code!r} has duplicate role-permission mappings.")
        current_permission_code_set = set(current_permission_codes)
        expected_permission_code_set = set(definition.permission_codes)
        unexpected_permission_codes = sorted(current_permission_code_set - expected_permission_code_set)
        if unexpected_permission_codes:
            raise RbacBaselineError(
                f"RBAC role {definition.role_code!r} has unexpected permissions: {unexpected_permission_codes!r}."
            )
        missing_permission_codes = sorted(expected_permission_code_set - current_permission_code_set)
        if missing_permission_codes and not allow_create:
            raise RbacBaselineError(
                f"RBAC role {definition.role_code!r} is missing permissions: {missing_permission_codes!r}."
            )
        for permission_code in missing_permission_codes:
            session.add(
                RbacRolePermission(
                    rbac_role_id=role.id,
                    rbac_permission_id=permission_rows_by_code[permission_code].id,
                )
            )
            role_permissions_created += 1
        role_permissions_verified += len(expected_permission_code_set.intersection(current_permission_code_set))

    return RbacBaselineSummary(
        roles_created=roles_created,
        roles_verified=roles_verified,
        permissions_created=permissions_created,
        permissions_verified=permissions_verified,
        role_permissions_created=role_permissions_created,
        role_permissions_verified=role_permissions_verified,
    )


def ensure_builtin_rbac_baseline(session: Session) -> RbacBaselineSummary:
    return _ensure_builtin_rbac_baseline(session, allow_create=True)


def verify_builtin_rbac_baseline(session: Session) -> RbacBaselineSummary:
    return _ensure_builtin_rbac_baseline(session, allow_create=False)


def provision_app_user(
    session: Session,
    *,
    username: str,
    email: str,
    role_code: str,
    external_subject: str | None = None,
    display_name: str | None = None,
) -> AppUserProvisioningSummary:
    normalized_username = _normalize_username(username)
    normalized_email = _normalize_email(email)
    if normalized_email is None:
        raise AppUserProvisioningError("email must not be blank.")
    normalized_role_code = _normalize_role_code(role_code)
    normalized_subject = _normalize_subject(external_subject)
    normalized_display_name = (display_name or "").strip() or None

    role = _single_row(session, RbacRole, "role_code", normalized_role_code)
    if role is None:
        raise AppUserProvisioningError(f"RBAC role does not exist: {normalized_role_code}")

    matched_users = [
        user
        for user in (
            _single_row(session, AppUser, "username", normalized_username),
            _single_row(session, AppUser, "external_email", normalized_email),
            _single_row(session, AppUser, "external_subject", normalized_subject) if normalized_subject is not None else None,
        )
        if user is not None
    ]
    unique_user_ids = {user.id for user in matched_users}
    if len(unique_user_ids) > 1:
        raise AppUserProvisioningError("Provisioning identity matches multiple existing AppUser rows.")

    user_created = False
    user_updated = False
    app_user = matched_users[0] if matched_users else None
    if app_user is None:
        app_user = AppUser(
            username=normalized_username,
            external_email=normalized_email,
            external_subject=normalized_subject,
            display_name=normalized_display_name or normalized_username,
            is_active=True,
        )
        session.add(app_user)
        session.flush()
        user_created = True
    else:
        if app_user.username != normalized_username:
            raise AppUserProvisioningError(
                f"Provisioning username {normalized_username!r} conflicts with existing user {app_user.username!r}."
            )
        existing_email = _normalize_email(app_user.external_email)
        if existing_email is not None and existing_email != normalized_email:
            raise AppUserProvisioningError(
                f"Provisioning email {normalized_email!r} conflicts with existing user email {existing_email!r}."
            )
        if existing_email is None:
            app_user.external_email = normalized_email
            user_updated = True
        if normalized_subject is not None:
            existing_subject = _normalize_subject(app_user.external_subject)
            if existing_subject is not None and existing_subject != normalized_subject:
                raise AppUserProvisioningError("Provisioning subject conflicts with existing AppUser.external_subject.")
            if existing_subject is None:
                app_user.external_subject = normalized_subject
                user_updated = True
        if normalized_display_name is not None and app_user.display_name != normalized_display_name:
            app_user.display_name = normalized_display_name
            user_updated = True
        if not app_user.is_active:
            app_user.is_active = True
            user_updated = True

    assignment = session.scalar(
        select(AppUserRole).where(
            AppUserRole.app_user_id == app_user.id,
            AppUserRole.rbac_role_id == role.id,
        )
    )
    role_assignment_created = False
    if assignment is None:
        session.add(AppUserRole(app_user_id=app_user.id, rbac_role_id=role.id))
        role_assignment_created = True

    return AppUserProvisioningSummary(
        user_created=user_created,
        user_updated=user_updated,
        role_assignment_created=role_assignment_created,
        username=app_user.username,
        external_email=app_user.external_email or normalized_email,
        external_subject=app_user.external_subject,
        role_code=role.role_code,
    )
