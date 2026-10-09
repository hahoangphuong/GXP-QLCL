from __future__ import annotations

import asyncio
import base64
from contextlib import contextmanager
import hashlib
import hmac
from io import BytesIO
import json
from pathlib import Path
import tempfile
import time
from urllib.parse import urlencode

import pytest

from fastapi import HTTPException

from backend.app.storage.bridge_auth import (
    BRIDGE_AUTH_MODE_GOOGLE_OIDC,
    BRIDGE_AUTH_MODE_HMAC_JWT,
    issue_bridge_token,
    load_bridge_auth_config,
    require_bridge_request_auth,
    verify_bridge_hmac_token,
    verify_google_oidc_token,
)
from backend.app.storage.external_bridge import ExternalBridgeStorageService
from backend.app.storage.filesystem import FilesystemStorageService
from backend.app.storage.types import (
    ExternalBridgeStorageConfig,
    StorageConfig,
    StorageEntry,
    StorageTargetExistsError,
)
from backend.storage_bridge_main import create_storage_bridge_app


class _FakeHttpResponse:
    def __init__(self, payload: bytes, *, status: int = 200):
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return self._payload


class _FakeHttpConnection:
    last_instance: "_FakeHttpConnection | None" = None

    def __init__(self, host, port=None, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.headers = {}
        self.path = None
        self.sent_chunks: list[bytes] = []
        _FakeHttpConnection.last_instance = self

    def putrequest(self, method, path):
        self.method = method
        self.path = path

    def putheader(self, key, value):
        self.headers[key] = value

    def endheaders(self):
        return None

    def send(self, chunk: bytes):
        self.sent_chunks.append(chunk)

    def getresponse(self):
        return _FakeHttpResponse(
            json.dumps(
                {
                    "relative_path": "2026/demo.bin",
                    "name": "demo.bin",
                    "is_dir": False,
                    "size": sum(len(item) for item in self.sent_chunks),
                }
            ).encode("utf-8")
        )

    def close(self):
        return None


class _TrackingStream(BytesIO):
    def __init__(self, payload: bytes, *, fail_after_reads: int | None = None):
        super().__init__(payload)
        self.closed_flag = False
        self.read_calls = 0
        self.fail_after_reads = fail_after_reads

    def read(self, size: int = -1) -> bytes:
        self.read_calls += 1
        if self.fail_after_reads is not None and self.read_calls > self.fail_after_reads:
            raise RuntimeError("simulated read failure")
        return super().read(size)

    def close(self):
        self.closed_flag = True
        super().close()


class _BridgeStorageHarness:
    def __init__(self, files: dict[str, bytes], *, fail_after_reads: int | None = None):
        self.config = StorageConfig(
            inspection_root=Path("."),
            dkkd_root=None,
            template_root=None,
            storage_class="local_filesystem_test",
        )
        self.files = files
        self.fail_after_reads = fail_after_reads
        self.last_stream: _TrackingStream | None = None

    def write_stream(
        self,
        relative_path: str,
        stream,
        *,
        root: str = "inspection",
        overwrite: bool = True,
    ) -> StorageEntry:
        if not overwrite and relative_path in self.files:
            raise StorageTargetExistsError(
                f"Storage target already exists and will not be overwritten: {relative_path!r}."
            )
        payload = stream.read()
        self.files[relative_path] = payload
        return StorageEntry(
            relative_path=relative_path,
            name=Path(relative_path).name,
            is_dir=False,
            size=len(payload),
        )

    def delete(self, relative_path: str, *, root: str = "inspection") -> None:
        del self.files[relative_path]

    @contextmanager
    def read_stream(self, relative_path: str, *, root: str = "inspection"):
        payload = self.files[relative_path]
        stream = _TrackingStream(payload, fail_after_reads=self.fail_after_reads)
        self.last_stream = stream
        try:
            yield stream
        finally:
            stream.close()


async def _invoke_asgi(app, *, method: str, path: str, headers: dict[str, str] | None = None, body: bytes = b""):
    raw_headers = [
        (key.lower().encode("ascii"), value.encode("utf-8"))
        for key, value in (headers or {}).items()
    ]
    messages: list[dict[str, object]] = []
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            await asyncio.sleep(0)
            return {"type": "http.request", "body": b"", "more_body": False}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path.split("?", 1)[0],
        "raw_path": path.split("?", 1)[0].encode("ascii"),
        "query_string": path.split("?", 1)[1].encode("ascii") if "?" in path else b"",
        "headers": raw_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    await app(scope, receive, send)
    return messages


def _body_from_messages(messages: list[dict[str, object]]) -> bytes:
    chunks: list[bytes] = []
    for message in messages:
        if message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))
    return b"".join(chunks)


def _status_from_messages(messages: list[dict[str, object]]) -> int:
    for message in messages:
        if message["type"] == "http.response.start":
            return int(message["status"])
    raise AssertionError("Missing response start")


def _authorized_headers(monkeypatch) -> dict[str, str]:
    monkeypatch.setenv("BRIDGE_AUTH_MODE", "hmac_jwt")
    monkeypatch.setenv("STORAGE_BRIDGE_SIGNING_KEY", "super-secret-signing-key")
    monkeypatch.setenv("STORAGE_BRIDGE_TOKEN_ISSUER", "gxp-web-api")
    monkeypatch.setenv("STORAGE_BRIDGE_AUTH_AUDIENCE", "storage-bridge")
    monkeypatch.setenv("STORAGE_BRIDGE_CLIENT_ID", "gxp-web-api")
    token = issue_bridge_token(load_bridge_auth_config())
    return {"Authorization": f"Bearer {token}"}


def test_bridge_auth_token_roundtrip(monkeypatch):
    headers = _authorized_headers(monkeypatch)
    assert headers["Authorization"].startswith("Bearer ")
    config = load_bridge_auth_config()
    claims = verify_bridge_hmac_token(headers["Authorization"][7:], config)

    assert claims["iss"] == "gxp-web-api"
    assert claims["aud"] == "storage-bridge"


def _sign_test_bridge_token(config, header, payload):
    """Build deliberately invalid but correctly signed tokens for verifier tests."""
    def encode(value):
        if isinstance(value, bytes):
            data = value
        else:
            data = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    signing_input = f"{encode(header)}.{encode(payload)}"
    signature = hmac.new(config.signing_key.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{encode(signature)}"


@pytest.mark.parametrize("token", [
    "", "a.b", "a.b.c.d", "a.b.%",
    "😀.abc.def", "abc.def.==", "abc.def./",
    "a" * 8193,
])
def test_bridge_hmac_malformed_untrusted_tokens_return_401_not_server_errors(monkeypatch, token):
    _authorized_headers(monkeypatch)
    with pytest.raises(HTTPException) as error:
        verify_bridge_hmac_token(token, load_bridge_auth_config())
    assert error.value.status_code == 401


@pytest.mark.parametrize(("header", "payload"), [
    ({"alg": "none", "typ": "JWT"}, "default"),
    ({"alg": "HS512", "typ": "JWT"}, "default"),
    ({"alg": "HS256", "typ": "other"}, "default"),
    (["HS256", "JWT"], "default"),
    ({"alg": "HS256", "typ": "JWT"}, b"not json"),
    ({"alg": "HS256", "typ": "JWT"}, ["not", "claims"]),
    ({"alg": "HS256", "typ": "JWT"}, None),
])
def test_bridge_hmac_rejects_noncontract_headers_and_payloads(monkeypatch, header, payload):
    _authorized_headers(monkeypatch)
    config = load_bridge_auth_config()
    now = int(time.time())
    claims = {
        "iss": config.issuer, "aud": config.audience, "sub": config.client_id,
        "iat": now, "exp": now + 60,
    }
    token = _sign_test_bridge_token(config, header, claims if payload == "default" else payload)
    with pytest.raises(HTTPException) as error:
        verify_bridge_hmac_token(token, config)
    assert error.value.status_code == 401


@pytest.mark.parametrize(("changes", "reason"), [
    ({"iat": None}, "timestamps"),
    ({"iat": True}, "timestamps"),
    ({"exp": "9999999999"}, "timestamps"),
    ({"exp": 9999999999.0}, "timestamps"),
    ({"iat": 9999999999}, "lifetime"),
    ({"exp": 9999999999}, "lifetime"),
    ({"exp": 0}, "lifetime"),
])
def test_bridge_hmac_rejects_invalid_or_unbounded_lifetime(monkeypatch, changes, reason):
    _authorized_headers(monkeypatch)
    config = load_bridge_auth_config()
    now = int(time.time())
    claims = {
        "iss": config.issuer, "aud": config.audience, "sub": config.client_id,
        "iat": now, "exp": now + 60,
    }
    claims.update(changes)
    token = _sign_test_bridge_token(config, {"alg": "HS256", "typ": "JWT"}, claims)
    with pytest.raises(HTTPException) as error:
        verify_bridge_hmac_token(token, config)
    assert error.value.status_code == 401
    assert reason in str(error.value.detail).lower()


def test_bridge_hmac_rejects_expired_but_well_formed_token(monkeypatch):
    _authorized_headers(monkeypatch)
    config = load_bridge_auth_config()
    now = int(time.time())
    claims = {
        "iss": config.issuer, "aud": config.audience, "sub": config.client_id,
        "iat": now - 120, "exp": now - 60,
    }
    token = _sign_test_bridge_token(config, {"alg": "HS256", "typ": "JWT"}, claims)
    with pytest.raises(HTTPException) as error:
        verify_bridge_hmac_token(token, config)
    assert error.value.status_code == 401
    assert "expired" in str(error.value.detail).lower()


def test_bridge_google_oidc_mode_uses_explicit_verifier():
    config = load_bridge_auth_config(
        {
            "BRIDGE_AUTH_MODE": "google_oidc",
            "STORAGE_BRIDGE_AUTH_AUDIENCE": "https://bridge.example",
        }
    )
    claims = verify_google_oidc_token(
        "token",
        config,
        verifier=lambda token, audience: {"sub": "svc-1", "aud": audience, "token": token},
    )

    assert claims["aud"] == "https://bridge.example"
    assert claims["sub"] == "svc-1"


def test_bridge_auth_mode_mismatch_is_rejected(monkeypatch):
    _authorized_headers(monkeypatch)
    config = load_bridge_auth_config()
    try:
        verify_google_oidc_token("token", config, verifier=lambda token, audience: {"aud": audience})
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("Expected mode mismatch to be rejected")


def test_bridge_read_endpoint_streams_and_closes_for_multiple_sizes(monkeypatch):
    headers = _authorized_headers(monkeypatch)
    empty_storage = _BridgeStorageHarness({"empty.bin": b""})
    empty_app = create_storage_bridge_app(empty_storage)
    empty_messages = asyncio.run(
        _invoke_asgi(
            empty_app,
            method="GET",
            path=f"/bridge/storage/read?{urlencode({'root': 'inspection', 'relative_path': 'empty.bin'})}",
            headers=headers,
        )
    )
    assert _status_from_messages(empty_messages) == 200
    assert _body_from_messages(empty_messages) == b""

    payloads = {
        "one-byte.bin": b"x",
        "normal.bin": b"hello world" * 128,
        "large.bin": b"0123456789abcdef" * (1024 * 256),
    }
    for relative_path, payload in payloads.items():
        storage = _BridgeStorageHarness({relative_path: payload})
        app = create_storage_bridge_app(storage)
        messages = asyncio.run(
            _invoke_asgi(
                app,
                method="GET",
                path=f"/bridge/storage/read?{urlencode({'root': 'inspection', 'relative_path': relative_path})}",
                headers=headers,
            )
        )
        assert _status_from_messages(messages) == 200
        assert _body_from_messages(messages) == payload
        assert storage.last_stream is not None
        assert storage.last_stream.closed_flag is True


def test_bridge_read_endpoint_returns_500_and_closes_stream_on_generator_error(monkeypatch):
    headers = _authorized_headers(monkeypatch)
    storage = _BridgeStorageHarness({"broken.bin": b"abcdef"}, fail_after_reads=1)
    app = create_storage_bridge_app(storage)

    messages: list[dict[str, object]] | None = None
    try:
        messages = asyncio.run(
            _invoke_asgi(
                app,
                method="GET",
                path=f"/bridge/storage/read?{urlencode({'root': 'inspection', 'relative_path': 'broken.bin'})}",
                headers=headers,
            )
        )
    except RuntimeError as exc:
        assert "simulated read failure" in str(exc)
    else:
        assert messages is not None
        assert _status_from_messages(messages) == 500

    assert storage.last_stream is not None
    assert storage.last_stream.closed_flag is True


def test_bridge_http_read_rejects_malformed_hmac_token_with_401(monkeypatch):
    _authorized_headers(monkeypatch)
    app = create_storage_bridge_app(_BridgeStorageHarness({"private.bin": b"protected-content"}))
    messages = asyncio.run(
        _invoke_asgi(
            app,
            method="GET",
            path=f"/bridge/storage/read?{urlencode({'root': 'inspection', 'relative_path': 'private.bin'})}",
            headers={"Authorization": "Bearer a.b.%"},
        )
    )
    assert _status_from_messages(messages) == 401
    assert b"protected-content" not in _body_from_messages(messages)


def test_bridge_directory_listing_does_not_expose_outside_symlink_metadata(monkeypatch, tmp_path):
    headers = _authorized_headers(monkeypatch)
    root = tmp_path / "inspection"
    root.mkdir()
    outside = tmp_path / "private-outside.txt"
    outside.write_bytes(b"sensitive-outside-file")
    alias = root / "alias.txt"
    try:
        alias.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symlinks are not available: {exc}")

    app = create_storage_bridge_app(
        FilesystemStorageService(StorageConfig(inspection_root=root))
    )
    messages = asyncio.run(
        _invoke_asgi(
            app,
            method="GET",
            path="/bridge/storage/list?root=inspection",
            headers=headers,
        )
    )
    assert _status_from_messages(messages) == 400
    payload = _body_from_messages(messages)
    assert b"sensitive-outside-file" not in payload
    assert b"private-outside.txt" not in payload
    assert outside.read_bytes() == b"sensitive-outside-file"


def test_bridge_request_auth_rejects_missing_token(monkeypatch):
    monkeypatch.setenv("BRIDGE_AUTH_MODE", "hmac_jwt")
    monkeypatch.setenv("STORAGE_BRIDGE_SIGNING_KEY", "super-secret-signing-key")
    monkeypatch.setenv("STORAGE_BRIDGE_TOKEN_ISSUER", "gxp-web-api")
    monkeypatch.setenv("STORAGE_BRIDGE_AUTH_AUDIENCE", "storage-bridge")
    monkeypatch.setenv("STORAGE_BRIDGE_CLIENT_ID", "gxp-web-api")
    app = create_storage_bridge_app(_BridgeStorageHarness({"x.bin": b"x"}))

    async def run():
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/healthz",
            "raw_path": b"/healthz",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "app": app,
        }
        request = type("Req", (), {"headers": {}, "app": app})()
        return require_bridge_request_auth(request)

    try:
        asyncio.run(run())
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("Expected missing token to be rejected")


def test_bridge_delete_endpoint_removes_file(monkeypatch):
    headers = _authorized_headers(monkeypatch)
    storage = _BridgeStorageHarness({"orphan.bin": b"orphan"})
    app = create_storage_bridge_app(storage)

    messages = asyncio.run(
        _invoke_asgi(
            app,
            method="POST",
            path="/bridge/storage/delete",
            headers={**headers, "content-type": "application/json"},
            body=json.dumps(
                {"root": "inspection", "relative_path": "orphan.bin"}
            ).encode("utf-8"),
        )
    )

    assert _status_from_messages(messages) == 200
    assert "orphan.bin" not in storage.files


def test_external_bridge_delete_uses_bridge_delete_contract(monkeypatch):
    service = ExternalBridgeStorageService(
        ExternalBridgeStorageConfig(
            base_url="http://bridge.internal",
            auth_mode=BRIDGE_AUTH_MODE_GOOGLE_OIDC,
            auth_audience=None,
        )
    )
    calls: list[tuple[str, str, dict[str, str]]] = []

    monkeypatch.setattr(
        service,
        "_request_json",
        lambda method, path, *, payload=None, query=None: calls.append(
            (method, path, payload)
        )
        or {"deleted": True},
    )

    service.delete("2026/orphan.docx", root="inspection")

    assert calls == [
        (
            "POST",
            "/bridge/storage/delete",
            {"root": "inspection", "relative_path": "2026/orphan.docx"},
        )
    ]


def test_external_bridge_write_stream_sends_chunks(monkeypatch):
    monkeypatch.setattr("backend.app.storage.external_bridge.http.client.HTTPConnection", _FakeHttpConnection)
    service = ExternalBridgeStorageService(
        ExternalBridgeStorageConfig(
            base_url="http://bridge.internal",
            auth_mode=BRIDGE_AUTH_MODE_GOOGLE_OIDC,
            auth_audience=None,
        ),
        chunk_size=4,
    )

    entry = service.write_stream(
        "2026/demo.bin",
        BytesIO(b"abcdefghij"),
        overwrite=False,
    )

    assert entry.size == 10
    assert _FakeHttpConnection.last_instance is not None
    assert _FakeHttpConnection.last_instance.sent_chunks == [b"abcd", b"efgh", b"ij"]
    assert "overwrite=false" in (_FakeHttpConnection.last_instance.path or "")


def test_bridge_exclusive_write_returns_conflict_without_overwriting(monkeypatch):
    headers = _authorized_headers(monkeypatch)
    storage = _BridgeStorageHarness({"existing.bin": b"original"})
    app = create_storage_bridge_app(storage)

    messages = asyncio.run(
        _invoke_asgi(
            app,
            method="POST",
            path=f"/bridge/storage/write?{urlencode({'root': 'inspection', 'relative_path': 'existing.bin', 'overwrite': 'false'})}",
            headers={**headers, "content-type": "application/octet-stream"},
            body=b"replacement",
        )
    )

    assert _status_from_messages(messages) == 409
    assert storage.files["existing.bin"] == b"original"


@pytest.mark.parametrize("operation", ["copy", "move", "rename"])
def test_bridge_file_operations_return_conflict_and_preserve_existing_content(monkeypatch, tmp_path, operation):
    headers = _authorized_headers(monkeypatch)
    root = tmp_path / "inspection"
    root.mkdir()
    source = root / "source.txt"
    target = root / "existing.txt"
    source.write_bytes(b"unmodified-source")
    target.write_bytes(b"existing-document")

    app = create_storage_bridge_app(
        FilesystemStorageService(StorageConfig(inspection_root=root))
    )
    payload = {"root": "inspection", "source_relative_path": "source.txt"}
    if operation == "rename":
        payload["new_name"] = "existing.txt"
    else:
        payload["target_relative_path"] = "existing.txt"

    messages = asyncio.run(
        _invoke_asgi(
            app,
            method="POST",
            path=f"/bridge/storage/{operation}",
            headers={**headers, "content-type": "application/json"},
            body=json.dumps(payload).encode("utf-8"),
        )
    )
    assert _status_from_messages(messages) == 409
    assert source.read_bytes() == b"unmodified-source"
    assert target.read_bytes() == b"existing-document"


def test_bridge_upload_limit_rejects_large_payload(monkeypatch):
    headers = _authorized_headers(monkeypatch)
    monkeypatch.setenv("STORAGE_BRIDGE_MAX_UPLOAD_BYTES", "4")
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = _BridgeStorageHarness({})
        app = create_storage_bridge_app(storage)
        messages = asyncio.run(
            _invoke_asgi(
                app,
                method="POST",
                path=f"/bridge/storage/write?{urlencode({'root': 'inspection', 'relative_path': 'oversize.bin'})}",
                headers={**headers, "content-type": "application/octet-stream"},
                body=b"12345",
            )
        )
    assert _status_from_messages(messages) == 413


def test_bridge_readyz_fails_when_auth_is_not_configured_even_if_bootstrap_health_is_allowed(monkeypatch):
    monkeypatch.setenv("BRIDGE_BOOTSTRAP_ALLOW_UNCONFIGURED_AUTH", "1")
    storage = _BridgeStorageHarness({})
    app = create_storage_bridge_app(storage)

    messages = asyncio.run(
        _invoke_asgi(
            app,
            method="GET",
            path="/readyz",
        )
    )

    assert _status_from_messages(messages) == 503


def test_bridge_healthz_reports_bootstrap_auth_pending(monkeypatch):
    monkeypatch.setenv("BRIDGE_BOOTSTRAP_ALLOW_UNCONFIGURED_AUTH", "1")
    storage = _BridgeStorageHarness({})
    app = create_storage_bridge_app(storage)

    messages = asyncio.run(
        _invoke_asgi(
            app,
            method="GET",
            path="/healthz",
        )
    )

    assert _status_from_messages(messages) == 200
    payload = json.loads(_body_from_messages(messages).decode("utf-8"))
    assert payload["auth_configured"] is False
    assert payload["bootstrap_auth_pending"] is True
