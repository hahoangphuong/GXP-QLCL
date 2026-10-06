from __future__ import annotations

import pytest

from backend.app.document.inspection_ke_hoach_kt_province_projection import (
    CENTRAL_DRUG_AUTHORITY,
    HCM_DRUG_AUTHORITY,
    REFERENCE_WORKBOOK_SHA256,
    VACCINE_AUTHORITY,
    InspectionKeHoachKtProvinceProjectionError,
    load_inspection_ke_hoach_kt_province_reference,
    project_inspection_ke_hoach_kt_province,
)


def test_province_reference_locks_exact_legacy_geometry_and_provenance():
    reference = load_inspection_ke_hoach_kt_province_reference()

    assert len(reference.entries) == 63
    assert [entry.legacy_index for entry in reference.entries] == list(range(1, 64))
    assert reference.vkn_central_institute_max_legacy_index == 32
    assert REFERENCE_WORKBOOK_SHA256 == "c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d"
    assert reference.entries[31].province_name == "Đà Nẵng"
    assert reference.entries[32].province_name == "Quảng Nam"


def test_province_projection_reproduces_diadiemx_prefix_and_vkn_boundary():
    danang = project_inspection_ke_hoach_kt_province(
        province_name="Đà Nẵng",
        daychuyen="Viên nén",
    )
    quangnam = project_inspection_ke_hoach_kt_province(
        province_name="Quảng Nam",
        daychuyen="Viên nén",
    )

    assert danang.diadiemx == "thành phố Đà Nẵng"
    assert danang.legacy_index == 32
    assert danang.vknx == CENTRAL_DRUG_AUTHORITY
    assert quangnam.diadiemx == "tỉnh Quảng Nam"
    assert quangnam.legacy_index == 33
    assert quangnam.vknx == HCM_DRUG_AUTHORITY


def test_province_projection_preserves_historical_ho_chi_minh_tp_rewrite():
    projection = project_inspection_ke_hoach_kt_province(
        province_name="TP Hồ Chí Minh",
        daychuyen="Viên nang",
    )

    assert projection.legacy_index == 45
    assert projection.diadiemx == "thành phố Hồ Chí Minh"
    assert projection.vknx == HCM_DRUG_AUTHORITY


@pytest.mark.parametrize("signal", ["vắc xin", "VẮCXIN", "vacxin", "VAC XIN"])
def test_vaccine_scope_overrides_province_authority_branch(signal):
    projection = project_inspection_ke_hoach_kt_province(
        province_name="Cà Mau",
        daychuyen=f"Sản xuất {signal} và sinh phẩm",
    )

    assert projection.vknx == VACCINE_AUTHORITY


def test_province_lookup_matches_excel_text_case_insensitively_but_does_not_fuzzy_match():
    projection = project_inspection_ke_hoach_kt_province(
        province_name="hà nội",
        daychuyen="Viên nén",
    )
    assert projection.legacy_index == 1
    assert projection.diadiemx == "thành phố hà nội"

    with pytest.raises(
        InspectionKeHoachKtProvinceProjectionError,
        match="outside the source-proven",
    ):
        project_inspection_ke_hoach_kt_province(
            province_name="Ha Noi",
            daychuyen="Viên nén",
        )


def test_unknown_future_province_fails_closed_instead_of_reusing_legacy_index_zero_fallback():
    with pytest.raises(
        InspectionKeHoachKtProvinceProjectionError,
        match="outside the source-proven",
    ):
        project_inspection_ke_hoach_kt_province(
            province_name="Tỉnh mới chưa được phê duyệt",
            daychuyen="Viên nén",
        )
