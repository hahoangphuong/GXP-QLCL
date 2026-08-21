from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

import os
import tempfile

from backend.app.storage.bridge_auth import load_bridge_auth_config, require_bridge_request_auth
from backend.app.storage import ExternalBridgeStorageService, FilesystemStorageService, create_storage_service_from_env
from backend.app.storage.socket_proxy import enable_socket_proxy_from_env
from backend.app.storage.types import StorageEntry, StorageOperationError, StorageResolution


def _entry_payload(entry: StorageEntry) -> dict[str, object]:
    return {
        "relative_path": entry.relative_path,
        "name": entry.name,
        "is_dir": entry.is_dir,
        "size": entry.size,
    }


def _resolution_payload(resolution: StorageResolution) -> dict[str, object]:
    return {
        "status": resolution.status.value,
        "relative_path": resolution.relative_path,
        "candidate_count": resolution.candidate_count,
        "detail": resolution.detail,
    }


def create_storage_bridge_app(storage_service: FilesystemStorageService | None = None) -> FastAPI:
    app = FastAPI(title="GxP Storage Bridge")
    resolved_storage = storage_service
    storage_error: str | None = None
    if resolved_storage is None:
        try:
            enable_socket_proxy_from_env()
            resolved_storage = create_storage_service_from_env()
        except StorageOperationError as exc:
            storage_error = str(exc)
        except RuntimeError as exc:
            storage_error = str(exc)
    if isinstance(resolved_storage, ExternalBridgeStorageService):
        storage_error = "Storage bridge runtime must use a filesystem-backed storage adapter, not external_bridge_http."
        resolved_storage = None
    app.state.storage_service = resolved_storage
    app.state.storage_error = storage_error
    app.state.max_upload_bytes = max(
        1,
        int((os.environ.get("STORAGE_BRIDGE_MAX_UPLOAD_BYTES", "67108864") or "67108864").strip()),
    )
    try:
        app.state.bridge_auth_config = load_bridge_auth_config()
    except RuntimeError as exc:
        app.state.bridge_auth_config = None
        if storage_error is None:
            storage_error = str(exc)
        app.state.storage_error = storage_error

    def get_storage(request: Request) -> FilesystemStorageService:
        service = getattr(request.app.state, "storage_service", None)
        if service is None:
            detail = getattr(request.app.state, "storage_error", None) or "Storage bridge is not configured."
            raise HTTPException(status_code=503, detail=detail)
        return service

    def raise_http_error(exc: Exception) -> None:
        if isinstance(exc, FileNotFoundError):
            raise HTTPException(status_code=404, detail="Storage target not found.") from exc
        if isinstance(exc, StorageOperationError):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise exc

    @app.get("/healthz")
    def healthz():
        return {
            "ok": True,
            "service": "storage_bridge",
            "storage_configured": app.state.storage_service is not None,
            "auth_configured": app.state.bridge_auth_config is not None,
        }

    @app.get("/readyz")
    def readyz():
        if app.state.storage_service is None:
            raise HTTPException(status_code=503, detail=app.state.storage_error or "Storage bridge is not configured.")
        if app.state.bridge_auth_config is None:
            raise HTTPException(status_code=503, detail="Storage bridge auth is not configured.")
        try:
            app.state.storage_service.list("", root="inspection")
        except Exception as exc:  # pragma: no cover
            raise_http_error(exc)
        return {
            "ok": True,
            "service": "storage_bridge",
            "inspection_root_ready": True,
        }

    @app.post("/bridge/storage/inspection-folder/resolve")
    def resolve_inspection_folder(
        payload: dict = Body(...),
        storage: FilesystemStorageService = Depends(get_storage),
        _claims: dict = Depends(require_bridge_request_auth),
    ):
        try:
            resolution = storage.resolve_inspection_folder(
                case_id=payload.get("case_id"),
                year=int(payload["year"]),
                site_legacy_id=int(payload["site_legacy_id"]),
                inspection_legacy_code=str(payload["inspection_legacy_code"]),
            )
            return _resolution_payload(resolution)
        except Exception as exc:  # pragma: no cover
            raise_http_error(exc)

    @app.post("/bridge/storage/dkkd-folder/resolve")
    def resolve_dkkd_folder(
        payload: dict = Body(...),
        storage: FilesystemStorageService = Depends(get_storage),
        _claims: dict = Depends(require_bridge_request_auth),
    ):
        try:
            resolution = storage.resolve_dkkd_folder(
                case_id=payload.get("case_id"),
                site_legacy_id=int(payload["site_legacy_id"]),
            )
            return _resolution_payload(resolution)
        except Exception as exc:  # pragma: no cover
            raise_http_error(exc)

    @app.get("/bridge/storage/list")
    def list_entries(
        root: str = Query("inspection"),
        relative_path: str = Query(""),
        storage: FilesystemStorageService = Depends(get_storage),
        _claims: dict = Depends(require_bridge_request_auth),
    ):
        try:
            return [_entry_payload(item) for item in storage.list(relative_path, root=root)]
        except Exception as exc:  # pragma: no cover
            raise_http_error(exc)

    @app.get("/bridge/storage/stat")
    def stat_entry(
        root: str = Query("inspection"),
        relative_path: str = Query(...),
        storage: FilesystemStorageService = Depends(get_storage),
        _claims: dict = Depends(require_bridge_request_auth),
    ):
        try:
            return _entry_payload(storage.stat(relative_path, root=root))
        except Exception as exc:  # pragma: no cover
            raise_http_error(exc)

    @app.get("/bridge/storage/exists")
    def exists_entry(
        root: str = Query("inspection"),
        relative_path: str = Query(...),
        storage: FilesystemStorageService = Depends(get_storage),
        _claims: dict = Depends(require_bridge_request_auth),
    ):
        try:
            return {"exists": storage.exists(relative_path, root=root)}
        except Exception as exc:  # pragma: no cover
            raise_http_error(exc)

    @app.get("/bridge/storage/read")
    def read_entry(
        root: str = Query("inspection"),
        relative_path: str = Query(...),
        storage: FilesystemStorageService = Depends(get_storage),
        _claims: dict = Depends(require_bridge_request_auth),
    ):
        try:
            def iterator():
                with storage.read_stream(relative_path, root=root) as stream:
                    while True:
                        chunk = stream.read(1024 * 1024)
                        if not chunk:
                            break
                        yield chunk

            return StreamingResponse(iterator(), media_type="application/octet-stream")
        except Exception as exc:  # pragma: no cover
            raise_http_error(exc)

    @app.post("/bridge/storage/write")
    async def write_entry(
        request: Request,
        root: str = Query("inspection"),
        relative_path: str = Query(...),
        storage: FilesystemStorageService = Depends(get_storage),
        _claims: dict = Depends(require_bridge_request_auth),
    ):
        try:
            @asynccontextmanager
            async def request_stream():
                tmp = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)
                total_bytes = 0
                try:
                    async for chunk in request.stream():
                        if not chunk:
                            continue
                        total_bytes += len(chunk)
                        if total_bytes > request.app.state.max_upload_bytes:
                            raise HTTPException(status_code=413, detail="Upload exceeds STORAGE_BRIDGE_MAX_UPLOAD_BYTES.")
                        tmp.write(chunk)
                    tmp.seek(0)
                    yield tmp
                finally:
                    tmp.close()

            async with request_stream() as stream:
                entry = storage.write_stream(relative_path, stream, root=root)
            return _entry_payload(entry)
        except Exception as exc:  # pragma: no cover
            raise_http_error(exc)

    @app.post("/bridge/storage/create-folder")
    def create_folder(
        payload: dict = Body(...),
        storage: FilesystemStorageService = Depends(get_storage),
        _claims: dict = Depends(require_bridge_request_auth),
    ):
        try:
            entry = storage.create_folder(str(payload["relative_path"]), root=str(payload["root"]))
            return _entry_payload(entry)
        except Exception as exc:  # pragma: no cover
            raise_http_error(exc)

    @app.post("/bridge/storage/copy")
    def copy_entry(
        payload: dict = Body(...),
        storage: FilesystemStorageService = Depends(get_storage),
        _claims: dict = Depends(require_bridge_request_auth),
    ):
        try:
            entry = storage.copy(
                str(payload["source_relative_path"]),
                str(payload["target_relative_path"]),
                root=str(payload["root"]),
            )
            return _entry_payload(entry)
        except Exception as exc:  # pragma: no cover
            raise_http_error(exc)

    @app.post("/bridge/storage/move")
    def move_entry(
        payload: dict = Body(...),
        storage: FilesystemStorageService = Depends(get_storage),
        _claims: dict = Depends(require_bridge_request_auth),
    ):
        try:
            entry = storage.move(
                str(payload["source_relative_path"]),
                str(payload["target_relative_path"]),
                root=str(payload["root"]),
            )
            return _entry_payload(entry)
        except Exception as exc:  # pragma: no cover
            raise_http_error(exc)

    @app.post("/bridge/storage/rename")
    def rename_entry(
        payload: dict = Body(...),
        storage: FilesystemStorageService = Depends(get_storage),
        _claims: dict = Depends(require_bridge_request_auth),
    ):
        try:
            entry = storage.rename(
                str(payload["source_relative_path"]),
                str(payload["new_name"]),
                root=str(payload["root"]),
            )
            return _entry_payload(entry)
        except Exception as exc:  # pragma: no cover
            raise_http_error(exc)

    @app.get("/bridge/storage/checksum")
    def checksum_entry(
        root: str = Query("inspection"),
        relative_path: str = Query(...),
        storage: FilesystemStorageService = Depends(get_storage),
        _claims: dict = Depends(require_bridge_request_auth),
    ):
        try:
            return {"checksum_sha256": storage.checksum(relative_path, root=root)}
        except Exception as exc:  # pragma: no cover
            raise_http_error(exc)

    return app


app = create_storage_bridge_app()
