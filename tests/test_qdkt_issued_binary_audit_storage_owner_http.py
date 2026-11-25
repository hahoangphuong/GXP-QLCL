"""Issued-QĐKT binary audit must use the app-owned storage adapter.

Exercise real ASGI FastAPI routing without TestClient: repository's locked
Starlette dependency intentionally does not include httpx2.
"""
import asyncio
import json
from uuid import uuid4

from backend.app.main import create_app
from backend.app.services.workflow import CaseWorkflowService


def _request(storage, url):
    app = create_app(
        "sqlite:///:memory:",
        storage_service=storage,
        app_env={"AUTH_MODE": "header_stub", "APP_ENV": "development"},
    )
    # For the absent-storage case, development startup may initialize its
    # local fallback. Force the actual app-level unavailable state.
    app.state.storage_service = storage

    async def invoke():
        messages = []
        received = False

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.Future()

        async def send(message):
            messages.append(message)

        await app({
            "type": "http", "asgi": {"version": "3.0"},
            "http_version": "1.1", "method": "GET", "scheme": "http",
            "path": url, "raw_path": url.encode(),
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/json"),
                (b"x-auth-user", b"synthetic-auditor"),
                (b"x-auth-role", b"admin"),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("localhost", 80), "root_path": "",
        }, receive, send)
        status = next(x["status"] for x in messages if x["type"] == "http.response.start")
        data = b"".join(x.get("body", b"") for x in messages if x["type"] == "http.response.body")
        return status, json.loads(data) if data else None

    return asyncio.run(invoke())


def _path():
    return (
        f"/cases/{uuid4()}/qdkt-issued-decisions/{uuid4()}"
        "/pdf-version/binary-audit"
    )


def test_qdkt_issued_binary_audit_uses_exact_startup_storage_not_env(monkeypatch):
    startup_storage = object()
    observed = []

    def audit(self, session, *, case_id, decision_id, storage, user):
        assert storage is startup_storage
        observed.append((case_id, decision_id, user))
        return {
            "case_id": case_id, "decision_id": decision_id,
            "binding_id": str(uuid4()), "document_version_id": str(uuid4()),
            "verified_sha256": "a" * 64,
            "verified_pdf_bytes": 123,
            "actual_binary_checksum_verified": True,
            "basic_pdf_envelope_verified": True,
            "signature_cryptographically_verified": False,
            "pdf_decision_content_verified": False,
            "independent_legal_issuance_verified": False,
            "ready_to_render": False,
        }

    def forbidden_factory(*args, **kwargs):
        raise AssertionError("binary audit reconstructed a different storage adapter")

    monkeypatch.setattr(CaseWorkflowService, "audit_qdkt_issued_pdf_binary", audit)
    monkeypatch.setattr(
        "backend.app.storage.factory.create_storage_service_from_env", forbidden_factory
    )
    url = _path()
    status, body = _request(startup_storage, url)
    assert status == 200, body
    assert body["case_id"] == url.split("/")[2]
    assert body["decision_id"] == url.split("/")[4]
    assert body["actual_binary_checksum_verified"] is True
    assert body["signature_cryptographically_verified"] is False
    assert body["independent_legal_issuance_verified"] is False
    assert len(observed) == 1


def test_qdkt_issued_binary_audit_fails_closed_when_startup_storage_missing(monkeypatch):
    called = []

    def forbidden_audit(*args, **kwargs):
        called.append(True)
        raise AssertionError("audit must not run without validated storage")

    monkeypatch.setattr(CaseWorkflowService, "audit_qdkt_issued_pdf_binary", forbidden_audit)
    status, body = _request(None, _path())
    assert status == 503, body
    assert body["detail"] == "QDKT_ISSUED_BINARY_STORAGE_UNAVAILABLE"
    assert not called
