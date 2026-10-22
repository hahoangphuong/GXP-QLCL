"""QĐKT institution-selection regression based on confirmed owner rules and VBA prose."""
import pytest

from backend.app.document.inspection_qd_kt_vkn_authority import (
    QdKtAuthorityBlocked, select_qdkt_vkn_authority,
)


@pytest.mark.parametrize("location", [
    "DA_NANG_AND_NORTH", "SOUTH_OF_DA_NANG", "UNPROVEN",
])
def test_vaccine_biological_institution_overrides_geography(location):
    selected = select_qdkt_vkn_authority(
        manufacture_kind="VACCINE_OR_BIOLOGICAL", geography=location,
    )
    assert selected.branch == "VACCINE"
    assert selected.vkn == "VKĐQG Vắc xin & Sinh phẩm y tế"
    assert selected.vknx == "Viện kiểm định Quốc gia Vắc xin & Sinh phẩm y tế"


def test_medicine_danang_and_north_uses_central_institute():
    selected = select_qdkt_vkn_authority(
        manufacture_kind="MEDICINE", geography="DA_NANG_AND_NORTH",
    )
    assert selected.branch == "NORTH"
    assert selected.vkn == "VKN thuốc Trung ương"
    assert selected.vknx == "Viện Kiểm nghiệm thuốc Trung ương"


def test_medicine_south_uses_hcm_institute():
    selected = select_qdkt_vkn_authority(
        manufacture_kind="MEDICINE", geography="SOUTH_OF_DA_NANG",
    )
    assert selected.branch == "SOUTH"
    assert selected.vkn == "VKN thuốc Tp. Hồ Chí Minh"
    assert selected.vknx == "Viện Kiểm nghiệm thuốc Tp. Hồ Chí Minh"


@pytest.mark.parametrize("kind,geography,code", [
    ("UNPROVEN", "DA_NANG_AND_NORTH", "MANUFACTURE_CLASSIFICATION_UNPROVEN"),
    ("UNPROVEN", "UNPROVEN", "MANUFACTURE_CLASSIFICATION_UNPROVEN"),
    ("MEDICINE", "UNPROVEN", "GEOGRAPHY_CLASSIFICATION_UNPROVEN"),
    ("", "SOUTH_OF_DA_NANG", "MANUFACTURE_CLASSIFICATION_UNPROVEN"),
    ("MEDICINE", "province named Hà Nội", "GEOGRAPHY_CLASSIFICATION_UNPROVEN"),
])
def test_unproven_source_classification_never_guesses_institution(kind, geography, code):
    with pytest.raises(QdKtAuthorityBlocked, match=code):
        select_qdkt_vkn_authority(manufacture_kind=kind, geography=geography)
