"""QĐKT locality projection never treats unverified Case Site values as legacy row data."""
import pytest

from backend.app.document.inspection_ke_hoach_kt_province_projection import (
    InspectionKeHoachKtProvinceReference,
    InspectionKeHoachKtProvinceReferenceEntry,
)
from backend.app.document.inspection_qd_kt_locality_projection import (
    QdKtLocationBlocked, project_qdkt_locality_from_attested_legacy,
)


def _reference():
    return InspectionKeHoachKtProvinceReference(
        entries=(
            InspectionKeHoachKtProvinceReferenceEntry(1, "Hà Nội", None),
            InspectionKeHoachKtProvinceReferenceEntry(2, "Hồ Chí Minh", "TP"),
            InspectionKeHoachKtProvinceReferenceEntry(3, "Đà Nẵng", "TP "),
        ),
        vkn_central_institute_max_legacy_index=32,
    )


@pytest.mark.parametrize("name,diadiemx,index", [
    ("Hà Nội", "hà Nội", 1),
    ("Hồ Chí Minh", "thành phố Hồ Chí Minh", 2),
    ("Đà Nẵng", "thành phố Đà Nẵng", 3),
])
def test_attested_source_projection_does_not_authorize_case_render(name, diadiemx, index):
    out = project_qdkt_locality_from_attested_legacy(
        planning_row_province=name, source_attested=True, reference=_reference(),
    )
    assert out.diadiem == name
    assert out.diadiemx == diadiemx
    assert out.legacy_province_index == index
    assert out.case_source_equivalence_verified is False
    assert out.ready_to_render is False


@pytest.mark.parametrize("province,attested,error", [
    ("Hà Nội", False, "QDKT_PLANNING_ROW_PROVINCE_UNATTESTED"),
    ("", True, "QDKT_PLANNING_ROW_PROVINCE_MISSING"),
    (" Hà Nội", True, "QDKT_PLANNING_ROW_PROVINCE_UNNORMALIZED"),
    ("Unknown", True, "QDKT_LEGACY_PROVINCE_NOT_UNIQUE"),
])
def test_untrusted_provenance_is_blocked(province, attested, error):
    with pytest.raises(QdKtLocationBlocked, match=error):
        project_qdkt_locality_from_attested_legacy(
            planning_row_province=province, source_attested=attested, reference=_reference(),
        )
