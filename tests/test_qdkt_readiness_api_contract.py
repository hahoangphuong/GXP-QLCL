"""The QĐKT readiness API must never become an executable create contract."""
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
