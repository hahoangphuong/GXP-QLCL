from __future__ import annotations

from datetime import date
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from backend.app.document.inspection_ke_hoach_kt_effective_template_contract import (
    build_inspection_ke_hoach_kt_effective_template_contract,
)
from backend.app.document.inspection_ke_hoach_kt_payload_composer import (
    InspectionKeHoachKtPayloadComposerError,
    compose_inspection_ke_hoach_kt_render_plan,
)
from backend.app.document.inspection_ke_hoach_kt_payload_input import (
    InspectionKeHoachKtPayloadInput,
)
from backend.app.document.inspection_ke_hoach_kt_team_projection import (
    InspectionKeHoachKtTeamMemberInput,
)

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
BOOKMARKS = (
    "Fulldate", "TenCoSo1", "DiaChiCoSo", "QDKT", "NgayQDKT", "DayChuyen",
    "GioiHanPvi", "GhPviDG", "TieuchuanKT", "TT1x", "TT2x", "TT3x", "TT3Del",
    "TT_ext", "TT_VKNx", "VKNx", "TT_SYTx", "Diadiemx", "Diadiemx1", "DGMoi",
    "PVDuoclieu1", "PVCepha1", "PVPeni1", "PVSuibot", "PVNangmem1", "PVDuoclieu2",
    "PVNangmem2", "PVTiem1", "PVNhomat", "PVCepha2", "PVTiem2", "PVPeni2", "PVTiem3",
)


def _template() -> bytes:
    xml = "".join(
        f'<w:bookmarkStart w:id="{index}" w:name="{name}"/>'
        f'<w:r><w:t>{" – Thành viên;" if name == "TT_ext" else name}</w:t></w:r>'
        f'<w:bookmarkEnd w:id="{index}"/>'
        for index, name in enumerate(BOOKMARKS, 1)
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{WORD_NS}"><w:body><w:p>{xml}</w:p></w:body></w:document>'
    ).encode()
    target = BytesIO()
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document)
    return target.getvalue()


def _member(name: str, order: int) -> InspectionKeHoachKtTeamMemberInput:
    return InspectionKeHoachKtTeamMemberInput(
        display_name=name,
        sort_order=order,
        role_code="LEADER" if order == 1 else "SECRETARY" if order == 2 else "MEMBER",
        identity_kind="INSPECTOR_PROFILE",
        roster_group="DRUG_ADMINISTRATION_AND_TRADITIONAL_MEDICINE",
    )


def _payload(**overrides) -> InspectionKeHoachKtPayloadInput:
    values = dict(
        case_id="case-1",
        gxp_type="GMP",
        site_name="Cơ sở A",
        site_address="Dòng 1\r\nDòng 2",
        province_name="Hà Nội",
        dossier_code=None,
        submitted_on=None,
        decision_reference="123/QĐ-QLD",
        decision_date=date(2026, 9, 20),
        applicable_standard="WHO-GMP",
        daychuyen="Cephalosporin; Tiêm",
        gioi_han_pvi="Không",
        diadiemx="thành phố Hà Nội",
        vknx="Viện Kiểm nghiệm thuốc Trung ương",
        team_members=(_member("A", 1), _member("B", 2)),
        generated_on=date(2026, 10, 6),
        fulldate="ngày 06 tháng 10 năm 2026",
    )
    values.update(overrides)
    return InspectionKeHoachKtPayloadInput(**values)


def test_khkt_composer_emits_only_effective_physical_bookmarks_and_structural_deletes():
    contract = build_inspection_ke_hoach_kt_effective_template_contract(
        gxp_type="GMP",
        template_bytes=_template(),
    )

    plan = compose_inspection_ke_hoach_kt_render_plan(
        payload=_payload(),
        contract=contract,
    )

    assert plan.bookmark_replacements["Fulldate"] == "ngày 06 tháng 10 năm 2026"
    assert plan.bookmark_replacements["TenCoSo1"] == "Cơ sở A"
    assert plan.bookmark_replacements["DiaChiCoSo"] == "Dòng 1;Dòng 2"
    assert plan.bookmark_replacements["QDKT"] == "123/QĐ-QLD"
    assert plan.bookmark_replacements["NgayQDKT"] == "20/09/2026"
    assert plan.bookmark_replacements["DayChuyen"] == "Cephalosporin; Tiêm"
    assert plan.bookmark_replacements["TT1x"] == "A"
    assert plan.bookmark_replacements["TT2x"] == "B"
    assert plan.bookmark_replacements["TT3x"] == ""
    assert plan.bookmark_replacements["Diadiemx1"] == "thành phố Hà Nội"
    assert "HsDK" not in plan.bookmark_replacements
    assert set(plan.delete_targets) == {
        "TT3Del",
        "PVPeni1", "PVPeni2",
        "PVDuoclieu1", "PVDuoclieu2",
        "PVNhomat",
        "PVNangmem1", "PVNangmem2",
        "PVSuibot",
    }


def test_khkt_composer_uses_template_owned_tt_ext_for_tail_members():
    contract = build_inspection_ke_hoach_kt_effective_template_contract(
        gxp_type="GMP",
        template_bytes=_template(),
    )
    payload = _payload(team_members=(_member("A", 1), _member("B", 2), _member("C", 3), _member("D", 4)))

    plan = compose_inspection_ke_hoach_kt_render_plan(payload=payload, contract=contract)

    assert plan.bookmark_replacements["TT3x"] == "C – Thành viên;\r\nD"
    assert "TT3Del" not in plan.delete_targets


def test_khkt_composer_rejects_payload_template_gxp_mismatch():
    contract = build_inspection_ke_hoach_kt_effective_template_contract(
        gxp_type="GMP",
        template_bytes=_template(),
    )
    with pytest.raises(
        InspectionKeHoachKtPayloadComposerError,
        match="does not match",
    ):
        compose_inspection_ke_hoach_kt_render_plan(
            payload=_payload(gxp_type="GLP"),
            contract=contract,
        )
