from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import DocumentVariantType
from backend.app.db.models.phase1 import TemplateBinding, TemplateDefinition
from backend.app.document.contextual_actions import get_case_document_context_spec
from backend.app.document.inspection_ke_hoach_kt_template_asset_contract import (
    get_inspection_ke_hoach_kt_template_asset,
    load_inspection_ke_hoach_kt_template_assets,
)
from backend.app.document.template_binary import build_template_binary_requirement
from backend.app.document.template_binary_binding import assign_template_binary_binding


def _definition() -> TemplateDefinition:
    return TemplateDefinition(
        family_code="INSPECTION_KE_HOACH_KT",
        document_type_code="inspection_ke_hoach_kt",
        source_application="Word",
        storage_scope="inspection_folder",
        legacy_host_procedure="RecordForm.CreateFile",
        legacy_case_number=3,
        variant_type=DocumentVariantType.EDITABLE_DOCX,
        template_name="3. Kế hoạch kiểm tra {GP}.dotx",
        template_pattern="3. Kế hoạch kiểm tra {GP}.dotx",
        bookmark_contract=None,
        is_active=True,
    )


def _allocation(definition_id: str, binding_id: str | None, gxp_type: str = "GMP"):
    return SimpleNamespace(
        prepared=SimpleNamespace(
            persisted_state=SimpleNamespace(
                template_definition_id=definition_id,
                template_binding_id=binding_id,
            ),
            generation_plan=SimpleNamespace(
                request=SimpleNamespace(gxp_type=gxp_type),
                template=SimpleNamespace(
                    family_code="INSPECTION_KE_HOACH_KT",
                    template_pattern="3. Kế hoạch kiểm tra {GP}.dotx",
                ),
            ),
        )
    )


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_khkt_asset_contract_contains_authoritative_four_gxp_mappings():
    assets = {
        asset.gxp_type: asset
        for asset in load_inspection_ke_hoach_kt_template_assets()
    }

    assert set(assets) == {"GMP", "GLP", "GMPbb", "GSP"}
    for gxp_type, asset in assets.items():
        assert asset.storage_root == "template"
        assert asset.storage_relative_path == f"3. Kế hoạch kiểm tra {gxp_type}.dotx"
        assert asset.filename == f"3. Kế hoạch kiểm tra {gxp_type}.dotx"
        assert len(asset.checksum_sha256) == 64


@pytest.mark.parametrize("gxp_type", ["GMP", "GLP", "GMPbb", "GSP"])
def test_khkt_exact_binding_must_match_immutable_asset_contract(gxp_type):
    session = _session()
    try:
        definition = _definition()
        session.add(definition)
        session.flush()
        binding = TemplateBinding(
            family_code=definition.family_code,
            template_definition_id=definition.id,
            gxp_type=gxp_type,
            legacy_mode=None,
            storage_scope=definition.storage_scope,
            is_active=True,
        )
        session.add(binding)
        session.flush()
        asset = get_inspection_ke_hoach_kt_template_asset(gxp_type)
        assign_template_binary_binding(
            session,
            template_binding_id=binding.id,
            storage_root=asset.storage_root,
            storage_relative_path=asset.storage_relative_path,
            original_filename=asset.filename,
            checksum_sha256=asset.checksum_sha256,
        )

        requirement = build_template_binary_requirement(
            session,
            _allocation(definition.id, binding.id, gxp_type),
        )

        assert requirement.readiness_status == "direct_stream_ready"
        assert requirement.storage_relative_path == asset.storage_relative_path
        assert requirement.checksum_sha256 == asset.checksum_sha256
    finally:
        session.close()


def test_khkt_generic_definition_locator_cannot_replace_exact_gxp_binding():
    session = _session()
    try:
        definition = _definition()
        definition.template_storage_root = "template"
        definition.template_storage_relative_path = "generic.dotx"
        session.add(definition)
        session.flush()

        requirement = build_template_binary_requirement(
            session,
            _allocation(definition.id, None, "GMP"),
        )

        assert requirement.readiness_status == "missing_exact_template_binding"
        assert requirement.storage_relative_path is None
    finally:
        session.close()


def test_khkt_mismatched_exact_binding_fails_closed():
    session = _session()
    try:
        definition = _definition()
        session.add(definition)
        session.flush()
        binding = TemplateBinding(
            family_code=definition.family_code,
            template_definition_id=definition.id,
            gxp_type="GMP",
            legacy_mode=None,
            storage_scope=definition.storage_scope,
            is_active=True,
        )
        session.add(binding)
        session.flush()
        asset = get_inspection_ke_hoach_kt_template_asset("GMP")
        assign_template_binary_binding(
            session,
            template_binding_id=binding.id,
            storage_root="template",
            storage_relative_path=asset.storage_relative_path,
            original_filename=asset.filename,
            checksum_sha256="0" * 64,
        )

        requirement = build_template_binary_requirement(
            session,
            _allocation(definition.id, binding.id, "GMP"),
        )

        assert requirement.readiness_status == "invalid_template_binding"
        assert requirement.storage_relative_path is None
    finally:
        session.close()


def test_khkt_contextual_create_reports_frontend_handler_blocker():
    spec = get_case_document_context_spec("INSPECTION_KE_HOACH_KT")

    assert spec is not None
    assert spec.create_readiness == "FRONTEND_CREATE_ACTION_MISSING"
