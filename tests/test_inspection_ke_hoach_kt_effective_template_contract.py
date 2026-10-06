from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

import backend.app.document.inspection_ke_hoach_kt_effective_template_contract as contract_module
from backend.app.document.inspection_ke_hoach_kt_effective_template_contract import (
    InspectionKeHoachKtEffectiveTemplateContractError,
    build_inspection_ke_hoach_kt_effective_template_contract,
)

BOOKMARKS = {
    "GLP": (
        "Fulldate", "TenCoSo1", "DiaChiCoSo", "QDKT", "NgayQDKT", "DayChuyen",
        "TT1x", "TT2x", "TT3x", "TT3Del", "TT_ext", "TT_VKNx", "VKNx",
        "TT_SYTx", "Diadiemx", "Diadiemx1",
    ),
    "GMP": (
        "Fulldate", "TenCoSo1", "DiaChiCoSo", "QDKT", "NgayQDKT", "DayChuyen",
        "GioiHanPvi", "GhPviDG", "TieuchuanKT", "TT1x", "TT2x", "TT3x", "TT3Del",
        "TT_ext", "TT_VKNx", "VKNx", "TT_SYTx", "Diadiemx", "Diadiemx1", "DGMoi",
        "PVDuoclieu1", "PVCepha1", "PVPeni1", "PVSuibot", "PVNangmem1", "PVDuoclieu2",
        "PVNangmem2", "PVTiem1", "PVNhomat", "PVCepha2", "PVTiem2", "PVPeni2", "PVTiem3",
    ),
    "GMPbb": (
        "Fulldate", "TenCoSo1", "DiaChiCoSo", "DayChuyen", "TT1x", "TT2x", "TT3x",
        "TT3Del", "TT_ext", "TT_VKNx", "VKNx", "TT_SYTx", "Diadiemx", "Diadiemx1",
    ),
    "GSP": (
        "Fulldate", "TenCoSo1", "DiaChiCoSo", "DayChuyen", "TT1x", "TT2x", "TT3x",
        "TT3Del", "TT_ext", "TT_SYTx", "Diadiemx", "Diadiemx1",
    ),
}


def _template(
    gxp_type: str,
    *,
    bookmarks: tuple[str, ...] | None = None,
    tt_ext_text: str = " – Thành viên;",
) -> bytes:
    names = BOOKMARKS[gxp_type] if bookmarks is None else bookmarks
    bookmark_xml = "".join(
        f'<w:bookmarkStart w:id="{index}" w:name="{name}"/>'
        f'<w:r><w:t>{tt_ext_text if name == "TT_ext" else name}</w:t></w:r>'
        f'<w:bookmarkEnd w:id="{index}"/>'
        for index, name in enumerate(names, 1)
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body><w:p>{bookmark_xml}</w:p></w:body></w:document>'
    ).encode("utf-8")
    target = BytesIO()
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)
    return target.getvalue()


@pytest.mark.parametrize("gxp_type", ["GMP", "GLP", "GMPbb", "GSP"])
def test_exact_khkt_geometry_resolves_effective_i3_targets(gxp_type: str):
    contract = build_inspection_ke_hoach_kt_effective_template_contract(
        gxp_type=gxp_type,
        template_bytes=_template(gxp_type),
    )
    assert contract.scalar_targets["Fulldate"] == ("Fulldate",)
    assert contract.scalar_targets["Tencoso"] == ("TenCoSo1",)
    assert contract.scalar_targets["Diachicoso"] == ("DiaChiCoSo",)
    assert contract.scalar_targets["Diadiem"] == ()
    # VBA writes Diadiemx1..3; only x1 exists in the exact audited geometry.
    # The bare Diadiemx bookmark is not targeted by that ranged helper call.
    assert contract.scalar_targets["Diadiemx"] == ("Diadiemx1",)
    assert contract.scalar_targets["HsDK"] == ()
    assert contract.scalar_targets["NgaynopHsDK"] == ()
    assert contract.scalar_targets["Daychuyen"] == ("DayChuyen",)
    assert contract.third_member_delete_target == "TT3Del"
    assert contract.team_separator_text == " – Thành viên;"


def test_gmp_is_the_only_khkt_geometry_with_scope_section_delete_targets():
    gmp = build_inspection_ke_hoach_kt_effective_template_contract(
        gxp_type="GMP", template_bytes=_template("GMP")
    )
    assert gmp.scope_section_delete_targets == {
        "PVCepha": ("PVCepha1", "PVCepha2"),
        "PVPeni": ("PVPeni1", "PVPeni2"),
        "PVDuoclieu": ("PVDuoclieu1", "PVDuoclieu2"),
        "PVTiem": ("PVTiem1", "PVTiem2", "PVTiem3"),
        "PVNhomat": ("PVNhomat",),
        "PVNangmem": ("PVNangmem1", "PVNangmem2"),
        "PVSuibot": ("PVSuibot",),
    }
    for gxp_type in ("GLP", "GMPbb", "GSP"):
        contract = build_inspection_ke_hoach_kt_effective_template_contract(
            gxp_type=gxp_type, template_bytes=_template(gxp_type)
        )
        assert contract.scope_section_delete_targets == {}


def test_effective_contract_preserves_variant_specific_optional_targets():
    glp = build_inspection_ke_hoach_kt_effective_template_contract(
        gxp_type="GLP", template_bytes=_template("GLP")
    )
    gmpbb = build_inspection_ke_hoach_kt_effective_template_contract(
        gxp_type="GMPbb", template_bytes=_template("GMPbb")
    )
    gsp = build_inspection_ke_hoach_kt_effective_template_contract(
        gxp_type="GSP", template_bytes=_template("GSP")
    )
    assert glp.scalar_targets["QDKT"] == ("QDKT",)
    assert glp.scalar_targets["NgayQDKT"] == ("NgayQDKT",)
    assert gmpbb.scalar_targets["QDKT"] == ()
    assert gsp.scalar_targets["VKNx"] == ()
    assert gmpbb.optional_team_targets == ("TT_VKNx", "TT_SYTx")
    assert gsp.optional_team_targets == ("TT_SYTx",)


def test_effective_contract_fails_closed_on_bookmark_geometry_drift():
    drifted = tuple("TieuchuanKX" if name == "TieuchuanKT" else name for name in BOOKMARKS["GMP"])
    with pytest.raises(
        InspectionKeHoachKtEffectiveTemplateContractError,
        match="bookmark geometry changed",
    ):
        build_inspection_ke_hoach_kt_effective_template_contract(
            gxp_type="GMP", template_bytes=_template("GMP", bookmarks=drifted)
        )


def test_effective_contract_rejects_unsupported_gxp_type():
    with pytest.raises(
        InspectionKeHoachKtEffectiveTemplateContractError,
        match="Unsupported KHKT GxP type",
    ):
        build_inspection_ke_hoach_kt_effective_template_contract(
            gxp_type="GMPnn", template_bytes=_template("GMP")
        )



@pytest.mark.parametrize("gxp_type", ["GMP", "GLP", "GMPbb", "GSP"])
def test_effective_khkt_input_coverage_has_proven_owner_for_every_active_source(gxp_type: str):
    contract = build_inspection_ke_hoach_kt_effective_template_contract(
        gxp_type=gxp_type,
        template_bytes=_template(gxp_type),
    )

    assert contract.input_owner_by_source
    assert "Fulldate" in contract.input_owner_by_source
    assert "Tencoso" in contract.input_owner_by_source
    assert "Diachicoso" in contract.input_owner_by_source
    assert "Daychuyen" in contract.input_owner_by_source
    assert "TT3Del" in contract.input_owner_by_source
    assert set(contract.input_owner_by_source).isdisjoint(contract.legacy_noop_scalar_sources)


def test_effective_khkt_input_coverage_records_variant_legacy_noops():
    gmp = build_inspection_ke_hoach_kt_effective_template_contract(
        gxp_type="GMP",
        template_bytes=_template("GMP"),
    )
    gsp = build_inspection_ke_hoach_kt_effective_template_contract(
        gxp_type="GSP",
        template_bytes=_template("GSP"),
    )

    assert {"Diadiem", "HsDK", "NgaynopHsDK"}.issubset(gmp.legacy_noop_scalar_sources)
    assert {"QDKT", "NgayQDKT", "GioiHanPvi", "TieuchuanKT", "VKNx"}.issubset(
        gsp.legacy_noop_scalar_sources
    )
    assert "PVTiem" in gmp.input_owner_by_source
    assert "PVTiem" not in gsp.input_owner_by_source


def test_effective_khkt_input_coverage_fails_closed_for_new_unowned_active_source(monkeypatch):
    monkeypatch.setitem(
        contract_module._SCALAR_SOURCE_TARGETS,
        "UnownedFutureSource",
        ("Fulldate",),
    )

    with pytest.raises(
        InspectionKeHoachKtEffectiveTemplateContractError,
        match="without proven owners: UnownedFutureSource",
    ):
        build_inspection_ke_hoach_kt_effective_template_contract(
            gxp_type="GMP",
            template_bytes=_template("GMP"),
        )
