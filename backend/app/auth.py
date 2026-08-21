from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from fastapi import HTTPException, Request
from sqlalchemy import select

from backend.app.db.models.phase1 import AppUser, AppUserRole, RbacPermission, RbacRole, RbacRolePermission


IAP_JWT_HEADER = "X-Goog-IAP-JWT-Assertion"
IAP_EMAIL_HEADER = "X-Goog-Authenticated-User-Email"
IAP_SUBJECT_HEADER = "X-Goog-Authenticated-User-Id"
DEFAULT_AUTH_MODE = "header_stub"
DEFAULT_IAP_CERTS_URL = "https://www.gstatic.com/iap/verify/public_key"


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    auth_mode: str
    email: str | None = None
    subject: str | None = None
    role_codes: tuple[str, ...] = ()
    permissions: frozenset[str] = frozenset()

    @property
    def role(self) -> str:
        return self.role_codes[0] if self.role_codes else ""


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

ALLOWED_READ_ROLES = {"reader", "inspector", "manager", "admin"}


def build_authenticated_user(
    username: str | None,
    role: str | None = None,
    *,
    auth_mode: str = DEFAULT_AUTH_MODE,
    email: str | None = None,
    subject: str | None = None,
    role_codes: Iterable[str] | None = None,
    permissions: Iterable[str] | None = None,
) -> AuthenticatedUser:
    normalized_username = (username or "").strip()
    normalized_email = (email or "").strip().lower() or None
    normalized_subject = (subject or "").strip() or None
    normalized_role_codes = tuple(
        sorted({item.strip().lower() for item in (role_codes or ([role] if role else [])) if item and item.strip()})
    )
    normalized_permissions = frozenset(
        item.strip().lower() for item in (permissions or ()) if item and item.strip()
    )
    if not normalized_username:
        raise HTTPException(status_code=401, detail="Missing authenticated username.")
    if not normalized_role_codes and not normalized_permissions:
        raise HTTPException(status_code=401, detail="Missing authenticated authorization context.")
    return AuthenticatedUser(
        username=normalized_username,
        auth_mode=auth_mode,
        email=normalized_email,
        subject=normalized_subject,
        role_codes=normalized_role_codes,
        permissions=normalized_permissions,
    )


def require_role(user: AuthenticatedUser, allowed_roles: Iterable[str]) -> AuthenticatedUser:
    allowed = {role.strip().lower() for role in allowed_roles}
    if not set(user.role_codes).intersection(allowed):
        raise HTTPException(status_code=403, detail="User role is not allowed to access this resource.")
    return user


def require_permissions(user: AuthenticatedUser, required_permissions: Iterable[str]) -> AuthenticatedUser:
    required = {permission.strip().lower() for permission in required_permissions}
    if not required.issubset(user.permissions):
        raise HTTPException(status_code=403, detail="User is missing required permission.")
    return user


def parse_role_map(raw: str | None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for chunk in (raw or "").split(";"):
        entry = chunk.strip()
        if not entry:
            continue
        key, separator, value = entry.partition("=")
        if not separator:
            raise HTTPException(
                status_code=500,
                detail="AUTH_ROLE_MAP contains an invalid entry. Expected email=role pairs.",
            )
        normalized_key = key.strip().lower()
        normalized_value = value.strip().lower()
        if not normalized_key or not normalized_value:
            raise HTTPException(
                status_code=500,
                detail="AUTH_ROLE_MAP contains a blank identity or role entry.",
            )
        mapping[normalized_key] = normalized_value
    return mapping


def resolve_mapped_role(email: str | None, *, default_role: str, role_map_raw: str | None) -> str:
    normalized_default = (default_role or "").strip().lower()
    if not normalized_default:
        raise HTTPException(status_code=500, detail="AUTH_DEFAULT_ROLE must not be blank.")
    normalized_email = (email or "").strip().lower()
    if normalized_email:
        mapping = parse_role_map(role_map_raw)
        if normalized_email in mapping:
            return mapping[normalized_email]
    return normalized_default


def normalize_identity_header(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if ":" in normalized:
        _, _, suffix = normalized.partition(":")
        candidate = suffix.strip()
        return candidate or None
    return normalized


def validate_email_domain(email: str | None, allowed_domain: str | None) -> None:
    normalized_domain = (allowed_domain or "").strip().lower().lstrip("@")
    if not normalized_domain:
        return
    normalized_email = (email or "").strip().lower()
    if not normalized_email.endswith(f"@{normalized_domain}"):
        raise HTTPException(
            status_code=403,
            detail="Authenticated email is outside the configured Google Cloud identity domain.",
        )


def _verify_iap_jwt_assertion(assertion: str, expected_audience: str) -> dict[str, Any]:
    try:
        from google.auth.transport.requests import Request as GoogleAuthRequest
        from google.oauth2 import id_token
    except ModuleNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="google-auth is required for AUTH_MODE=google_iap_jwt.",
        ) from exc
    try:
        claims = id_token.verify_token(
            assertion,
            GoogleAuthRequest(),
            audience=expected_audience,
            certs_url=DEFAULT_IAP_CERTS_URL,
        )
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=401, detail="Invalid Google Cloud IAP identity assertion.") from exc
    if not isinstance(claims, dict):
        raise HTTPException(status_code=401, detail="Invalid Google Cloud IAP identity assertion payload.")
    return claims


def _load_database_user(request: Request, *, email: str | None, subject: str | None) -> AuthenticatedUser:
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        if not email and not subject:
            raise HTTPException(status_code=401, detail="Authenticated identity is missing both email and subject.")

        def load_single_match(field_name: str, value: str | None) -> AppUser | None:
            if not value:
                return None
            field = getattr(AppUser, field_name)
            rows = session.scalars(
                select(AppUser).where(
                    AppUser.is_active.is_(True),
                    field == value,
                )
            ).all()
            if len(rows) > 1:
                raise HTTPException(
                    status_code=403,
                    detail=f"Authenticated identity is ambiguously provisioned for {field_name}.",
                )
            return rows[0] if rows else None

        subject_user = load_single_match("external_subject", subject)
        email_user = load_single_match("external_email", email)

        if subject_user is not None and email_user is not None and subject_user.id != email_user.id:
            raise HTTPException(
                status_code=403,
                detail="Authenticated identity claims resolve to different provisioned users.",
            )

        app_user = subject_user or email_user
        if app_user is None:
            raise HTTPException(status_code=403, detail="Authenticated user is not provisioned in application RBAC.")
        if (
            subject_user is not None
            and email is not None
            and app_user.external_email is not None
            and app_user.external_email.strip().lower() != email
        ):
            raise HTTPException(
                status_code=403,
                detail="Authenticated identity email does not match the provisioned subject owner.",
            )

        role_rows = session.execute(
            select(RbacRole.role_code)
            .join(AppUserRole, AppUserRole.rbac_role_id == RbacRole.id)
            .where(AppUserRole.app_user_id == app_user.id)
        ).scalars().all()
        if not role_rows:
            raise HTTPException(status_code=403, detail="Authenticated user has no assigned RBAC role.")

        permission_rows = session.execute(
            select(RbacPermission.permission_code)
            .join(RbacRolePermission, RbacRolePermission.rbac_permission_id == RbacPermission.id)
            .join(RbacRole, RbacRole.id == RbacRolePermission.rbac_role_id)
            .join(AppUserRole, AppUserRole.rbac_role_id == RbacRole.id)
            .where(AppUserRole.app_user_id == app_user.id)
        ).scalars().all()
        derived_permissions = set(permission_rows)
        for role_code in role_rows:
            derived_permissions.update(ROLE_PERMISSIONS.get(role_code, frozenset()))
        return build_authenticated_user(
            app_user.username,
            auth_mode="google_iap_jwt",
            email=email,
            subject=subject,
            role_codes=role_rows,
            permissions=derived_permissions,
        )
    finally:
        session.close()


def authenticate_google_iap_request(request: Request, *, verifier: Any | None = None) -> AuthenticatedUser:
    config = request.app.state.config
    expected_audience = config.auth_iap_expected_audience.strip()
    if not expected_audience:
        raise HTTPException(status_code=500, detail="AUTH_IAP_EXPECTED_AUDIENCE must be configured.")

    assertion = (request.headers.get(IAP_JWT_HEADER) or "").strip()
    claims: dict[str, Any] | None = None
    if assertion:
        verification_fn = verifier or _verify_iap_jwt_assertion
        claims = verification_fn(assertion, expected_audience)
    elif not config.auth_trusted_header_fallback:
        raise HTTPException(status_code=401, detail="Missing Google Cloud IAP identity assertion.")

    if claims is not None:
        email = str(claims.get("email") or "").strip().lower() or None
        subject = str(claims.get("sub") or "").strip() or None
    else:
        email = normalize_identity_header(request.headers.get(IAP_EMAIL_HEADER))
        subject = normalize_identity_header(request.headers.get(IAP_SUBJECT_HEADER))

    validate_email_domain(email, config.auth_iap_allowed_email_domain)
    role_source = request.app.state.config.auth_role_source.strip().lower()
    if role_source == "database":
        return _load_database_user(request, email=email, subject=subject)
    if role_source != "env_map":
        raise HTTPException(status_code=500, detail=f"Unsupported AUTH_ROLE_SOURCE: {request.app.state.config.auth_role_source}")
    role = resolve_mapped_role(
        email,
        default_role=config.auth_default_role,
        role_map_raw=config.auth_role_map,
    )
    permissions = ROLE_PERMISSIONS.get(role, frozenset())
    username = email or subject
    return build_authenticated_user(
        username,
        role,
        auth_mode="google_iap_jwt",
        email=email,
        subject=subject,
        permissions=permissions,
    )


def get_authenticated_user(request: Request) -> AuthenticatedUser:
    auth_mode = request.app.state.config.auth_mode.strip().lower()
    if auth_mode == "header_stub":
        role = request.headers.get("X-Auth-Role")
        permissions = ROLE_PERMISSIONS.get((role or "").strip().lower(), frozenset())
        return build_authenticated_user(
            request.headers.get("X-Auth-User"),
            role,
            auth_mode="header_stub",
            permissions=permissions,
        )
    if auth_mode == "google_iap_jwt":
        return authenticate_google_iap_request(request)
    raise HTTPException(status_code=500, detail=f"Unsupported AUTH_MODE: {request.app.state.config.auth_mode}")
