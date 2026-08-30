from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.audit_phase5_real_templates import normalize_name


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": WORD_NS}

TEMPLATES_ROOT = ROOT / "legacy" / "Templates"
RECONCILED_PATH = ROOT / "artifacts" / "phase5" / "template_contract_reconciled.json"
OUTPUT_JSON = ROOT / "artifacts" / "phase5" / "dkkd_template_variants.json"
OUTPUT_MD = ROOT / "artifacts" / "phase5" / "dkkd_template_variants.md"


def _bookmark_names(path: Path) -> list[str]:
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    names = [
        bookmark.attrib.get(f"{{{WORD_NS}}}name")
        for bookmark in root.findall(".//w:bookmarkStart", NSMAP)
    ]
    return sorted({name for name in names if name and not name.startswith("_")}, key=str.lower)


def _find_template(prefix: str) -> Path:
    matches = [
        path
        for path in TEMPLATES_ROOT.iterdir()
        if path.is_file() and normalize_name(path.name).startswith(prefix)
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one DDKD variant template for prefix={prefix!r}, found {len(matches)}")
    return matches[0]


def _ddkd_family_fields() -> list[str]:
    payload = json.loads(RECONCILED_PATH.read_text(encoding="utf-8"))
    family = next(item for item in payload["families"] if item["family_code"] == "DDKD_CERTIFICATE")
    return [item["field_name"] for item in family["field_resolutions"]]


def main() -> None:
    moi_path = _find_template("z2 giay chung nhan ddkkdd moi")
    dieu_chinh_path = _find_template("z2 giay chung nhan ddkkdd dieu chinh")
    moi_bookmarks = _bookmark_names(moi_path)
    dieu_chinh_bookmarks = _bookmark_names(dieu_chinh_path)
    family_fields = _ddkd_family_fields()

    common = sorted(set(moi_bookmarks) & set(dieu_chinh_bookmarks), key=str.lower)
    moi_only = sorted(set(moi_bookmarks) - set(dieu_chinh_bookmarks), key=str.lower)
    dieu_chinh_only = sorted(set(dieu_chinh_bookmarks) - set(moi_bookmarks), key=str.lower)

    payload = {
        "family_code": "DDKD_CERTIFICATE",
        "variants": [
            {
                "variant_key": "ddkd_certificate_new",
                "template_name": moi_path.name,
                "bookmarks": moi_bookmarks,
                "allowed_payload_fields": [field for field in family_fields if field in moi_bookmarks],
                "exclusive_bookmarks": moi_only,
            },
            {
                "variant_key": "ddkd_certificate_adjustment",
                "template_name": dieu_chinh_path.name,
                "bookmarks": dieu_chinh_bookmarks,
                "allowed_payload_fields": [field for field in family_fields if field in dieu_chinh_bookmarks],
                "exclusive_bookmarks": dieu_chinh_only,
            },
        ],
        "common_bookmarks": common,
        "new_only_bookmarks": moi_only,
        "adjustment_only_bookmarks": dieu_chinh_only,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    lines = [
        "# DDKD Template Variants",
        "",
        f"- new template: `{moi_path.name}`",
        f"- adjustment template: `{dieu_chinh_path.name}`",
        f"- common bookmarks: `{len(common)}`",
        f"- new-only bookmarks: `{', '.join(moi_only) or 'none'}`",
        f"- adjustment-only bookmarks: `{', '.join(dieu_chinh_only) or 'none'}`",
        "",
        "## Allowed Payload Fields",
    ]
    for variant in payload["variants"]:
        lines.append(f"- `{variant['variant_key']}` -> `{', '.join(variant['allowed_payload_fields'])}`")
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
