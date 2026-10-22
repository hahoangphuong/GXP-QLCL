"""The QĐKT readiness API must never become an executable create contract."""
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.api.routers.document import register_document_routes
from backend.app.read_models import CaseQdKtRuntimeReadinessRead


def test_qdkt_readiness_route_is_get_only_and_typed(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'route.sqlite').as_posix()}")
    app = FastAPI()
    register_document_routes(app, sessionmaker(bind=engine))
    routes = [
        r for r in app.routes
        if getattr(r, "path", "") == "/cases/{case_id}/documents/inspection-qd-kt/readiness"
    ]
    assert len(routes) == 1
    route = routes[0]
    assert route.methods == {"GET"}
    assert route.response_model is CaseQdKtRuntimeReadinessRead
    assert not any(
        getattr(r, "path", "").endswith("/inspection-qd-kt/render")
        for r in app.routes
    )
    engine.dispose()


def test_qdkt_readiness_schema_cannot_claim_ready():
    import pytest
    from pydantic import ValidationError

    payload = {
        "case_id": "case", "family_code": "INSPECTION_QD_KT",
        "decision_source_id": "decision", "registered_site_id": "site",
        "blocked_reasons": ["QDKT_TYPED_RENDER_CONTRACT_MISSING"],
    }
    assert CaseQdKtRuntimeReadinessRead(**payload, ready_to_render=False).ready_to_render is False
    with pytest.raises(ValidationError):
        CaseQdKtRuntimeReadinessRead(**payload, ready_to_render=True)
    with pytest.raises(ValidationError):
        CaseQdKtRuntimeReadinessRead(**{**payload, "family_code": "INSPECTION_KE_HOACH_KT"}, ready_to_render=False)


def _qdkt_endpoint():
    app = FastAPI()
    register_document_routes(app, lambda: None)
    return next(
        route.endpoint for route in app.routes
        if getattr(route, "path", "") == "/cases/{case_id}/documents/inspection-qd-kt/readiness"
    )


def test_qdkt_readiness_denies_reader_before_source_query(monkeypatch):
    from fastapi import HTTPException
    from backend.app.auth import build_authenticated_user
    import backend.app.api.routers.document as document_router

    calls = []

    def unexpected(*_args, **_kwargs):
        calls.append("read")
        raise AssertionError("no source query before RBAC")

    monkeypatch.setattr(document_router, "inspect_qdkt_case_readiness", unexpected)
    reader = build_authenticated_user("readonly-user", permissions={"document.read"})
    with pytest.raises(HTTPException) as exc:
        _qdkt_endpoint()(case_id="case", session=object(), user=reader)
    assert exc.value.status_code == 403
    assert calls == []


def test_qdkt_readiness_authorized_still_explicitly_blocked(monkeypatch):
    from types import SimpleNamespace
    from backend.app.auth import build_authenticated_user
    import backend.app.api.routers.document as document_router

    calls = []

    def inspect(session, *, case_id):
        calls.append((session, case_id))
        return SimpleNamespace(
            case_id=case_id,
            decision_source_id="decision-id",
            registered_site_id="site-id",
            blockers=("BLANK_ISSUANCE_DATE_BOOKMARK_UNVERIFIED",),
        )

    monkeypatch.setattr(document_router, "inspect_qdkt_case_readiness", inspect)
    session = object()
    response = _qdkt_endpoint()(
        case_id="case-id", session=session,
        user=build_authenticated_user("writer-user", permissions={"document.write"}),
    )
    assert response.family_code == "INSPECTION_QD_KT"
    assert response.ready_to_render is False
    assert response.blocked_reasons == ["BLANK_ISSUANCE_DATE_BOOKMARK_UNVERIFIED"]
    assert calls == [(session, "case-id")]
