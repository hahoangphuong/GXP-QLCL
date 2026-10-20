"""Typed KHKT Case create boundary: no caller-owned business/template fields.

The generation/commit owner is exercised by the existing KHKT end-to-end
suite. These tests prove that the contextual HTTP route supplies only
canonical Case-derived inputs to that same owner.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routers.document import register_document_routes
from backend.app.auth import build_authenticated_user, get_authenticated_user
from backend.app.document.inspection_ke_hoach_kt_template_asset_contract import (
    get_inspection_ke_hoach_kt_output_filename,
)
from backend.app.services.document_api import DocumentWorkflowService


class _Session:
    is_active = True

    def __init__(self, case):
        self.case = case
        self.commits = 0

    def get(self, model, identity):
        from backend.app.db.models.phase1 import Case
        assert model is Case
        return self.case if self.case is not None and identity == self.case.id else None

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


def _app(monkeypatch, *, gxp_type="GMP", can_write=True):
    case = None if gxp_type is None else SimpleNamespace(id="case-typed", gxp_type=gxp_type)
    session = _Session(case)
    app = FastAPI()
    app.state.storage_service = object()
    register_document_routes(app, lambda: session)
    user = build_authenticated_user(
        "typed-khkt-inspector",
        permissions={"document.write", "document.read"} if can_write else {"document.read"},
    )
    app.dependency_overrides[get_authenticated_user] = lambda: user
    rendered = []

    def _fake_render(self, actual_session, *, storage, payload, user):
        assert actual_session is session
        assert storage is app.state.storage_service
        rendered.append(payload)
        return {
            "document_id": "document-typed",
            "document_variant_id": "variant-typed",
            "document_version_id": "version-typed",
            "generation_run_id": "run-typed",
            "generation_status": "succeeded",
            "output_storage_root": "inspection",
            "output_storage_relative_path": "synthetic/khkt.docx",
            "output_original_filename": payload["output_filename"],
            "checksum_sha256": "a" * 64,
            "byte_size": 1,
            "scalar_replacement_mode": "khkt_contract_exact",
            "template_variant_key": payload["gxp_type"],
            "replaced_bookmarks": [],
            "replaced_table_regions": [],
            "replaced_parts": [],
            "audit_event_id": "audit-typed",
            "_rollback_cleanup_required": False,
        }

    monkeypatch.setattr(DocumentWorkflowService, "render_template_docx", _fake_render)
    return app, session, rendered


@pytest.mark.parametrize("gxp_type", ("GMP", "GLP", "GMPbb", "GSP"))
def test_typed_case_khkt_http_route_derives_all_business_fields(monkeypatch, gxp_type):
    app, session, rendered = _app(monkeypatch, gxp_type=gxp_type)
    with TestClient(app) as client:
        response = client.post(
            "/cases/case-typed/documents/inspection-ke-hoach-kt/render",
            json={"idempotency_key": "user-request-1"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["generation_status"] == "succeeded"
    assert session.commits == 1
    assert rendered == [{
        "family_code": "INSPECTION_KE_HOACH_KT",
        "case_id": "case-typed",
        "gxp_type": gxp_type,
        "storage_scope": "inspection_folder",
        "language_code": "vi",
        "idempotency_key": "user-request-1",
        "output_filename": get_inspection_ke_hoach_kt_output_filename(gxp_type),
        "payload": {},
        "strict_payload": True,
        "capa_cycle_id": None,
        "certificate_id": None,
        "business_eligibility_certificate_id": None,
        "change_request_id": None,
        "legacy_mode": None,
        "payload_notes": None,
        "copy_pt": False,
    }]


@pytest.mark.parametrize("untrusted_field", (
    "family_code", "case_id", "gxp_type", "storage_scope",
    "output_filename", "payload", "certificate_id",
))
def test_typed_khkt_route_rejects_client_owned_business_fields(monkeypatch, untrusted_field):
    app, session, rendered = _app(monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/cases/case-typed/documents/inspection-ke-hoach-kt/render",
            json={"idempotency_key": "x", untrusted_field: "untrusted"},
        )
    assert response.status_code == 422
    assert session.commits == 0
    assert rendered == []


@pytest.mark.parametrize(("gxp_type", "case_id", "status"), (
    (None, "not-found", 404),
    ("UNSUPPORTED", "case-typed", 409),
))
def test_typed_khkt_route_fails_closed_before_render(
    monkeypatch, gxp_type, case_id, status,
):
    app, session, rendered = _app(monkeypatch, gxp_type=gxp_type)
    with TestClient(app) as client:
        response = client.post(
            f"/cases/{case_id}/documents/inspection-ke-hoach-kt/render",
            json={},
        )
    assert response.status_code == status
    assert session.commits == 0
    assert rendered == []


def test_typed_khkt_route_checks_write_permission_before_case_lookup(monkeypatch):
    app, session, rendered = _app(monkeypatch, can_write=False)
    with TestClient(app) as client:
        response = client.post(
            "/cases/case-typed/documents/inspection-ke-hoach-kt/render",
            json={},
        )
    assert response.status_code == 403
    assert session.commits == 0
    assert rendered == []
