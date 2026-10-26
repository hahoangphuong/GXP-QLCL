"""Ensure the Case i=2 QĐKT manifest cannot silently masquerade as another source."""
import json

import pytest

from backend.app.document.inspection_qd_kt_template_asset_contract import (
    CONTRACT_PATH,
    InspectionQdKtTemplateAssetContractError,
    load_inspection_qd_kt_template_assets,
)


def test_pinned_i2_manifest_declares_all_four_templates():
    assets = load_inspection_qd_kt_template_assets()
    assert {a.gxp_type for a in assets} == {"GMP", "GLP", "GMPbb", "GSP"}


@pytest.mark.parametrize("mutation", [
    {"schema_version": "inspection-qd-kt-template-assets-v2"},
    {"schema_version": None},
    {"source_variant": "recordform_get_tpl_case_3"},
    {"source_variant": None},
    {"family_code": "INSPECTION_KHKT"},
])
def test_changed_manifest_origin_fails_closed(tmp_path, mutation):
    data = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    data.update(mutation)
    path = tmp_path / "changed-manifest.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(InspectionQdKtTemplateAssetContractError):
        load_inspection_qd_kt_template_assets(path)


def test_non_object_manifest_fails_closed(tmp_path):
    path = tmp_path / "wrong-shape.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(InspectionQdKtTemplateAssetContractError):
        load_inspection_qd_kt_template_assets(path)
