"""Real Process B HTTP -> version link -> startup-owned filesystem bytes.

The test uses a fresh migrated disposable PostgreSQL schema, an ephemeral
local filesystem storage root and the actual ASGI router/permission handler.
It does NOT prove a cryptographic signature or legally issued decision.
"""
from __future__ import annotations

import asyncio
from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.enums import DocumentVariantType
from backend.app.db.models.phase1 import (
    AuditEvent, Document, DocumentVariant, DocumentVersion, QdKtIssuedDocumentBinding,
    StorageBinding,
)
from backend.app.main import create_app
from backend.app.storage.local import LocalStorageService
from backend.app.storage.types import StorageConfig
from test_canonical_workflow_postgres import DAY, SERVICE, pg_engine, seed, write


def _http(app, method: str, path: str, payload: dict | None = None, *, role="admin"):
    """Minimal real ASGI HTTP caller; never requires the optional httpx2."""
    async def invoke():
        body = b"" if payload is None else json.dumps(payload).encode()
        messages = []
        received = False

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": body, "more_body": False}
            await asyncio.Future()

        async def send(message):
            messages.append(message)

        await app({
            "type": "http", "asgi": {"version": "3.0"},
            "http_version": "1.1", "method": method, "scheme": "http",
            "path": path, "raw_path": path.encode(), "query_string": b"",
            "headers": [
                (b"content-type", b"application/json"),
                (b"x-auth-user", b"synthetic-pdf-operator"),
                (b"x-auth-role", role.encode()),
            ],
            "client": ("127.0.0.1", 12345), "server": ("localhost", 80),
            "root_path": "",
        }, receive, send)
        status = next(x["status"] for x in messages if x["type"] == "http.response.start")
        raw = b"".join(x.get("body", b"") for x in messages if x["type"] == "http.response.body")
        return status, json.loads(raw) if raw else None
    return asyncio.run(invoke())


def _ok(app, method, path, payload=None, **kwargs):
    status, body = _http(app, method, path, payload, **kwargs)
    assert status == 200, (method, path, status, body)
    return body


def test_qdkt_operator_attested_pdf_binding_to_actual_bytes_http_postgres(pg_engine, tmp_path):
    owner_case, _ = seed(pg_engine)
    foreign_case, _ = seed(pg_engine)
    plan = write(
        pg_engine, SERVICE.upsert_inspection_plan,
        case_id=owner_case, plan_start_on=DAY, plan_end_on=DAY,
        planning_sheet_name="Exact operator-owned PDF chain",
        decision_document_hint=None, reason="Synthetic QDKT plan",
    )
    root = tmp_path / "inspection"
    root.mkdir()
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    app = create_app(
        pg_engine.url.render_as_string(hide_password=False),
        storage_service=storage,
        app_env={"AUTH_MODE": "header_stub", "APP_ENV": "development"},
    )
    assert app.state.storage_service is storage

    decision_id = str(uuid4())
    issued_root = f"/cases/{owner_case}/qdkt-issued-decisions"
    payload = {
        "decision_id": decision_id,
        "expected_plan_version": plan["row_version"],
        "reference": "SYNTH-EXTERNAL-QDKT",
        "decision_on": DAY.isoformat(),
        "source_text": "Synthetic operator-transcribed approved decision",
        "relation_type": "INITIAL", "related_decision_id": None,
        "external_approval_confirmed": True,
        "approval_basis": "Synthetic external operator confirmation",
        "team_confirmed": True, "roster_source": "USER_ENTERED",
        "members": [{
            "source_member_id": str(uuid4()), "display_name": "Synthetic leader",
            "role_code": "LEADER", "job_title": "Inspector",
        }],
        "reason": "Synthetic external document recording",
    }
    refused, _ = _http(app, "POST", issued_root, payload, role="reader")
    assert refused == 403
    issued = _ok(app, "POST", issued_root, payload)
    assert issued["decision_id"] == decision_id
    assert issued["relation_type"] == "INITIAL"

    pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
    digest = sha256(pdf).hexdigest()
    relative_folder = "synthetic-" + owner_case
    relative_file = relative_folder + "/issued/decision.pdf"
    full_path = root / relative_file
    full_path.parent.mkdir(parents=True)
    full_path.write_bytes(pdf)

    # The exact pre-existing DocumentVersion is registered independently of
    # Process B. The API must not create an inferred/latest version.
    with Session(pg_engine) as db:
        folder = StorageBinding(
            case_id=owner_case, relative_path=relative_folder,
            storage_class="local_filesystem_fake",
        )
        db.add(folder); db.flush()
        document = Document(
            case_id=owner_case, family_code="INSPECTION_QD_KT",
            document_type_code="INSPECTION_QD_KT",
        )
        db.add(document); db.flush()
        variant = DocumentVariant(
            document_id=document.id, variant_type=DocumentVariantType.SIGNED_PDF,
            language_code="vi",
        )
        db.add(variant); db.flush()
        version = DocumentVersion(
            document_variant_id=variant.id, version_no=1,
            storage_binding_id=folder.id, storage_root="inspection",
            storage_relative_path=relative_file, checksum_sha256=digest,
        )
        db.add(version)
        db.commit()
        version_id = version.id

    decision_path = issued_root + "/" + decision_id
    binding_path = decision_path + "/pdf-version"
    audit_path = binding_path + "/binary-audit"

    status, not_linked = _http(app, "GET", binding_path)
    assert status == 404, not_linked
    binding_id = str(uuid4())
    link_payload = {
        "binding_id": binding_id,
        "document_version_id": version_id,
        "reason": "Synthetic explicit external PDF association",
    }
    denied, _ = _http(app, "POST", binding_path, link_payload, role="reader")
    assert denied == 403
    saved = _ok(app, "POST", binding_path, link_payload)
    assert saved["binding_id"] == binding_id
    assert saved["document_version_id"] == version_id
    assert saved["recorded_checksum_sha256"] == digest
    assert saved["variant_type"] == "signed_pdf"
    assert saved["binary_checksum_verified"] is False
    assert saved["independent_signature_verified"] is False
    assert saved["legal_issuance_verified"] is False
    assert saved["ready_to_render"] is False
    assert _ok(app, "GET", binding_path) == saved

    foreign_path = f"/cases/{foreign_case}/qdkt-issued-decisions/{decision_id}/pdf-version"
    denied, _ = _http(app, "GET", foreign_path)
    assert denied == 404
    denied, _ = _http(app, "GET", foreign_path + "/binary-audit")
    assert denied == 404
    denied, _ = _http(app, "GET", audit_path, role="reader")
    assert denied == 403

    def evidence_counts():
        with Session(pg_engine) as db:
            return (
                db.scalar(select(func.count()).select_from(QdKtIssuedDocumentBinding)
                    .where(QdKtIssuedDocumentBinding.inspection_decision_id == decision_id)),
                db.scalar(select(func.count()).select_from(AuditEvent)
                    .where(AuditEvent.entity_type == "qdkt_issued_document_binding",
                           AuditEvent.entity_id == binding_id,
                           AuditEvent.action == "qdkt_issued_pdf_version.bind")),
            )

    before = evidence_counts()
    assert before == (1, 1)
    actual = _ok(app, "GET", audit_path)
    assert actual["case_id"] == owner_case
    assert actual["decision_id"] == decision_id
    assert actual["binding_id"] == binding_id
    assert actual["document_version_id"] == version_id
    assert actual["verified_sha256"] == digest
    assert actual["verified_pdf_bytes"] == len(pdf)
    assert actual["actual_binary_checksum_verified"] is True
    assert actual["basic_pdf_envelope_verified"] is True
    assert actual["signature_cryptographically_verified"] is False
    assert actual["pdf_decision_content_verified"] is False
    assert actual["independent_legal_issuance_verified"] is False
    assert actual["ready_to_render"] is False
    assert evidence_counts() == before

    # The exact registered PDF bytes can change without changing metadata.
    # A read must fail closed; it must not silently bind a different file or
    # update the persisted checksum/attestation.
    full_path.write_bytes(pdf.replace(b"Catalog", b"Altered"))
    status, tampered = _http(app, "GET", audit_path)
    assert status == 409, tampered
    assert tampered["detail"] == "QDKT_ISSUED_BINARY_CHECKSUM_MISMATCH"
    assert _ok(app, "GET", binding_path) == saved
    assert evidence_counts() == before
    full_path.write_bytes(pdf)
    assert _ok(app, "GET", audit_path) == actual
    assert evidence_counts() == before

    # POST replay is never used to recover an unknown-outcome binding.
    replay, _ = _http(app, "POST", binding_path, link_payload)
    assert replay == 409
    assert evidence_counts() == before
    assert _ok(app, "GET", binding_path) == saved
