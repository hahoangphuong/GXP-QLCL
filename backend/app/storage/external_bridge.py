from __future__ import annotations

from contextlib import contextmanager
import http.client
import json
import tempfile
from typing import Any, BinaryIO, Callable, Iterator
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from backend.app.storage.bridge_auth import (
    BRIDGE_AUTH_MODE_GOOGLE_OIDC,
    BRIDGE_AUTH_MODE_HMAC_JWT,
    BridgeAuthConfig,
    issue_bridge_token,
)
from backend.app.storage.types import (
    ExternalBridgeStorageConfig,
    StorageEntry,
    StorageOperationError,
    StorageResolution,
)


class ExternalBridgeStorageService:
    def __init__(
        self,
        config: ExternalBridgeStorageConfig,
        *,
        token_provider: Callable[[str], str] | None = None,
        chunk_size: int = 1024 * 1024,
        max_upload_bytes: int = 64 * 1024 * 1024,
    ):
        self.config = config
        self._token_provider = token_provider
        self._chunk_size = chunk_size
        self._max_upload_bytes = max_upload_bytes

    def _build_url(self, path: str, *, query: dict[str, str] | None = None) -> str:
        base = self.config.base_url.rstrip("/")
        suffix = path if path.startswith("/") else f"/{path}"
        if not query:
            return f"{base}{suffix}"
        encoded = urllib_parse.urlencode(query)
        return f"{base}{suffix}?{encoded}"

    def _build_headers(self, *, content_type: str | None = "application/json") -> dict[str, str]:
        headers: dict[str, str] = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        if self.config.auth_audience:
            token = self._fetch_bearer_token()
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _fetch_bearer_token(self) -> str:
        audience = (self.config.auth_audience or "").strip()
        if not audience:
            raise StorageOperationError("external_bridge auth_audience must not be blank when auth is enabled.")
        if self._token_provider is not None:
            return self._token_provider(audience)
        auth_mode = self.config.auth_mode.strip().lower()
        if auth_mode == BRIDGE_AUTH_MODE_HMAC_JWT:
            if not self.config.auth_client_id or not self.config.auth_token_issuer or not self.config.auth_signing_key:
                raise StorageOperationError("external_bridge HMAC auth config is incomplete.")
            return issue_bridge_token(
                BridgeAuthConfig(
                    mode=BRIDGE_AUTH_MODE_HMAC_JWT,
                    audience=audience,
                    client_id=self.config.auth_client_id,
                    issuer=self.config.auth_token_issuer,
                    signing_key=self.config.auth_signing_key,
                )
            )
        if auth_mode != BRIDGE_AUTH_MODE_GOOGLE_OIDC:
            raise StorageOperationError(f"Unsupported external_bridge auth_mode: {self.config.auth_mode!r}.")
        try:
            from google.auth.transport.requests import Request as GoogleAuthRequest
            from google.oauth2 import id_token
        except (ModuleNotFoundError, ImportError) as exc:
            raise StorageOperationError(
                "google-auth and requests are required to call external_bridge storage with service-to-service authentication."
            ) from exc
        return id_token.fetch_id_token(GoogleAuthRequest(), audience)

    def _perform_request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        raw_body: bytes | None = None,
        content_type: str | None = "application/json",
    ):
        body: bytes | None = raw_body
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib_request.Request(
            self._build_url(path, query=query),
            data=body,
            method=method,
            headers=self._build_headers(content_type=content_type),
        )
        try:
            return urllib_request.urlopen(req)
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise StorageOperationError(f"external_bridge request failed: {exc.code} {detail}".strip()) from exc
        except urllib_error.URLError as exc:
            raise StorageOperationError(f"external_bridge request failed: {exc.reason}") from exc

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        with self._perform_request(method, path, query=query, payload=payload) as response:
            return json.loads(response.read().decode("utf-8"))

    def _storage_entry_from_payload(self, payload: dict[str, Any]) -> StorageEntry:
        return StorageEntry(
            relative_path=str(payload["relative_path"]),
            name=str(payload["name"]),
            is_dir=bool(payload["is_dir"]),
            size=None if payload.get("size") is None else int(payload["size"]),
        )

    def _storage_resolution_from_payload(self, payload: dict[str, Any]) -> StorageResolution:
        from backend.app.db.enums import StorageResolutionStatus

        return StorageResolution(
            status=StorageResolutionStatus(str(payload["status"])),
            relative_path=payload.get("relative_path"),
            absolute_path=None,
            candidate_count=int(payload["candidate_count"]),
            detail=payload.get("detail"),
        )

    def resolve_inspection_folder(
        self,
        *,
        case_id: str | None = None,
        year: int,
        site_legacy_id: int,
        inspection_legacy_code: str,
    ) -> StorageResolution:
        payload = self._request_json(
            "POST",
            "/bridge/storage/inspection-folder/resolve",
            payload={
                "case_id": case_id,
                "year": year,
                "site_legacy_id": site_legacy_id,
                "inspection_legacy_code": inspection_legacy_code,
            },
        )
        return self._storage_resolution_from_payload(payload)

    def resolve_dkkd_folder(
        self,
        *,
        case_id: str | None = None,
        site_legacy_id: int,
    ) -> StorageResolution:
        payload = self._request_json(
            "POST",
            "/bridge/storage/dkkd-folder/resolve",
            payload={"case_id": case_id, "site_legacy_id": site_legacy_id},
        )
        return self._storage_resolution_from_payload(payload)

    def list(self, relative_path: str = "", *, root: str = "inspection") -> list[StorageEntry]:
        payload = self._request_json(
            "GET",
            "/bridge/storage/list",
            query={"root": root, "relative_path": relative_path},
        )
        return [self._storage_entry_from_payload(item) for item in payload]

    def stat(self, relative_path: str, *, root: str = "inspection") -> StorageEntry:
        payload = self._request_json(
            "GET",
            "/bridge/storage/stat",
            query={"root": root, "relative_path": relative_path},
        )
        return self._storage_entry_from_payload(payload)

    def exists(self, relative_path: str, *, root: str = "inspection") -> bool:
        payload = self._request_json(
            "GET",
            "/bridge/storage/exists",
            query={"root": root, "relative_path": relative_path},
        )
        return bool(payload["exists"])

    @contextmanager
    def read_stream(self, relative_path: str, *, root: str = "inspection") -> Iterator[BinaryIO]:
        with self._perform_request(
            "GET",
            "/bridge/storage/read",
            query={"root": root, "relative_path": relative_path},
            content_type=None,
        ) as response:
            yield response

    def write_stream(self, relative_path: str, stream: BinaryIO, *, root: str = "inspection") -> StorageEntry:
        parsed = urllib_parse.urlparse(
            self._build_url(
                "/bridge/storage/write",
                query={"root": root, "relative_path": relative_path},
            )
        )
        with tempfile.SpooledTemporaryFile(max_size=self._chunk_size) as spool:
            total_bytes = 0
            while True:
                chunk = stream.read(self._chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > self._max_upload_bytes:
                    raise StorageOperationError("external_bridge upload exceeds configured max_upload_bytes.")
                spool.write(chunk)
            spool.seek(0)
            connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
            connection = connection_cls(parsed.hostname, parsed.port, timeout=60)
            try:
                path = parsed.path
                if parsed.query:
                    path = f"{path}?{parsed.query}"
                headers = self._build_headers(content_type="application/octet-stream")
                headers["Content-Length"] = str(total_bytes)
                connection.putrequest("POST", path)
                for key, value in headers.items():
                    connection.putheader(key, value)
                connection.endheaders()
                while True:
                    chunk = spool.read(self._chunk_size)
                    if not chunk:
                        break
                    connection.send(chunk)
                response = connection.getresponse()
                payload = response.read().decode("utf-8", errors="replace")
                if response.status >= 400:
                    raise StorageOperationError(
                        f"external_bridge request failed: {response.status} {payload}".strip()
                    )
                return self._storage_entry_from_payload(json.loads(payload))
            finally:
                connection.close()

    def create_folder(self, relative_path: str, *, root: str = "inspection") -> StorageEntry:
        payload = self._request_json(
            "POST",
            "/bridge/storage/create-folder",
            payload={"root": root, "relative_path": relative_path},
        )
        return self._storage_entry_from_payload(payload)

    def copy(self, source_relative_path: str, target_relative_path: str, *, root: str = "inspection") -> StorageEntry:
        payload = self._request_json(
            "POST",
            "/bridge/storage/copy",
            payload={
                "root": root,
                "source_relative_path": source_relative_path,
                "target_relative_path": target_relative_path,
            },
        )
        return self._storage_entry_from_payload(payload)

    def move(self, source_relative_path: str, target_relative_path: str, *, root: str = "inspection") -> StorageEntry:
        payload = self._request_json(
            "POST",
            "/bridge/storage/move",
            payload={
                "root": root,
                "source_relative_path": source_relative_path,
                "target_relative_path": target_relative_path,
            },
        )
        return self._storage_entry_from_payload(payload)

    def rename(self, source_relative_path: str, new_name: str, *, root: str = "inspection") -> StorageEntry:
        payload = self._request_json(
            "POST",
            "/bridge/storage/rename",
            payload={"root": root, "source_relative_path": source_relative_path, "new_name": new_name},
        )
        return self._storage_entry_from_payload(payload)

    def checksum(self, relative_path: str, *, root: str = "inspection") -> str:
        payload = self._request_json(
            "GET",
            "/bridge/storage/checksum",
            query={"root": root, "relative_path": relative_path},
        )
        return str(payload["checksum_sha256"])
