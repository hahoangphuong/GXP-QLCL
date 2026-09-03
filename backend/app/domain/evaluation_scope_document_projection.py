from __future__ import annotations

"""Branch-aware C.5e evaluation-scope projections for legacy document fields.

This module is intentionally separate from the compact workspace summary.  It
ports only the scalar scope variables that active ``RecordForm.frm`` document
paths consume.  Certificate detail rendering (``Input_DC_to_CC``) is a distinct
structured-table path and is deliberately not implemented here.
"""

from dataclasses import dataclass
import re
from typing import Any, Iterable

from backend.app.domain.evaluation_scope_vba_renderer import compile_vba_readable_scope


ASSESSMENT_LABEL_SOURCE = "Phạm vi chứng nhận"
ASSESSMENT_LABEL_TARGET = "Phạm vi đánh giá"
DEFAULT_NO_LIMITATION = "Không"


@dataclass(frozen=True)
class VbaDocumentScopeVariants:
    dc_cu: str
    daychuyen_dd: str
    daychuyen_x: str
    daychuyen_lf: str
    ghan_dc: str


@dataclass(frozen=True)
class VbaDocumentScopeProjection:
    family_code: str
    fields: dict[str, str]
    variants: VbaDocumentScopeVariants
    vba_branch: str


# Active RecordForm.frm writes only.  Commented-out assignments are excluded.
DOCUMENT_SCOPE_BRANCHES: dict[str, dict[str, Any]] = {
    "INSPECTION_BBTD_HOSO_DK": {
        "branch": "Tao_BBTD",
        "fields": {"Daychuyen": "DaychuyenDD"},
    },
    "INSPECTION_QD_KT": {
        "branch": "Tao_QDKT_KHKT_BBKT:i=2",
        "fields": {},
    },
    "INSPECTION_KE_HOACH_KT": {
        "branch": "Tao_QDKT_KHKT_BBKT:i=3",
        "fields": {"Daychuyen": "DC_cu", "GioiHanPvi": "GHanDC/default Không"},
    },
    "INSPECTION_BB_KT": {
        "branch": "Tao_QDKT_KHKT_BBKT:i=4",
        "fields": {
            "Daychuyen": "DaychuyenLF",
            "GhPviDG": "assessment-labeled GHanDC/default Không",
            "GhPviCN": "GHanDC/default Không",
        },
    },
    "INSPECTION_PT_PCT": {
        "branch": "Tao_PT_PCT_CT:i=7",
        "fields": {"Daychuyen": "RipDot(DaychuyenX)", "Daychuyen2": "DaychuyenLF", "GioihanPvi": "GHanDC"},
    },
    "INSPECTION_PT_CT": {
        "branch": "Tao_PT_PCT_CT:i=8",
        "fields": {"Daychuyen": "RipDot(DaychuyenX)", "Daychuyen2": "DaychuyenLF", "GioihanPvi": "GHanDC"},
        "condition": "CopyPT=False",
    },
    "RISK_MANAGEMENT_WORKSHEET": {
        "branch": "Tao_BB_QLRR",
        "fields": {"Daychuyen": "DaychuyenDD"},
    },
    "ASSESSMENT_MINUTES": {
        "branch": "Tao_BB_Danhgia",
        "fields": {"DayChuyen": "DaychuyenDD", "GioiHanPvi": "assessment-labeled GHanDC/default Không"},
    },
    "CERTIFICATE_DECISION": {
        "branch": "Tao_QD_CapCC",
        "fields": {},
        "commented_only": {"Daychuyen": "DaychuyenX"},
    },
}


def _vba_replace_case_insensitive(value: str, old: str, new: str) -> str:
    return re.sub(re.escape(old), lambda _: new, value, flags=re.IGNORECASE)


def _normalize_getdata_text(value: str) -> str:
    """Port the three final DCForm.GetData replacements for scalar source values."""
    result = value.strip(" ")
    result = _vba_replace_case_insensitive(result, "beta", "β")
    result = _vba_replace_case_insensitive(result, "lactam", "Lactam")
    result = _vba_replace_case_insensitive(result, " Lactam", "-Lactam")
    return result


def _daychuyen_x(daychuyen_dd: str) -> str:
    """Port RecordForm.GetTT_Ktra construction of ``DaychuyenX``."""
    value = daychuyen_dd.strip(" ")
    value = _vba_replace_case_insensitive(value, "* ", "")
    value = _vba_replace_case_insensitive(value, "*", "")
    for old in (".  \r\n", ". \r\n", ".\r\n", "\r\n"):
        value = _vba_replace_case_insensitive(value, old, "; ")
    value = _vba_replace_case_insensitive(value, ".; ", "; ")
    value = _vba_replace_case_insensitive(value, ";; ", "; ")
    return value


def _daychuyen_lf(daychuyen_dd: str) -> str:
    """Port RecordForm.GetTT_Ktra construction of ``DaychuyenLF``."""
    value = _vba_replace_case_insensitive(daychuyen_dd, "* ", "")
    value = _vba_replace_case_insensitive(value, "*", "")
    return value.strip(" ")


def _rip_dot(value: str) -> str:
    result = value.strip(" ")
    return result[:-1] if result.endswith(".") else result


def _assessment_limitation(ghan_dc: str) -> str:
    source = ghan_dc if ghan_dc != "" else DEFAULT_NO_LIMITATION
    return source.replace(ASSESSMENT_LABEL_SOURCE, ASSESSMENT_LABEL_TARGET)


def build_vba_document_scope_variants(
    *,
    blocks: Iterable[dict[str, Any]],
    taxonomy_nodes: Iterable[dict[str, Any]],
    limitation_text: str | None,
    gxp_type: str,
) -> VbaDocumentScopeVariants:
    """Build the RecordForm scalar variables from canonical structured scope.

    ``unkeyed_entries`` are intentionally stripped at this boundary.  They are
    legacy skipped-by-design evidence and are not semantic compiler input.
    """
    compiler_blocks = [
        {
            "id": block.get("id"),
            "ordinal": block.get("ordinal"),
            "name": block.get("name"),
            "note": block.get("note"),
            "selections": list(block.get("selections") or ()),
        }
        for block in blocks
    ]
    dc_cu = compile_vba_readable_scope(
        blocks=compiler_blocks,
        taxonomy_nodes=taxonomy_nodes,
        limitation_text=None,
        gxp_type=gxp_type,
    ).text
    ghan_dc = _normalize_getdata_text("" if limitation_text is None else str(limitation_text))
    return VbaDocumentScopeVariants(
        dc_cu=dc_cu,
        daychuyen_dd=dc_cu,
        daychuyen_x=_daychuyen_x(dc_cu),
        daychuyen_lf=_daychuyen_lf(dc_cu),
        ghan_dc=ghan_dc,
    )


def project_vba_document_scope_fields(
    *,
    family_code: str,
    blocks: Iterable[dict[str, Any]],
    taxonomy_nodes: Iterable[dict[str, Any]],
    limitation_text: str | None,
    gxp_type: str,
    copy_pt: bool = False,
) -> VbaDocumentScopeProjection:
    """Project only scalar scope fields actively written by one VBA document path.

    Unsupported families fail closed.  ``INSPECTION_PT_CT`` with ``CopyPT=True``
    returns no scalar scope writes because the active VBA branch is bypassed.
    """
    spec = DOCUMENT_SCOPE_BRANCHES.get(family_code)
    if spec is None:
        raise ValueError(f"Unsupported C.5e evaluation-scope document family: {family_code}")

    variants = build_vba_document_scope_variants(
        blocks=blocks,
        taxonomy_nodes=taxonomy_nodes,
        limitation_text=limitation_text,
        gxp_type=gxp_type,
    )

    if family_code == "INSPECTION_PT_CT" and copy_pt:
        fields: dict[str, str] = {}
    elif family_code in {"INSPECTION_QD_KT", "CERTIFICATE_DECISION"}:
        fields = {}
    elif family_code in {"INSPECTION_BBTD_HOSO_DK", "RISK_MANAGEMENT_WORKSHEET"}:
        fields = {"Daychuyen": variants.daychuyen_dd}
    elif family_code == "INSPECTION_KE_HOACH_KT":
        fields = {
            "Daychuyen": variants.dc_cu,
            "GioiHanPvi": variants.ghan_dc or DEFAULT_NO_LIMITATION,
        }
    elif family_code == "INSPECTION_BB_KT":
        fields = {
            "Daychuyen": variants.daychuyen_lf,
            "GhPviDG": _assessment_limitation(variants.ghan_dc),
            "GhPviCN": variants.ghan_dc or DEFAULT_NO_LIMITATION,
        }
    elif family_code in {"INSPECTION_PT_PCT", "INSPECTION_PT_CT"}:
        fields = {
            "Daychuyen": _rip_dot(variants.daychuyen_x),
            "Daychuyen2": variants.daychuyen_lf,
            "GioihanPvi": variants.ghan_dc,
        }
    elif family_code == "ASSESSMENT_MINUTES":
        fields = {
            "DayChuyen": variants.daychuyen_dd,
            "GioiHanPvi": _assessment_limitation(variants.ghan_dc),
        }
    else:  # pragma: no cover - exhaustive guard for future registry edits.
        raise AssertionError(f"C.5e branch table has no projection implementation for {family_code}")

    return VbaDocumentScopeProjection(
        family_code=family_code,
        fields=fields,
        variants=variants,
        vba_branch=str(spec["branch"]),
    )
