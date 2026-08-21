from __future__ import annotations

import asyncio
from contextlib import contextmanager
from io import BytesIO
import json
from pathlib import Path
import tempfile
from urllib.parse import urlencode

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
from backend.app.storage.types import ExternalBridgeStorageConfig, StorageConfig
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

    entry = service.write_stream("2026/demo.bin", BytesIO(b"abcdefghij"))

    assert entry.size == 10
    assert _FakeHttpConnection.last_instance is not None
    assert _FakeHttpConnection.last_instance.sent_chunks == [b"abcd", b"efgh", b"ij"]


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
