from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from backend.app.runtime_schema import expected_alembic_head_revision


def healthz(request: Request):
    return {
        "ok": True,
        "mode": request.app.state.config.app_mode,
        "deployment_platform": request.app.state.config.deployment_platform,
        "storage_configured": request.app.state.storage_service is not None,
        "frontend_topology": request.app.state.config.frontend_topology,
        "deployment_git_sha": request.app.state.config.deployment_git_sha or None,
    }


def readyz(request: Request):
    expected_revision = expected_alembic_head_revision()
    schema_current = False
    database_reachable = False
    database_error: str | None = None
    actual_revision: str | None = None

    session_factory = request.app.state.session_factory
    try:
        with session_factory() as session:
            session.execute(text("SELECT 1"))
            database_reachable = True
            try:
                actual_revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            except Exception as exc:
                database_error = f"alembic_version unavailable: {exc}"
            else:
                schema_current = expected_revision is not None and actual_revision == expected_revision
    except Exception as exc:
        database_error = str(exc)

    payload = {
        "ok": database_reachable and schema_current,
        "database_reachable": database_reachable,
        "schema_current": schema_current,
        "expected_revision": expected_revision,
        "actual_revision": actual_revision,
        "storage_configured": request.app.state.storage_service is not None,
        "frontend_topology": request.app.state.config.frontend_topology,
        "deployment_git_sha": request.app.state.config.deployment_git_sha or None,
        "database_error": database_error,
    }
    return JSONResponse(payload, status_code=200 if payload["ok"] else 503)


def register_health_routes(app) -> None:
    app.add_api_route("/healthz", healthz, methods=["GET"], tags=["health"])
    app.add_api_route("/readyz", readyz, methods=["GET"], tags=["health"])
