"""Issued-QĐKT binary audit reads only the application's startup-owned storage.

The endpoint must not construct another storage adapter from environment
variables. This regression uses real HTTP routing and permission checks but
a stubbed service so it can target the storage-injection boundary precisely.
"""
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services.workflow import CaseWorkflowService


def _client(storage):
    app = create_app(
        "sqlite:///:memory:",
        storage_service=storage,
        app_env={"AUTH_MODE": "header_stub", "APP_ENV": "development"},
    )
    # Model an unavailable startup adapter even if development defaults
    # would otherwise construct local storage.
    app.state.storage_service = storage
    return TestClient(app)


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
    with _client(startup_storage) as client:
        url = _path()
        result = client.get(url, headers={
            "X-Auth-User": "synthetic-auditor", "X-Auth-Role": "admin",
        })
    assert result.status_code == 200, result.text
    body = result.json()
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
    with _client(None) as client:
        result = client.get(_path(), headers={
            "X-Auth-User": "synthetic-auditor", "X-Auth-Role": "admin",
        })
    assert result.status_code == 503, result.text
    assert result.json()["detail"] == "QDKT_ISSUED_BINARY_STORAGE_UNAVAILABLE"
    assert not called
