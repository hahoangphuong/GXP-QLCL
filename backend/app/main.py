from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

from backend.app.api import include_api_routes
from backend.app.api.routers.catalog import register_catalog_routes
from backend.app.api.routers.document import register_document_routes
from backend.app.api.routers.storage import register_storage_routes
from backend.app.api.routers.workflow import register_workflow_routes
from backend.app.config import load_app_config, validate_runtime_config
from backend.app.db.session import build_session_factory
from backend.app.project_paths import frontend_dist_root
from backend.app.storage import (
    LocalStorageService,
    StorageBindingLookupService,
    StorageOperationError,
    create_storage_service_from_env,
)


REQUEST_LOGGER = logging.getLogger("gxp.request")


def _frontend_file_response(static_root: Path, relative_path: str) -> FileResponse:
    candidate = (static_root / relative_path).resolve()
    try:
        candidate.relative_to(static_root.resolve())
    except ValueError as exc:
        raise FileNotFoundError(relative_path) from exc
    if not candidate.is_file():
        raise FileNotFoundError(relative_path)
    return FileResponse(candidate)


def register_frontend_routes(app: FastAPI) -> None:
    static_root = frontend_dist_root()
    assets_root = static_root / "assets"
    if not static_root.exists():
        return
    if assets_root.exists():
        app.mount("/assets", StaticFiles(directory=assets_root), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def frontend_index():
        return FileResponse(static_root / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend_spa(full_path: str):
        if not full_path or full_path.startswith(("openapi", "docs", "redoc")):
            return FileResponse(static_root / "index.html")
        try:
            return _frontend_file_response(static_root, full_path)
        except FileNotFoundError:
            return FileResponse(static_root / "index.html")


def create_app(
    database_url: str | None = None,
    *,
    storage_service: LocalStorageService | None = None,
    storage_env: dict[str, str] | None = None,
    app_env: dict[str, str] | None = None,
) -> FastAPI:
    config = load_app_config(app_env)
    resolved_database_url = database_url or config.database_url
    app = FastAPI(title=config.app_name)
    session_factory = build_session_factory(resolved_database_url)
    resolved_storage_service = storage_service
    storage_error: str | None = None
    if resolved_storage_service is None:
        try:
            resolved_storage_service = create_storage_service_from_env(storage_env)
        except StorageOperationError as exc:
            storage_error = str(exc)
    validate_runtime_config(
        config,
        database_url=resolved_database_url,
        storage_service=resolved_storage_service,
        storage_error=storage_error,
    )
    app.state.config = config
    app.state.session_factory = session_factory
    app.state.storage_service = resolved_storage_service
    app.state.storage_lookup_service = (
        StorageBindingLookupService(resolved_storage_service) if resolved_storage_service is not None else None
    )
    app.state.storage_error = storage_error
    include_api_routes(app)
    register_catalog_routes(app, session_factory)
    register_storage_routes(app, session_factory)
    register_workflow_routes(app, session_factory)
    register_document_routes(app, session_factory)
    register_frontend_routes(app)

    @app.middleware("http")
    async def request_context_middleware(request, call_next):
        request_id = (request.headers.get("X-Request-Id") or "").strip() or str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        REQUEST_LOGGER.info(
            json.dumps(
                {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "deployment_git_sha": app.state.config.deployment_git_sha or None,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return response
    return app


app = create_app()
