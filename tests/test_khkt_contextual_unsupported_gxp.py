"""Case workspace KHKT capability must not break read-only Case access."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, Company, Site
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


@pytest.mark.parametrize("gxp_type", ("GMP", "GLP", "GMPbb", "GSP"))
def test_supported_gxp_keeps_existing_exact_khkt_create_contract(
    tmp_path, gxp_type,
):
    engine, case_id = _seed_case(tmp_path, gxp_type=gxp_type)
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
    assert create["reason_code"] is None
    assert create["create_readiness"] == "READY_CREATE_OPEN_HISTORY"
    assert create["create_gxp_type"] == gxp_type
    assert create["create_storage_scope"] == "inspection_folder"
    assert create["create_output_filename"] == get_inspection_ke_hoach_kt_output_filename(gxp_type)


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
