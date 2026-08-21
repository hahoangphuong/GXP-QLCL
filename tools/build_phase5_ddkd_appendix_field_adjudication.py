from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


VBA_SOURCE = ROOT / "artifacts" / "legacy_audit" / "vba_sources" / "GPs" / "RecordForm.frm"
Z3_TEMPLATE = ROOT / "legacy" / "Templates" / "z3. Phụ lục GCN ĐĐKKDD.dotx"
Z4_TEMPLATE = ROOT / "legacy" / "Templates" / "z4. QĐ cấp ĐĐKKDD.dotx"
OUTPUT_JSON = ROOT / "artifacts" / "phase5" / "ddkd_appendix_field_adjudication.json"
OUTPUT_MD = ROOT / "artifacts" / "phase5" / "ddkd_appendix_field_adjudication.md"

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}


def _load_vba_source() -> str:
    return VBA_SOURCE.read_text(encoding="utf-8", errors="ignore")


def _bookmark_names(path: Path) -> list[str]:
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    names = [
        bookmark.attrib.get(f"{{{WORD_NS}}}name")
        for bookmark in root.findall(".//w:bookmarkStart", NS)
    ]
    return sorted({name for name in names if name and not name.startswith("_")}, key=str.lower)


def _find_snippet(text: str, needle: str, *, radius: int = 600) -> str:
    idx = text.find(needle)
    if idx < 0:
        return ""
    return text[max(0, idx - radius) : idx + radius]


def build_report() -> dict[str, object]:
    vba_source = _load_vba_source()
    z3_bookmarks = _bookmark_names(Z3_TEMPLATE)
    z4_bookmarks = _bookmark_names(Z4_TEMPLATE)
    active_union = sorted(set(z3_bookmarks) | set(z4_bookmarks), key=str.lower)

    all_targets = [name for name in active_union if name.startswith("All")]
    report = {
        "family_code": "DDKD_APPENDIX_OR_DECISION",
        "templates": {
            "appendix": {
                "template_name": Z3_TEMPLATE.name,
                "bookmark_count": len(z3_bookmarks),
                "bookmarks": z3_bookmarks,
            },
            "issuance_decision": {
                "template_name": Z4_TEMPLATE.name,
                "bookmark_count": len(z4_bookmarks),
                "bookmarks": z4_bookmarks,
            },
        },
        "field_adjudications": [
            {
                "field_name": "All",
                "status": "safe_prefix_variant_group",
                "target_bookmarks": all_targets,
                "evidence": [
                    "Active templates expose AllGDP/AllGLP/AllGMP/AllGSP bookmarks.",
                    "RecordForm.Tao_PL_QD_GiayDDK deletes All{GPs_T} inside a 4-group loop.",
                    "Get_Tplz case 3 and case 4 both feed the same Tao_PL_QD_GiayDDK loop.",
                ],
                "vba_snippet": _find_snippet(vba_source, 'Delete_Bookmark wdDoc, "All" & GPs_T'),
            },
            {
                "field_name": "GCN_GMP",
                "status": "case_shared_write_with_missing_active_bookmark",
                "target_bookmarks": [],
                "evidence": [
                    "Get_Tplz selects z3 explicitly for case 3 and z4 explicitly for case 4.",
                    "CreateFilez handles case 3 and case 4 explicitly, then routes both into Tao_PL_QD_GiayDDK.",
                    "RecordForm.Tao_PL_QD_GiayDDK_Thongtinchung calls Replace_Bookmark wdDoc, GCN_GMP.",
                    "Replace_Bookmark uses On Error Resume Next and silently no-ops when a bookmark is missing.",
                    "Neither active template z3 nor z4 exposes a GCN_GMP bookmark.",
                ],
                "vba_snippet": _find_snippet(vba_source, 'Replace_Bookmark wdDoc, "GCN_GMP", Gcn_GP'),
            },
            {
                "field_name": "QD_GMP",
                "status": "case_shared_write_with_missing_active_bookmark",
                "target_bookmarks": [],
                "evidence": [
                    "Get_Tplz selects z3 explicitly for case 3 and z4 explicitly for case 4.",
                    "CreateFilez handles case 3 and case 4 explicitly, then routes both into Tao_PL_QD_GiayDDK.",
                    "RecordForm.Tao_PL_QD_GiayDDK_Thongtinchung calls Replace_Bookmark wdDoc, QD_GMP.",
                    "Replace_Bookmark uses On Error Resume Next and silently no-ops when a bookmark is missing.",
                    "Neither active template z3 nor z4 exposes a QD_GMP bookmark.",
                ],
                "vba_snippet": _find_snippet(vba_source, 'Replace_Bookmark wdDoc, "QD_GMP", QD_GCN'),
            },
        ],
        "recommended_next_state": {
            "promotable_now": ["All"],
            "still_blocked": ["GCN_GMP", "QD_GMP"],
            "notes": [
                "GCN_GMP and QD_GMP should not be promoted into render-safe runtime mapping until we explicitly decide how DocumentService handles case-shared writes whose active templates do not expose matching bookmarks.",
                "A future runtime policy may classify these as tolerated missing-bookmark writes for this family, but that must be an explicit contract decision rather than an accidental side effect.",
            ],
        },
    }
    return report


def render_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Phase 5 DDKD Appendix/Decision Field Adjudication",
        "",
        "## Scope",
        "- Family: `DDKD_APPENDIX_OR_DECISION`",
        "- Audit target: unresolved fields `All`, `GCN_GMP`, `QD_GMP`",
        "- Evidence sources:",
        "  - active templates `z3. Phụ lục GCN ĐĐKKDD.dotx` and `z4. QĐ cấp ĐĐKKDD.dotx`",
        "  - VBA source `artifacts/legacy_audit/vba_sources/GPs/RecordForm.frm`",
        "",
        "## Adjudications",
    ]
    for item in report["field_adjudications"]:
        lines.append(f"- `{item['field_name']}` -> status=`{item['status']}`")
        if item["target_bookmarks"]:
            lines.append(f"  targets: `{', '.join(item['target_bookmarks'])}`")
        for evidence in item["evidence"]:
            lines.append(f"  evidence: {evidence}")
    lines.extend(
        [
            "",
            "## Recommended Next State",
            f"- promotable now: `{', '.join(report['recommended_next_state']['promotable_now'])}`",
            f"- still blocked: `{', '.join(report['recommended_next_state']['still_blocked'])}`",
        ]
    )
    for note in report["recommended_next_state"]["notes"]:
        lines.append(f"- note: {note}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    report = build_report()
    OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_MD.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
