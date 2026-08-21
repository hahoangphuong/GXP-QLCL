from __future__ import annotations

from fastapi import Request

from backend.app.status import build_application_status


def app_status(request: Request):
    return {
        "app_name": request.app.state.config.app_name,
        "app_mode": request.app.state.config.app_mode,
        "deployment_platform": request.app.state.config.deployment_platform,
        "frontend_topology": request.app.state.config.frontend_topology,
        "auth_mode": request.app.state.config.auth_mode,
        "deployment": {
            "git_sha": request.app.state.config.deployment_git_sha or None,
            "git_short_sha": request.app.state.config.deployment_git_short_sha or None,
            "branch": request.app.state.config.deployment_branch or None,
            "image_uri": request.app.state.config.deployment_image_uri or None,
            "deployed_at_utc": request.app.state.config.deployment_timestamp_utc or None,
            "cloud_run_service_name": request.app.state.config.cloud_run_service_name or None,
            "db_name": request.app.state.config.db_name or None,
            "db_user": request.app.state.config.db_user or None,
        },
        "phases": build_application_status(),
    }


def register_status_routes(app) -> None:
    app.add_api_route("/app/status", app_status, methods=["GET"], tags=["status"])
