"""Case workspace KHKT capability must not break read-only Case access."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, Company, Site
from backend.app.document.contextual_actions import KHKT_CASE_TYPED_RENDER_ROUTE
from backend.app.api.routers.document import register_document_routes
from backend.app.read_models import ContextualDocumentActionAvailabilityRead
from fastapi import FastAPI
from backend.app.document.inspection_ke_hoach_kt_template_asset_contract import (
    InspectionKeHoachKtTemplateAssetContractError,
    get_inspection_ke_hoach_kt_output_filename,
)
from backend.app.services.catalog import CatalogReadService


def _seed_case(tmp_path, *, gxp_type: str):
    engine = create_engine(
        f"sqlite:///{(tmp_path / ('khkt-' + gxp_type + '.sqlite')).as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Công ty thử KHKT", short_name="KHKT")
        session.add(company)
        session.flush()
        site = Site(
            company_id=company.id, site_name="Cơ sở thử KHKT",
            site_address="Hà Nội", province_name="Hà Nội",
        )
        session.add(site)
        session.flush()
        case = Case(
            site_id=site.id,
            gxp_type=gxp_type,
            state=CaseState.DRAFT,
            applicable_standard="Thử nghiệm",
            opened_year=2026,
        )
        session.add(case)
        session.commit()
        return engine, case.id


def _create_action(contextual_items):
    family = next(
        item for item in contextual_items
        if item["family_code"] == "INSPECTION_KE_HOACH_KT"
    )
    return family, next(
        action for action in family["actions"]
        if action["action_key"] == "create"
    )


@pytest.mark.parametrize("gxp_type", ("GDP", "UNSUPPORTED"))
def test_unsupported_gxp_case_workspace_remains_readable_and_khkt_create_blocked(
    tmp_path, gxp_type,
):
    engine, case_id = _seed_case(tmp_path, gxp_type=gxp_type)
    user = build_authenticated_user(
        "manager", permissions={"document.read", "document.write"}
    )
    with Session(engine) as session:
        service = CatalogReadService()
        # Exercise the complete Case read model, not only a helper:
        # an unsupported template must not turn Case workspace into HTTP 500.
        workspace = service.get_case_workspace(
            session, case_id=case_id, user=user,
        )
        family, create = _create_action(
            service._build_case_contextual_document_actions(
                session, case_id=case_id, capa_cycles=[], user=user,
            )
        )

    assert workspace["case_summary"]["gxp_type"] == gxp_type
    ws_family = next(
        item for item in workspace["contextual_document_actions"]
        if item["family_code"] == "INSPECTION_KE_HOACH_KT"
    )
    assert ws_family["actions"][1] == create
    assert family["parent_id"] == case_id
    assert create["available"] is False
    assert create["reason_code"] == "unsupported_gxp_type"
    assert create["create_readiness"] == "UNSUPPORTED_GXP_TYPE"
    assert "không có mẫu Kế hoạch kiểm tra" in create["disabled_reason"]
    assert create["parent_scope"] == "case"
    assert create["parent_id"] == case_id
    assert "create_output_filename" not in create
    assert "create_storage_scope" not in create
    assert "create_endpoint" not in create
    assert "create_http_method" not in create


@pytest.mark.parametrize("gxp_type", ("GMP", "GLP", "GMPbb", "GSP"))
def test_supported_gxp_keeps_existing_exact_khkt_create_contract(
    tmp_path, gxp_type, monkeypatch,
):
    engine, case_id = _seed_case(tmp_path, gxp_type=gxp_type)
    # This test isolates the advertised typed route and exact asset metadata;
    # canonical business data availability is covered by dedicated tests.
    monkeypatch.setattr(
        "backend.app.services.catalog.load_inspection_ke_hoach_kt_payload_input",
        lambda *_args, **_kwargs: object(),
    )
    user = build_authenticated_user(
        "manager", permissions={"document.read", "document.write"}
    )
    with Session(engine) as session:
        _, create = _create_action(
            CatalogReadService()._build_case_contextual_document_actions(
                session, case_id=case_id, capa_cycles=[], user=user,
            )
        )
    assert create["available"] is True
    assert create["create_input_readiness"] == "CANONICAL_INPUT_READY"
    assert create["create_input_blocked_reason"] is None
    assert create["reason_code"] is None
    assert create["create_readiness"] == "READY_CREATE_OPEN_HISTORY"
    assert create["create_gxp_type"] == gxp_type
    assert create["create_storage_scope"] == "inspection_folder"
    assert create["create_output_filename"] == get_inspection_ke_hoach_kt_output_filename(gxp_type)
    assert create["create_endpoint"] == (
        f"/cases/{case_id}/documents/inspection-ke-hoach-kt/render"
    )
    assert create["create_http_method"] == "POST"
    typed = ContextualDocumentActionAvailabilityRead(**create)
    assert typed.create_endpoint == create["create_endpoint"]
    assert typed.create_http_method == "POST"


def test_supported_gxp_corrupt_template_contract_still_fails_closed(tmp_path, monkeypatch):
    engine, case_id = _seed_case(tmp_path, gxp_type="GMP")
    user = build_authenticated_user(
        "manager", permissions={"document.read", "document.write"}
    )

    def missing_template(_gxp_type):
        raise InspectionKeHoachKtTemplateAssetContractError(
            "exact template manifest corrupt"
        )

    monkeypatch.setattr(
        "backend.app.services.catalog.get_inspection_ke_hoach_kt_output_filename",
        missing_template,
    )
    with Session(engine) as session:
        with pytest.raises(
            InspectionKeHoachKtTemplateAssetContractError,
            match="exact template manifest corrupt",
        ):
            CatalogReadService()._build_case_contextual_document_actions(
                session, case_id=case_id, capa_cycles=[], user=user,
            )


def test_khkt_typed_action_url_stays_identical_to_registered_router(tmp_path, monkeypatch):
    app = FastAPI()
    register_document_routes(app, lambda: None)
    routes = [
        route for route in app.routes
        if getattr(route, "path", None) == KHKT_CASE_TYPED_RENDER_ROUTE
    ]
    assert len(routes) == 1
    assert routes[0].methods == {"POST"}
    engine, case_id = _seed_case(tmp_path, gxp_type="GLP")
    monkeypatch.setattr(
        "backend.app.services.catalog.load_inspection_ke_hoach_kt_payload_input",
        lambda *_args, **_kwargs: object(),
    )
    user = build_authenticated_user(
        "manager", permissions={"document.read", "document.write"},
    )
    with Session(engine) as session:
        _, action = _create_action(
            CatalogReadService()._build_case_contextual_document_actions(
                session, case_id=case_id, capa_cycles=[], user=user,
            )
        )
    assert action["create_endpoint"] == KHKT_CASE_TYPED_RENDER_ROUTE.format(case_id=case_id)


def test_khkt_typed_target_not_advertised_without_document_write(tmp_path):
    engine, case_id = _seed_case(tmp_path, gxp_type="GMP")
    user = build_authenticated_user("reader", permissions={"document.read"})
    with Session(engine) as session:
        _, create = _create_action(
            CatalogReadService()._build_case_contextual_document_actions(
                session, case_id=case_id, capa_cycles=[], user=user,
            )
        )
    assert create["available"] is False
    assert create["reason_code"] == "permission_denied"
    assert "create_endpoint" not in create
    assert "create_http_method" not in create


def test_khkt_typed_target_not_advertised_when_document_already_available(
    tmp_path, monkeypatch,
):
    engine, case_id = _seed_case(tmp_path, gxp_type="GSP")
    user = build_authenticated_user(
        "manager", permissions={"document.read", "document.write"}
    )
    service = CatalogReadService()
    original = service._serialize_document_checklist_items

    def document_already_present(*args, **kwargs):
        items = original(*args, **kwargs)
        for item in items:
            if item["family_code"] == "INSPECTION_KE_HOACH_KT":
                item["open_available"] = True
                item["detail_available"] = True
        return items

    monkeypatch.setattr(service, "_serialize_document_checklist_items", document_already_present)
    with Session(engine) as session:
        _, create = _create_action(
            service._build_case_contextual_document_actions(
                session, case_id=case_id, capa_cycles=[], user=user,
            )
        )
    assert create["available"] is False
    assert create["create_readiness"] == "READY_OPEN_HISTORY"
    assert create["reason_code"] == "ready_open_history"
    assert "create_endpoint" not in create
    assert "create_http_method" not in create


@pytest.mark.parametrize("gxp_type", ("GMP", "GLP", "GMPbb", "GSP"))
def test_supported_case_with_missing_business_input_remains_readable_but_create_blocked(
    tmp_path, gxp_type,
):
    engine, case_id = _seed_case(tmp_path, gxp_type=gxp_type)
    user = build_authenticated_user(
        "manager", permissions={"document.read", "document.write"},
    )
    with Session(engine) as session:
        workspace = CatalogReadService().get_case_workspace(
            session, case_id=case_id, user=user,
        )
    action = _create_action(workspace["contextual_document_actions"])[1]
    assert action["available"] is False
    assert action["reason_code"] == "business_input_not_ready"
    assert action["create_readiness"] == "BUSINESS_INPUT_NOT_READY"
    assert action["create_input_readiness"] == "CANONICAL_INPUT_BLOCKED"
    assert "inspection plan is missing" in action["create_input_blocked_reason"]
    assert "Dữ liệu nghiệp vụ" in action["disabled_reason"]
    assert "create_endpoint" not in action
    assert "create_http_method" not in action
    typed = ContextualDocumentActionAvailabilityRead(**action)
    assert typed.create_input_readiness == "CANONICAL_INPUT_BLOCKED"
    assert typed.create_input_blocked_reason == action["create_input_blocked_reason"]


def test_supported_case_scope_projection_error_is_not_misadvertised_as_render_ready(
    tmp_path, monkeypatch,
):
    from backend.app.document.payload_builders import DocumentPayloadBuildError
    engine, case_id = _seed_case(tmp_path, gxp_type="GMP")

    def fail_scope(*_args, **_kwargs):
        raise DocumentPayloadBuildError("canonical structured evaluation scope is unavailable")

    monkeypatch.setattr(
        "backend.app.services.catalog.load_inspection_ke_hoach_kt_payload_input",
        fail_scope,
    )
    user = build_authenticated_user(
        "manager", permissions={"document.read", "document.write"},
    )
    with Session(engine) as session:
        _, action = _create_action(
            CatalogReadService()._build_case_contextual_document_actions(
                session, case_id=case_id, capa_cycles=[], user=user,
            )
        )
    assert action["available"] is False
    assert action["create_readiness"] == "BUSINESS_INPUT_NOT_READY"
    assert "structured evaluation scope" in action["create_input_blocked_reason"]
    assert "create_endpoint" not in action


def test_case_input_preflight_does_not_run_for_read_only_user(tmp_path, monkeypatch):
    engine, case_id = _seed_case(tmp_path, gxp_type="GLP")

    def unexpected(*_args, **_kwargs):
        raise AssertionError("read-only user must not trigger document business input preflight")

    monkeypatch.setattr(
        "backend.app.services.catalog.load_inspection_ke_hoach_kt_payload_input",
        unexpected,
    )
    with Session(engine) as session:
        _, action = _create_action(
            CatalogReadService()._build_case_contextual_document_actions(
                session,
                case_id=case_id,
                capa_cycles=[],
                user=build_authenticated_user("reader", permissions={"document.read"}),
            )
        )
    assert action["available"] is False
    assert action["reason_code"] == "permission_denied"
    assert "create_endpoint" not in action
