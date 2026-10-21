"""GET KHKT runtime readiness is a separately authorized read-only inspection."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException

from backend.app.api.routers.document import register_document_routes
from backend.app.auth import build_authenticated_user
from backend.app.read_models import CaseInspectionPlanRuntimeReadinessRead
from backend.app.services.document_api import DocumentWorkflowService


ROUTE = "/cases/{case_id}/documents/inspection-ke-hoach-kt/readiness"


def _endpoint():
    app = FastAPI()
    register_document_routes(app, lambda: None)
    route = next(r for r in app.routes if getattr(r, "path", None) == ROUTE)
    assert route.methods == {"GET"}
    return route.endpoint


def test_runtime_readiness_get_requires_document_write_before_any_case_or_storage_read(
    monkeypatch,
):
    calls: list[str] = []

    def unexpected(*_args, **_kwargs):
        calls.append("readiness")
        raise AssertionError("must not inspect when the user has no write permission")

    monkeypatch.setattr(
        DocumentWorkflowService,
        "get_case_inspection_plan_runtime_readiness",
        unexpected,
    )
    reader = build_authenticated_user("khkt-reader", permissions={"document.read"})
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(storage_service=object())))

    with pytest.raises(HTTPException) as exc:
        _endpoint()(case_id="case-no-access", request=request, session=object(), user=reader)
    assert exc.value.status_code == 403
    assert calls == []


def test_runtime_readiness_get_returns_typed_diagnostic_without_calling_render_or_prepare(
    monkeypatch,
):
    calls: list[tuple[str, object]] = []

    def inspect(_self, session, *, case_id, storage):
        calls.append((case_id, storage))
        return {
            "case_id": case_id,
            "family_code": "INSPECTION_KE_HOACH_KT",
            "gxp_type": "GLP",
            "canonical_input_status": "ready",
            "template_binary_status": "blocked",
            "inspection_folder_status": "blocked",
            "ready_to_attempt_render": False,
            "blocked_reasons": ["template_binary_or_contract_unavailable", "inspection_folder_unavailable"],
        }

    monkeypatch.setattr(DocumentWorkflowService, "get_case_inspection_plan_runtime_readiness", inspect)
    monkeypatch.setattr(
        DocumentWorkflowService,
        "prepare_generation",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("unexpected prepare")),
    )
    monkeypatch.setattr(
        DocumentWorkflowService,
        "render_template_docx",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("unexpected render")),
    )
    storage = object()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(storage_service=storage)))
    result = _endpoint()(
        case_id="synthetic-case",
        request=request,
        session=object(),
        user=build_authenticated_user("khkt-writer", permissions={"document.write"}),
    )
    assert isinstance(result, CaseInspectionPlanRuntimeReadinessRead)
    assert result.case_id == "synthetic-case"
    assert result.ready_to_attempt_render is False
    assert result.blocked_reasons == [
        "template_binary_or_contract_unavailable",
        "inspection_folder_unavailable",
    ]
    assert calls == [("synthetic-case", storage)]
    assert not hasattr(result, "storage_relative_path")
    assert not hasattr(result, "checksum_sha256")
