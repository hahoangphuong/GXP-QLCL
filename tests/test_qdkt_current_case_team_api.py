"""The current-team read route must never manufacture a draft or issued roster."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.api.routers.document import register_document_routes
from backend.app.auth import build_authenticated_user
from backend.app.read_models import CaseQdKtCurrentTeamRead
from backend.app.document.inspection_qd_kt_team_source import QdKtTeamSourceBlocked


PATH = "/cases/{case_id}/documents/inspection-qd-kt/current-team"


def endpoint():
    app = FastAPI()
    register_document_routes(app, lambda: None)
    routes = [r for r in app.routes if getattr(r, "path", "") == PATH]
    assert len(routes) == 1
    assert routes[0].methods == {"GET"}
    assert routes[0].response_model is CaseQdKtCurrentTeamRead
    return routes[0].endpoint


def payload():
    return {
        "case_id": "case-a", "team_id": "team-a", "team_revision": 3,
        "source_kind": "CURRENT_CASE_TEAM",
        "draft_snapshot_available": False, "issued_team_confirmed": False,
        "members": [
            {"member_id": "m-1", "sort_order": 0, "role_code": "LEADER",
             "display_name": "Inspector One", "identity_kind": "INSPECTOR_PROFILE",
             "inspector_profile_id": "inspector-1", "person_id": None,
             "participant_catalog_id": None},
            {"member_id": "m-2", "sort_order": 1, "role_code": "MEMBER",
             "display_name": "Inspector Two", "identity_kind": "LEGACY_PERSON",
             "inspector_profile_id": None, "person_id": None,
             "participant_catalog_id": None},
        ],
    }


def test_read_only_route_and_explicit_current_team_flags():
    p = payload()
    model = CaseQdKtCurrentTeamRead(**p)
    assert model.members[0].role_code == "LEADER"
    assert [row.member_id for row in model.members] == ["m-1", "m-2"]
    with pytest.raises(ValidationError):
        CaseQdKtCurrentTeamRead(**{**p, "issued_team_confirmed": True})
    with pytest.raises(ValidationError):
        CaseQdKtCurrentTeamRead(**{**p, "draft_snapshot_available": True})
    endpoint()


def test_reader_denied_before_db_query(monkeypatch):
    import backend.app.api.routers.document as router
    calls = []
    monkeypatch.setattr(router, "read_qdkt_current_case_team",
                        lambda *_args, **_kwargs: calls.append("read"))
    reader = build_authenticated_user("reader", permissions={"document.read"})
    with pytest.raises(HTTPException) as exc:
        endpoint()(case_id="case-a", session=object(), user=reader)
    assert exc.value.status_code == 403
    assert calls == []


def test_writer_gets_source_projection_only(monkeypatch):
    import backend.app.api.routers.document as router
    p = payload()
    monkeypatch.setattr(router, "read_qdkt_current_case_team",
                        lambda _session, *, case_id: p if case_id == "case-a" else None)
    writer = build_authenticated_user("writer", permissions={"document.write"})
    result = endpoint()(case_id="case-a", session=object(), user=writer)
    assert result.source_kind == "CURRENT_CASE_TEAM"
    assert result.team_revision == 3
    assert result.issued_team_confirmed is False


def test_missing_or_ambiguous_team_fails_closed(monkeypatch):
    import backend.app.api.routers.document as router
    def blocked(_session, *, case_id):
        raise QdKtTeamSourceBlocked("INSPECTION_TEAM_ORDER_AMBIGUOUS")
    monkeypatch.setattr(router, "read_qdkt_current_case_team", blocked)
    writer = build_authenticated_user("writer", permissions={"document.write"})
    with pytest.raises(HTTPException) as exc:
        endpoint()(case_id="case-a", session=object(), user=writer)
    assert exc.value.status_code == 409
    assert exc.value.detail == "INSPECTION_TEAM_ORDER_AMBIGUOUS"
