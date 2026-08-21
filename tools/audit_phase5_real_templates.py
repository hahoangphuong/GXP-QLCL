from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from backend.app.project_paths import legacy_path, phase_artifact_path, repo_root


ROOT = repo_root()
REGISTRY_PATH = phase_artifact_path("phase5", "template_registry.curated.json")
TEMPLATES_ROOT = legacy_path("Templates")
OUTPUT_JSON = phase_artifact_path("phase5", "template_compatibility_audit.json")
OUTPUT_MD = phase_artifact_path("phase5", "template_compatibility_audit.md")

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": WORD_NS}


@dataclass(frozen=True)
class MatchRule:
    exact: tuple[str, ...] = ()
    prefixes: tuple[str, ...] = ()


FAMILY_MATCH_RULES: dict[str, MatchRule] = {
    "INSPECTION_BBTD_HOSO_DK": MatchRule(prefixes=("1 bbt d ho so dk", "1 bbtd ho so dk")),
    "INSPECTION_QD_KT": MatchRule(prefixes=("2 qd kt",)),
    "INSPECTION_KE_HOACH_KT": MatchRule(prefixes=("3 ke hoach kiem tra",)),
    "INSPECTION_BB_KT": MatchRule(prefixes=("4 bb kt",)),
    "INSPECTION_CAPA_LAN_1": MatchRule(prefixes=("5 danh gia capa",)),
    "INSPECTION_CAPA_LAN_2": MatchRule(prefixes=("5 danh gia capa",)),
    "INSPECTION_PT_PCT": MatchRule(prefixes=("6 pt pct",)),
    "INSPECTION_PT_CT": MatchRule(prefixes=("7 pt ct",)),
    "CERTIFICATE_DECISION": MatchRule(prefixes=("8 qd cap cc",)),
    "CERTIFICATE_ISSUANCE_WORD": MatchRule(prefixes=("9 chung chi",), exact=("9 chung chi gmpbb dotx", "9 chung chi glp moi dotx", "9 chung chi gmp moi dotx")),
    "RISK_MANAGEMENT_WORKSHEET": MatchRule(prefixes=("10 bang cong cu quan ly rui ro",)),
    "STATUS_CONFIRMATION_LETTER": MatchRule(prefixes=("a cv xac nhan tinh trang",)),
    "NAME_ADDRESS_CHANGE_LETTER": MatchRule(prefixes=("b cv tra loi dong y doi ten dia chi",)),
    "CHANGE_REPORT_ROUTE_LETTER": MatchRule(prefixes=("11 danh gia bao cao thay doi",)),
    "ASSESSMENT_MINUTES": MatchRule(prefixes=("3 2 bien ban danh gia",)),
    "CONSENT_CHANGE_LETTER": MatchRule(prefixes=("d cv dong y thay doi",)),
    "DDKD_PRESENTATION": MatchRule(prefixes=("z1 pt tt cap ddkkdd",)),
    "DDKD_CERTIFICATE": MatchRule(prefixes=("z2 giay chung nhan ddkkdd",)),
    "DDKD_APPENDIX_OR_DECISION": MatchRule(prefixes=("z3 phu luc gcn ddkkdd", "z4 qd cap ddkkdd")),
    "SUPPORT_TRAVEL_AUTHORIZATION": MatchRule(prefixes=("giay di duong",)),
    "SUPPORT_FLIGHT_REQUEST": MatchRule(prefixes=("xin di may bay",)),
    "SUPPORT_ATTENDEE_LIST": MatchRule(prefixes=("ds tham du dot kiem tra",)),
    "SUPPORT_DOSSIER_CHECKLIST": MatchRule(prefixes=("checklist ho so gps", "checklist kiem tra gps")),
    "SUPPORT_PAYMENT_TRANSFER": MatchRule(prefixes=("giay xin sec chuyen khoan", "uy quyen thanh toan ctp")),
    "SUPPORT_PAYMENT_WORKBOOK": MatchRule(prefixes=("thanh toan tam ung", "de nghi thanh toanx", "de nghi thanh toan")),
}


def normalize_name(value: str) -> str:
    value = value.replace("đ", "d").replace("Đ", "D")
    folded = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(ch for ch in folded if not unicodedata.combining(ch))
    cleaned = []
    for ch in ascii_only.lower():
        if ch.isalnum():
            cleaned.append(ch)
        else:
            cleaned.append(" ")
    return " ".join("".join(cleaned).split())


def load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def active_template_files() -> list[Path]:
    files: list[Path] = []
    for child in sorted(TEMPLATES_ROOT.iterdir(), key=lambda item: item.name.lower()):
        if child.is_file():
            files.append(child)
    return files


def _part_kind(part_name: str) -> str:
    if part_name == "word/document.xml":
        return "body"
    if part_name.startswith("word/header") and part_name.endswith(".xml"):
        return "header"
    if part_name.startswith("word/footer") and part_name.endswith(".xml"):
        return "footer"
    return "other"


def _bookmark_name(element: ET.Element) -> str | None:
    return element.attrib.get(f"{{{WORD_NS}}}name")


def inspect_word_ooxml(path: Path) -> dict:
    part_details: list[dict] = []
    all_bookmarks: list[str] = []
    with ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not (name.startswith("word/") and name.endswith(".xml")):
                continue
            try:
                root = ET.fromstring(archive.read(name))
            except ET.ParseError:
                continue
            bookmarks: list[str] = []
            table_bookmarks: list[str] = []
            for bookmark in root.findall(".//w:bookmarkStart", NSMAP):
                bookmark_name = _bookmark_name(bookmark)
                if not bookmark_name or bookmark_name.startswith("_"):
                    continue
                bookmarks.append(bookmark_name)
                for ancestor in root.iter():
                    pass
            if not bookmarks:
                continue
            bookmark_set = tuple(sorted(set(bookmarks), key=str.lower))
            for table in root.findall(".//w:tbl", NSMAP):
                for bookmark in table.findall(".//w:bookmarkStart", NSMAP):
                    bookmark_name = _bookmark_name(bookmark)
                    if bookmark_name and not bookmark_name.startswith("_"):
                        table_bookmarks.append(bookmark_name)
            table_bookmark_set = tuple(sorted(set(table_bookmarks), key=str.lower))
            all_bookmarks.extend(bookmark_set)
            part_details.append(
                {
                    "part_name": name,
                    "part_kind": _part_kind(name),
                    "bookmark_count": len(bookmark_set),
                    "bookmarks": list(bookmark_set),
                    "table_bookmarks": list(table_bookmark_set),
                }
            )
    unique_bookmarks = tuple(sorted(set(all_bookmarks), key=str.lower))
    return {
        "file_type": path.suffix.lower().lstrip("."),
        "is_word_ooxml": True,
        "bookmark_count": len(unique_bookmarks),
        "bookmarks": list(unique_bookmarks),
        "parts": part_details,
        "has_header_footer_bookmarks": any(
            part["part_kind"] in {"header", "footer"} and part["bookmark_count"] > 0
            for part in part_details
        ),
        "has_table_bookmarks": any(part["table_bookmarks"] for part in part_details),
    }


def inspect_file(path: Path) -> dict:
    suffix = path.suffix.lower()
    if suffix in {".dotx", ".docx", ".potx"}:
        try:
            return inspect_word_ooxml(path)
        except BadZipFile:
            return {
                "file_type": suffix.lstrip("."),
                "is_word_ooxml": False,
                "error": "bad_zip_file",
                "bookmark_count": 0,
                "bookmarks": [],
                "parts": [],
                "has_header_footer_bookmarks": False,
                "has_table_bookmarks": False,
            }
    return {
        "file_type": suffix.lstrip("."),
        "is_word_ooxml": False,
        "bookmark_count": 0,
        "bookmarks": [],
        "parts": [],
        "has_header_footer_bookmarks": False,
        "has_table_bookmarks": False,
    }


def match_families(file_name: str) -> tuple[str, ...]:
    normalized = normalize_name(file_name)
    matched: list[str] = []
    for family_code, rule in FAMILY_MATCH_RULES.items():
        if normalized in rule.exact:
            matched.append(family_code)
            continue
        if any(normalized.startswith(prefix) for prefix in rule.prefixes):
            matched.append(family_code)
    return tuple(dict.fromkeys(matched))


def classify_family(registry_entry: dict, files: list[dict], missing_bookmarks: list[str]) -> str:
    if not files:
        return "missing_active_template"
    if registry_entry["source_application"] != "Word":
        return "out_of_scope_excel_template"
    if any(item["path"].lower().endswith(".potx") for item in files):
        return "powerpoint_or_non_word_variant_present"
    if missing_bookmarks:
        return "bookmark_contract_mismatch"
    if registry_entry["copy_forward_dependencies"]:
        return "template_verified_copy_forward_pending"
    return "template_verified_word_ooxml"


def build_audit() -> dict:
    registry = load_registry()
    files = []
    files_by_family: dict[str, list[dict]] = {}
    unmatched_files: list[dict] = []
    for path in active_template_files():
        inspection = inspect_file(path)
        matched_families = match_families(path.name)
        file_record = {
            "path": path.relative_to(ROOT).as_posix(),
            "name": path.name,
            "normalized_name": normalize_name(path.stem + path.suffix),
            "matched_family_codes": list(matched_families),
            **inspection,
        }
        files.append(file_record)
        if not matched_families:
            unmatched_files.append(file_record)
            continue
        for family_code in matched_families:
            files_by_family.setdefault(family_code, []).append(file_record)

    family_reports: list[dict] = []
    for entry in registry["entries"]:
        family_files = sorted(files_by_family.get(entry["family_code"], []), key=lambda item: item["name"].lower())
        expected = sorted(set(entry["bookmarks"]), key=str.lower)
        actual = sorted(
            {
                bookmark
                for file_record in family_files
                for bookmark in file_record["bookmarks"]
            },
            key=str.lower,
        )
        missing = sorted(set(expected) - set(actual), key=str.lower)
        extra = sorted(set(actual) - set(expected), key=str.lower)
        family_reports.append(
            {
                "family_code": entry["family_code"],
                "logical_name": entry["logical_name"],
                "source_application": entry["source_application"],
                "storage_scope": entry["storage_scope"],
                "template_pattern": entry["template_pattern"],
                "copy_forward_dependencies": entry["copy_forward_dependencies"],
                "matched_file_count": len(family_files),
                "matched_files": family_files,
                "expected_bookmark_count": len(expected),
                "actual_bookmark_count": len(actual),
                "missing_bookmarks": missing,
                "extra_bookmarks": extra,
                "has_header_footer_bookmarks": any(item["has_header_footer_bookmarks"] for item in family_files),
                "has_table_bookmarks": any(item["has_table_bookmarks"] for item in family_files),
                "compatibility_status": classify_family(entry, family_files, missing),
            }
        )

    return {
        "templates_root": TEMPLATES_ROOT.relative_to(ROOT).as_posix(),
        "active_file_count": len(files),
        "registry_family_count": len(registry["entries"]),
        "matched_family_count": sum(1 for item in family_reports if item["matched_file_count"] > 0),
        "family_reports": family_reports,
        "unmatched_active_files": unmatched_files,
    }


def render_markdown(audit: dict) -> str:
    lines = [
        "# Phase 5 Real Template Compatibility Audit",
        "",
        "## Scope",
        "- Evidence source: active top-level files under `legacy/Templates`.",
        "- Archived revisions under `legacy/Templates/Cũ` are intentionally excluded from the compatibility baseline.",
        f"- Active files scanned: `{audit['active_file_count']}`.",
        f"- Registry families scanned: `{audit['registry_family_count']}`.",
        "",
        "## Family Matrix",
    ]
    for family in audit["family_reports"]:
        matched_names = ", ".join(f"`{item['name']}`" for item in family["matched_files"]) or "none"
        lines.append(
            f"- `{family['family_code']}` | status=`{family['compatibility_status']}` "
            f"| files={family['matched_file_count']} | expected={family['expected_bookmark_count']} "
            f"| actual={family['actual_bookmark_count']} | header/footer={family['has_header_footer_bookmarks']} "
            f"| table-bookmarks={family['has_table_bookmarks']}"
        )
        lines.append(f"  files: {matched_names}")
        if family["missing_bookmarks"]:
            lines.append(
                "  missing bookmarks: " + ", ".join(f"`{item}`" for item in family["missing_bookmarks"][:20])
            )
        if family["extra_bookmarks"]:
            lines.append(
                "  extra bookmarks: " + ", ".join(f"`{item}`" for item in family["extra_bookmarks"][:20])
            )

    lines.extend(
        [
            "",
            "## Unmatched Active Files",
        ]
    )
    if audit["unmatched_active_files"]:
        for file_record in audit["unmatched_active_files"]:
            lines.append(
                f"- `{file_record['name']}` | type=`{file_record['file_type']}` | bookmarks={file_record['bookmark_count']}"
            )
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    audit = build_audit()
    OUTPUT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_MD.write_text(render_markdown(audit), encoding="utf-8")


if __name__ == "__main__":
    main()
