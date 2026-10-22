"""QĐKT institute selection reuses the verified 63-province legacy reference."""
import pytest
from backend.app.document.inspection_ke_hoach_kt_province_projection import (
    load_inspection_ke_hoach_kt_province_reference,
)
from backend.app.document.inspection_qd_kt_legacy_province_band import (
    qdkt_vkn_from_source_province,
)
from backend.app.document.inspection_qd_kt_vkn_authority import QdKtAuthorityBlocked


def test_legacy_geography_exact_boundary_and_vaccine_precedence():
    ref = load_inspection_ke_hoach_kt_province_reference()
    north = ref.entries[31]
    south = ref.entries[32]
    assert north.legacy_index == 32
    assert south.legacy_index == 33
    assert qdkt_vkn_from_source_province(
        manufacture_kind="MEDICINE", registered_province=north.province_name,
        reference=ref,
    ).branch == "NORTH"
    assert qdkt_vkn_from_source_province(
        manufacture_kind="MEDICINE", registered_province=south.province_name,
        reference=ref,
    ).branch == "SOUTH"
    assert qdkt_vkn_from_source_province(
        manufacture_kind="VACCINE_OR_BIOLOGICAL",
        registered_province=south.province_name, reference=ref,
    ).branch == "VACCINE"


@pytest.mark.parametrize("manufacture_kind,province,reason", [
    ("UNPROVEN", "Đà Nẵng", "MANUFACTURE_CLASSIFICATION_UNPROVEN"),
    ("MEDICINE", "", "REGISTERED_PROVINCE_MISSING"),
    ("MEDICINE", None, "REGISTERED_PROVINCE_MISSING"),
    ("MEDICINE", "Unsupported future province", "LEGACY_PROVINCE_MAPPING_UNPROVEN"),
])
def test_unsupported_classification_or_legacy_location_fails_closed(
    manufacture_kind, province, reason,
):
    with pytest.raises(QdKtAuthorityBlocked, match=reason):
        qdkt_vkn_from_source_province(
            manufacture_kind=manufacture_kind, registered_province=province
        )
