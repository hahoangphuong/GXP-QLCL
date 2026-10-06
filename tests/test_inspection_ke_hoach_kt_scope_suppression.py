from __future__ import annotations

from xml.etree import ElementTree as ET

from backend.app.document.inspection_ke_hoach_kt_effective_template_contract import (
    InspectionKeHoachKtEffectiveTemplateContract,
)
from backend.app.document.inspection_ke_hoach_kt_scope_suppression import (
    apply_inspection_ke_hoach_kt_scope_suppression,
    build_inspection_ke_hoach_kt_scope_suppression_plan,
)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}


def _contract(
    targets: dict[str, tuple[str, ...]],
) -> InspectionKeHoachKtEffectiveTemplateContract:
    return InspectionKeHoachKtEffectiveTemplateContract(
        gxp_type="GMP",
        template_bookmarks=tuple(
            target
            for section_targets in targets.values()
            for target in section_targets
        ),
        scalar_targets={},
        optional_team_targets=(),
        third_member_delete_target="TT3Del",
        scope_section_delete_targets=targets,
    )


def _xml(body: str) -> ET.Element:
    return ET.fromstring(
        f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'
    )


def _text(root: ET.Element) -> list[str]:
    return [
        "".join(text.text or "" for text in paragraph.findall(".//w:t", NS))
        for paragraph in root.findall(".//w:p", NS)
    ]


def test_scope_suppression_preserves_vbtextcompare_substring_semantics():
    contract = _contract(
        {
            "PVCepha": ("PVCepha1", "PVCepha2"),
            "PVPeni": ("PVPeni1", "PVPeni2"),
            "PVDuoclieu": ("PVDuoclieu1", "PVDuoclieu2"),
            "PVTiem": ("PVTiem1", "PVTiem2", "PVTiem3"),
            "PVNhomat": ("PVNhomat",),
            "PVNangmem": ("PVNangmem1", "PVNangmem2"),
            "PVSuibot": ("PVSuibot",),
        }
    )

    plan = build_inspection_ke_hoach_kt_scope_suppression_plan(
        daychuyen="DƯỢC LIỆU; cephalosporin; thuốc TIÊM; nang mềm",
        contract=contract,
    )

    assert plan.suppressed_sections == ("PVPeni", "PVNhomat", "PVSuibot")
    assert plan.delete_targets == (
        "PVPeni1",
        "PVPeni2",
        "PVNhomat",
        "PVSuibot",
    )


def test_scope_suppression_is_noop_when_template_has_no_section_targets():
    contract = _contract({})

    plan = build_inspection_ke_hoach_kt_scope_suppression_plan(
        daychuyen="",
        contract=contract,
    )

    assert plan.suppressed_sections == ()
    assert plan.delete_targets == ()


def test_scope_suppression_applies_only_planned_structural_range():
    contract = _contract({"PVCepha": ("PVCepha1",)})
    root = _xml(
        '<w:p><w:bookmarkStart w:id="1" w:name="PVCepha1"/>'
        '<w:r><w:t>delete cephalosporin section</w:t></w:r></w:p>'
        '<w:p><w:bookmarkEnd w:id="1"/><w:r><w:t>keep penicillin section</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>keep footer</w:t></w:r></w:p>'
    )

    result = apply_inspection_ke_hoach_kt_scope_suppression(
        root,
        daychuyen="Penicillin",
        contract=contract,
    )

    assert result.plan.suppressed_sections == ("PVCepha",)
    assert result.range_delete_result.planned_bookmarks == ("PVCepha1",)
    assert result.range_delete_result.deleted_paragraph_count == 1
    assert _text(root) == ["keep penicillin section", "keep footer"]
