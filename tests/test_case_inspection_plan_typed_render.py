"""Typed KHKT Case create boundary without an HTTP client dependency.

The generation/commit owner is exercised by the existing KHKT end-to-end
suite. These tests invoke the registered FastAPI endpoint and validate the
actual Pydantic input schema, without Starlette's optional TestClient package.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError

from backend.app.api.routers.document import register_document_routes
from backend.app.auth import build_authenticated_user
from backend.app.document.inspection_ke_hoach_kt_template_asset_contract import (
    get_inspection_ke_hoach_kt_output_filename,
)
from backend.app.read_models import CaseInspectionPlanRenderRequest
from backend.app.services.document_api import DocumentWorkflowService


ROUTE = "/cases/{case_id}/documents/inspection-ke-hoach-kt/render"


class _Session:
    is_active = True

    def __init__(self, case):
        self.case = case
        self.commits = 0

    def get(self, model, identity):
        from backend.app.db.models.phase1 import Case
        assert model is Case
        return self.case if self.case is not None and identity == self.case.id else None

    def scalar(self, statement):
        from backend.app.db.models.phase1 import Case, DocumentVersion
        entity = statement.column_descriptions[0]["entity"]
        if entity is Case:
            # Typed create takes the Case lock before inspecting current versions.
            assert statement._for_update_arg is not None
            return self.case
        if entity is DocumentVersion:
            # These endpoint tests have no persisted KHKT document; the real
            # current-version query is tested against SQLite separately.
            return None
        raise AssertionError(f"unexpected scalar lookup: {entity!r}")

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
    return app, session, user, rendered


def _invoke(app, session, user, *, case_id="case-typed", body=None):
    endpoint = next(
        route.endpoint for route in app.routes
        if getattr(route, "path", None) == ROUTE and "POST" in route.methods
    )
    # The router, pydantic model and existing commit path are real;
    # the SQLAlchemy session and storage result are controlled fixtures.
    scope = {
        "type": "http",
        "method": "POST",
        "path": ROUTE.replace("{case_id}", case_id),
        "headers": [],
        "app": app,
    }
    return endpoint(
        case_id=case_id,
        payload=CaseInspectionPlanRenderRequest.model_validate(body or {}),
        request=Request(scope),
        session=session,
        user=user,
    )


@pytest.mark.parametrize("gxp_type", ("GMP", "GLP", "GMPbb", "GSP"))
def test_typed_case_khkt_endpoint_derives_all_business_fields(monkeypatch, gxp_type):
    app, session, user, rendered = _app(monkeypatch, gxp_type=gxp_type)
    response = _invoke(
        app, session, user, body={"idempotency_key": "user-request-1"},
    )
    assert response.generation_status == "succeeded"
    assert response.output_original_filename == get_inspection_ke_hoach_kt_output_filename(gxp_type)
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
def test_typed_khkt_request_schema_rejects_client_owned_business_fields(
    monkeypatch, untrusted_field,
):
    app, session, user, rendered = _app(monkeypatch)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _invoke(app, session, user, body={
            "idempotency_key": "x", untrusted_field: "untrusted",
        })
    assert session.commits == 0
    assert rendered == []


@pytest.mark.parametrize(("gxp_type", "case_id", "status"), (
    (None, "not-found", 404),
    ("UNSUPPORTED", "case-typed", 409),
))
def test_typed_khkt_endpoint_fails_closed_before_render(
    monkeypatch, gxp_type, case_id, status,
):
    app, session, user, rendered = _app(monkeypatch, gxp_type=gxp_type)
    with pytest.raises(HTTPException) as failure:
        _invoke(app, session, user, case_id=case_id)
    assert failure.value.status_code == status
    assert session.commits == 0
    assert rendered == []


def test_typed_khkt_endpoint_checks_write_permission_before_case_lookup(monkeypatch):
    app, session, user, rendered = _app(monkeypatch, can_write=False)
    with pytest.raises(HTTPException) as failure:
        _invoke(app, session, user)
    assert failure.value.status_code == 403
    assert session.commits == 0
    assert rendered == []
