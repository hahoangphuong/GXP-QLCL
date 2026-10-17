from __future__ import annotations

from fastapi import Depends, Request

from backend.app.auth import AuthenticatedUser, get_authenticated_user, require_permissions
from backend.app.status import build_application_status


def _build_status_payload(request: Request, *, include_internal: bool):
    """Expose internal deployment identifiers only after admin.users authorization."""
    return {
        "app_name": request.app.state.config.app_name,
        "app_mode": request.app.state.config.app_mode,
        "deployment_platform": request.app.state.config.deployment_platform,
        "frontend_topology": request.app.state.config.frontend_topology,
        "auth_mode": request.app.state.config.auth_mode,
        "auth": {
            "mode": request.app.state.config.auth_mode,
            "oidc_client_id": request.app.state.config.auth_oidc_client_id or None,
            "allowed_email_domain": request.app.state.config.auth_iap_allowed_email_domain or None,
        },
        "deployment": {
            "git_sha": request.app.state.config.deployment_git_sha or None,
            "git_short_sha": request.app.state.config.deployment_git_short_sha or None,
            "branch": request.app.state.config.deployment_branch or None,
            "image_uri": (request.app.state.config.deployment_image_uri or None) if include_internal else None,
            "deployed_at_utc": request.app.state.config.deployment_timestamp_utc or None,
            "cloud_run_service_name": (request.app.state.config.cloud_run_service_name or None) if include_internal else None,
            "db_name": (request.app.state.config.db_name or None) if include_internal else None,
            "db_user": (request.app.state.config.db_user or None) if include_internal else None,
        },
        "phases": build_application_status(),
    }


def app_status(request: Request):
    return _build_status_payload(request, include_internal=False)


def admin_system_status(
    request: Request,
    user: AuthenticatedUser = Depends(get_authenticated_user),
):
    require_permissions(user, {"admin.users"})
    return _build_status_payload(request, include_internal=True)


def register_status_routes(app) -> None:
    app.add_api_route("/app/status", app_status, methods=["GET"], tags=["status"])
    app.add_api_route("/admin/runtime-status", admin_system_status, methods=["GET"], tags=["admin"])
