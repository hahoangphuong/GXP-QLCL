from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZipFile

FAMILY_CODE = "INSPECTION_KE_HOACH_KT"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W_NAME = f"{{{WORD_NS}}}name"


class InspectionKeHoachKtEffectiveTemplateContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class InspectionKeHoachKtEffectiveTemplateContract:
    gxp_type: str
    template_bookmarks: tuple[str, ...]
    scalar_targets: dict[str, tuple[str, ...]]
    optional_team_targets: tuple[str, ...]
    third_member_delete_target: str
    scope_section_delete_targets: dict[str, tuple[str, ...]]
    input_owner_by_source: dict[str, str]
    legacy_noop_scalar_sources: tuple[str, ...]


# This is the *effective* i=3 contract after VBA best-effort operations are
# intersected with each immutable template asset. Missing bookmarks are legacy
# no-ops, not missing business inputs.
_SCALAR_SOURCE_TARGETS: dict[str, tuple[str, ...]] = {
    "Fulldate": ("Fulldate",),
    "Tencoso": tuple(f"Tencoso{i}" for i in range(1, 9)),
    "Diadiem": ("Diadiem",),
    "Diadiemx": tuple(f"Diadiemx{i}" for i in range(1, 4)),
    "Diachicoso": ("Diachicoso",),
    "HsDK": ("HsDK",),
    "NgaynopHsDK": ("NgaynopHsDK",),
    "VKNx": ("VKNx",),
    "TT1x": ("TT1x",),
    "TT2x": ("TT2x",),
    "TT3x": ("TT3x",),
    "TT_VKNx": ("TT_VKNx",),
    "TT_SYTx": ("TT_SYTx",),
    "QDKT": ("QDKT",),
    "NgayQDKT": ("NgayQDKT",),
    "Daychuyen": ("Daychuyen",),
    "GioiHanPvi": ("GioiHanPvi",),
    "TieuchuanKT": ("TieuchuanKT",),
}

_PROVEN_INPUT_OWNER_BY_SOURCE: dict[str, str] = {
    "Fulldate": "backend.app.document.inspection_ke_hoach_kt_generation_date",
    "Tencoso": "Site.site_name",
    "Diadiem": "Site.province_name",
    "Diadiemx": "backend.app.document.inspection_ke_hoach_kt_province_projection",
    "Diachicoso": "Site.site_address",
    "HsDK": "CaseApplication.dossier_code",
    "NgaynopHsDK": "CaseApplication.submitted_on",
    "VKNx": "backend.app.document.inspection_ke_hoach_kt_province_projection",
    "TT1x": "backend.app.document.inspection_ke_hoach_kt_team_projection",
    "TT2x": "backend.app.document.inspection_ke_hoach_kt_team_projection",
    "TT3x": "backend.app.document.inspection_ke_hoach_kt_team_projection",
    "TT_VKNx": "backend.app.document.inspection_ke_hoach_kt_team_projection",
    "TT_SYTx": "backend.app.document.inspection_ke_hoach_kt_team_projection",
    "QDKT": "InspectionPlan.decision_reference",
    "NgayQDKT": "InspectionPlan.decision_date",
    "Daychuyen": "CaseEvaluationScope projection: DC_cu",
    "GioiHanPvi": "CaseEvaluationScope projection: GHanDC",
    "TieuchuanKT": "Case.applicable_standard",
    "TT3Del": "backend.app.document.inspection_ke_hoach_kt_team_projection",
    "PVCepha": "backend.app.document.inspection_ke_hoach_kt_scope_suppression",
    "PVPeni": "backend.app.document.inspection_ke_hoach_kt_scope_suppression",
    "PVDuoclieu": "backend.app.document.inspection_ke_hoach_kt_scope_suppression",
    "PVTiem": "backend.app.document.inspection_ke_hoach_kt_scope_suppression",
    "PVNhomat": "backend.app.document.inspection_ke_hoach_kt_scope_suppression",
    "PVNangmem": "backend.app.document.inspection_ke_hoach_kt_scope_suppression",
    "PVSuibot": "backend.app.document.inspection_ke_hoach_kt_scope_suppression",
}

_SCOPE_DELETE_SOURCE_TARGETS: dict[str, tuple[str, ...]] = {
    "PVCepha": ("PVCepha1", "PVCepha2"),
    "PVPeni": ("PVPeni1", "PVPeni2"),
    "PVDuoclieu": ("PVDuoclieu1", "PVDuoclieu2"),
    "PVTiem": ("PVTiem1", "PVTiem2", "PVTiem3"),
    "PVNhomat": ("PVNhomat",),
    "PVNangmem": ("PVNangmem1", "PVNangmem2"),
    "PVSuibot": ("PVSuibot",),
}

_EXPECTED_BOOKMARKS: dict[str, tuple[str, ...]] = {
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


def _bookmark_names(template_bytes: bytes) -> tuple[str, ...]:
    try:
        with ZipFile(BytesIO(template_bytes), "r") as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
    except (KeyError, ET.ParseError, OSError) as exc:
        raise InspectionKeHoachKtEffectiveTemplateContractError(
            "KHKT template bytes are not an inspectable DOCX package"
        ) from exc
    names = [
        node.attrib.get(W_NAME)
        for node in root.findall(f".//{{{WORD_NS}}}bookmarkStart")
    ]
    return tuple(name for name in names if name and not name.startswith("_"))


def _casefold_index(names: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        key = name.casefold()
        if key in result:
            raise InspectionKeHoachKtEffectiveTemplateContractError(
                f"KHKT template contains case-insensitive duplicate bookmark: {name}"
            )
        result[key] = name
    return result


def _effective_targets(
    source_targets: tuple[str, ...],
    index: dict[str, str],
) -> tuple[str, ...]:
    return tuple(index[target.casefold()] for target in source_targets if target.casefold() in index)


def build_inspection_ke_hoach_kt_effective_template_contract(
    *,
    gxp_type: str,
    template_bytes: bytes,
) -> InspectionKeHoachKtEffectiveTemplateContract:
    if gxp_type not in _EXPECTED_BOOKMARKS:
        raise InspectionKeHoachKtEffectiveTemplateContractError(
            f"Unsupported KHKT GxP type: {gxp_type!r}"
        )
    names = _bookmark_names(template_bytes)
    if names != _EXPECTED_BOOKMARKS[gxp_type]:
        raise InspectionKeHoachKtEffectiveTemplateContractError(
            f"KHKT {gxp_type} bookmark geometry changed; fail closed"
        )
    index = _casefold_index(names)
    scalar_targets = {
        field: _effective_targets(targets, index)
        for field, targets in _SCALAR_SOURCE_TARGETS.items()
    }
    section_targets = {
        field: _effective_targets(targets, index)
        for field, targets in _SCOPE_DELETE_SOURCE_TARGETS.items()
    }
    section_targets = {field: targets for field, targets in section_targets.items() if targets}
    required_input_sources = {
        field for field, targets in scalar_targets.items() if targets
    }
    required_input_sources.update(section_targets)
    required_input_sources.add("TT3Del")
    missing_input_owners = sorted(required_input_sources - set(_PROVEN_INPUT_OWNER_BY_SOURCE))
    if missing_input_owners:
        raise InspectionKeHoachKtEffectiveTemplateContractError(
            "KHKT effective template exposes source inputs without proven owners: "
            + ", ".join(missing_input_owners)
        )
    input_owner_by_source = {
        field: _PROVEN_INPUT_OWNER_BY_SOURCE[field]
        for field in sorted(required_input_sources, key=str.casefold)
    }
    legacy_noop_scalar_sources = tuple(
        field for field, targets in scalar_targets.items() if not targets
    )
    return InspectionKeHoachKtEffectiveTemplateContract(
        gxp_type=gxp_type,
        template_bookmarks=names,
        scalar_targets=scalar_targets,
        optional_team_targets=tuple(
            target
            for key in ("TT_VKNx", "TT_SYTx")
            for target in scalar_targets[key]
        ),
        third_member_delete_target=index["tt3del"],
        scope_section_delete_targets=section_targets,
        input_owner_by_source=input_owner_by_source,
        legacy_noop_scalar_sources=legacy_noop_scalar_sources,
    )
