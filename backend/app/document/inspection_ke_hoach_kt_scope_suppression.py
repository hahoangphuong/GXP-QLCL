from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

from backend.app.document.docx_bookmark_range import (
    BookmarkRangeDeleteResult,
    delete_bookmark_ranges,
)
from backend.app.document.inspection_ke_hoach_kt_effective_template_contract import (
    InspectionKeHoachKtEffectiveTemplateContract,
)


_SECTION_TRIGGER_TEXT: tuple[tuple[str, str], ...] = (
    ("PVCepha", "Cephalosporin"),
    ("PVPeni", "Penicillin"),
    ("PVDuoclieu", "Dược liệu"),
    ("PVTiem", "Tiêm"),
    ("PVNhomat", "Nhỏ mắt"),
    ("PVNangmem", "Nang mềm"),
    ("PVSuibot", "Sủi bọt"),
)


@dataclass(frozen=True)
class InspectionKeHoachKtScopeSuppressionPlan:
    suppressed_sections: tuple[str, ...]
    delete_targets: tuple[str, ...]


@dataclass(frozen=True)
class InspectionKeHoachKtScopeSuppressionResult:
    plan: InspectionKeHoachKtScopeSuppressionPlan
    range_delete_result: BookmarkRangeDeleteResult


def build_inspection_ke_hoach_kt_scope_suppression_plan(
    *,
    daychuyen: str,
    contract: InspectionKeHoachKtEffectiveTemplateContract,
) -> InspectionKeHoachKtScopeSuppressionPlan:
    """Project the legacy i=3 scope-section delete decisions.

    The source uses InStr(..., vbTextCompare) against DC_cu. Preserve that
    narrow behavior here: case-insensitive substring membership only. Do not
    normalize accents, infer dosage-form synonyms, or inspect another field.
    Template geometry remains owned by the effective template contract.
    """

    haystack = str(daychuyen or "").casefold()
    suppressed: list[str] = []
    delete_targets: list[str] = []
    for section_name, trigger_text in _SECTION_TRIGGER_TEXT:
        targets = contract.scope_section_delete_targets.get(section_name, ())
        if not targets:
            continue
        if trigger_text.casefold() in haystack:
            continue
        suppressed.append(section_name)
        delete_targets.extend(targets)
    return InspectionKeHoachKtScopeSuppressionPlan(
        suppressed_sections=tuple(suppressed),
        delete_targets=tuple(delete_targets),
    )


def apply_inspection_ke_hoach_kt_scope_suppression(
    root: ET.Element,
    *,
    daychuyen: str,
    contract: InspectionKeHoachKtEffectiveTemplateContract,
) -> InspectionKeHoachKtScopeSuppressionResult:
    plan = build_inspection_ke_hoach_kt_scope_suppression_plan(
        daychuyen=daychuyen,
        contract=contract,
    )
    delete_result = delete_bookmark_ranges(
        root,
        plan.delete_targets,
        missing_ok=False,
    )
    return InspectionKeHoachKtScopeSuppressionResult(
        plan=plan,
        range_delete_result=delete_result,
    )
