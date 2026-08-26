from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.audit_phase5_real_templates import inspect_file, match_families


OUTPUT_JSON = ROOT / "artifacts" / "phase5" / "bbtd_template_variants.json"
OUTPUT_MD = ROOT / "artifacts" / "phase5" / "bbtd_template_variants.md"
RECONCILIATION_JSON = ROOT / "artifacts" / "phase5" / "template_contract_reconciled.json"
TEMPLATES_ROOT = ROOT / "legacy" / "Templates"


def _load_reconciled_family() -> dict[str, object]:
    payload = json.loads(RECONCILIATION_JSON.read_text(encoding="utf-8"))
    return next(item for item in payload["families"] if item["family_code"] == "INSPECTION_BBTD_HOSO_DK")


def _variant_key_for_bookmarks(bookmarks: tuple[str, ...]) -> str:
    slot_suffixes = sorted(
        {
            int(bookmark[-1])
            for bookmark in bookmarks
            if bookmark[-1].isdigit() and bookmark[:-1] in {"DayChuyen", "DiaChiCoSo", "TenCoSo", "TenNguoiPhuTrach"}
        }
    )
    if slot_suffixes == [1, 2, 3]:
        return "bbtd_hoso_dk_all_lines"
    if len(slot_suffixes) == 1:
        return f"bbtd_hoso_dk_line_{slot_suffixes[0]}"
    raise RuntimeError(f"Could not derive BBTD variant key from bookmark slots: {bookmarks!r}")


def build_variant_contract() -> dict[str, object]:
    family = _load_reconciled_family()
    resolutions = {
        item["field_name"]: tuple(item["target_bookmarks"])
        for item in family["field_resolutions"]
    }
    matched_files: list[tuple[str, tuple[str, ...]]] = []
    for path in sorted(TEMPLATES_ROOT.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        if "INSPECTION_BBTD_HOSO_DK" not in match_families(path.name):
            continue
        inspection = inspect_file(path)
        matched_files.append((path.name, tuple(inspection["bookmarks"])))

    grouped: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for file_name, bookmarks in matched_files:
        grouped[bookmarks].append(file_name)

    variants: list[dict[str, object]] = []
    for bookmarks, template_names in sorted(grouped.items(), key=lambda item: (len(item[0]), item[1][0].lower())):
        field_mappings = {
            field_name: [bookmark for bookmark in targets if bookmark in bookmarks]
            for field_name, targets in resolutions.items()
        }
        field_mappings = {
            field_name: targets
            for field_name, targets in field_mappings.items()
            if targets
        }
        variants.append(
            {
                "variant_key": _variant_key_for_bookmarks(bookmarks),
                "template_name": template_names[0],
                "template_examples": template_names,
                "bookmarks": list(bookmarks),
                "allowed_payload_fields": sorted(field_mappings),
                "exclusive_bookmarks": [],
                "field_mappings": field_mappings,
                "unmapped_template_bookmarks": [
                    bookmark
                    for bookmark in bookmarks
                    if bookmark not in {target for targets in field_mappings.values() for target in targets}
                ],
            }
        )

    payload = {
        "family_code": "INSPECTION_BBTD_HOSO_DK",
        "variants": variants,
    }
    return payload


def render_markdown(payload: dict[str, object]) -> str:
    lines = [
        "# Phase 5 BBTD Variant Contracts",
        "",
        "## Scope",
        "- Family: `INSPECTION_BBTD_HOSO_DK`",
        "- Evidence source: active templates under `legacy/Templates` matched to the BBTD family.",
        "- Mapping source: `artifacts/phase5/template_contract_reconciled.json`",
        "",
        "## Variants",
    ]
    for item in payload["variants"]:
        lines.append(f"- `{item['variant_key']}`")
        lines.append(f"  examples: `{', '.join(item['template_examples'])}`")
        lines.append(f"  allowed fields: `{', '.join(item['allowed_payload_fields'])}`")
        mapping = ", ".join(
            f"{field}->{'/'.join(targets)}"
            for field, targets in sorted(item["field_mappings"].items())
        )
        lines.append(f"  field mappings: `{mapping}`")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    payload = build_variant_contract()
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    OUTPUT_MD.write_text(render_markdown(payload), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
