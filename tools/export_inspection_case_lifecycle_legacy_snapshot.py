from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from backend.app.domain.legacy_snapshot import read_core_sheet_rows
from backend.app.domain.phase2_import import normalize_row, parse_int
from tools.plan_inspection_case_lifecycle_reconciliation import (
    SNAPSHOT_CC_FIELDS,
    SNAPSHOT_CC_IDENTITY_PROVENANCE_FIELDS,
    SNAPSHOT_EXTRACTION_OWNER,
    SNAPSHOT_EXTRACTION_STATUS,
    SNAPSHOT_KTRA_FIELDS,
    SNAPSHOT_REQUIRED_SECTIONS,
    SNAPSHOT_SCHEMA_VERSION,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / ".local-audit" / "inspection_case_lifecycle_legacy_snapshot.json"


def _required_integer(value: str, *, source_sheet: str, source_row: str, field: str) -> int:
    parsed = parse_int(value)
    if parsed is None:
        raise RuntimeError(f"{source_sheet} row {source_row} has invalid required {field}")
    return parsed


def _select_rows(
    source_rows: list[dict[str, str]],
    fields: tuple[str, ...],
    *,
    source_sheet: str,
    require_case_link: bool,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    selected: list[dict[str, str]] = []
    counts = {
        "structural_blank_rows_skipped": 0,
        "linked_rows": 0,
        "unlinked_rows": 0,
        "unlinked_rows_with_business_payload": 0,
        "invalid_link_rows": 0,
    }
    identity_fields = SNAPSHOT_CC_IDENTITY_PROVENANCE_FIELDS
    business_fields = tuple(field for field in fields if field not in identity_fields)
    for raw in source_rows:
        normalized = normalize_row(raw)
        source_row = str(normalized.get("__excel_row_number", "")).strip()
        _required_integer(source_row, source_sheet=source_sheet, source_row=source_row or "?", field="__excel_row_number")
        has_business_payload = any(str(normalized.get(field, "")).strip() not in {"", "-", "???"} for field in business_fields)
        raw_id = normalized.get("ID", "")
        try:
            _required_integer(raw_id, source_sheet=source_sheet, source_row=source_row, field="ID")
        except RuntimeError:
            if has_business_payload:
                raise
            counts["structural_blank_rows_skipped"] += 1
            continue
        if require_case_link:
            raw_case_link = str(normalized.get("inspection_case_legacy_id_ref", "")).strip()
            if not raw_case_link:
                if not has_business_payload:
                    counts["structural_blank_rows_skipped"] += 1
                    continue
                counts["unlinked_rows"] += 1
                counts["unlinked_rows_with_business_payload"] += 1
            else:
                try:
                    _required_integer(
                        raw_case_link,
                        source_sheet=source_sheet,
                        source_row=source_row,
                        field="inspection_case_legacy_id_ref",
                    )
                except RuntimeError:
                    counts["invalid_link_rows"] += 1
                    raise
                counts["linked_rows"] += 1
        selected.append({field: str(normalized.get(field, "")) for field in fields})
    return selected, counts


def build_snapshot_payload(workbook: Path, source_rows: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
    """Build deterministic local-only evidence from the canonical Excel extraction."""
    missing = [name for name in SNAPSHOT_REQUIRED_SECTIONS if name not in source_rows]
    if missing:
        raise RuntimeError(f"canonical workbook extraction is missing required sheets: {', '.join(missing)}")
    ktra_rows, ktra_counts = _select_rows(
        source_rows["db.ktra"], SNAPSHOT_KTRA_FIELDS, source_sheet="db.ktra", require_case_link=False
    )
    cc_rows, cc_counts = _select_rows(
        source_rows["db.cc"],
        SNAPSHOT_CC_FIELDS,
        source_sheet="db.cc",
        require_case_link=True,
    )
    sections = {
        "db.ktra": {"source_sheet": "db.ktra", "row_count": len(ktra_rows), "rows": ktra_rows},
        "db.cc": {"source_sheet": "db.cc", "row_count": len(cc_rows), "rows": cc_rows},
    }
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "source_workbook_sha256": sha256(workbook.read_bytes()).hexdigest(),
        "source_workbook_name": workbook.name,
        "extraction_owner": SNAPSHOT_EXTRACTION_OWNER,
        "source_sheets": list(SNAPSHOT_REQUIRED_SECTIONS),
        "row_count": len(ktra_rows) + len(cc_rows),
        "extraction_status": SNAPSHOT_EXTRACTION_STATUS,
        "sections": sections,
        "row_eligibility_counts": {
            "db_ktra_rows_emitted": len(ktra_rows),
            "db_ktra_structural_blank_rows_skipped": ktra_counts["structural_blank_rows_skipped"],
            "db_cc_rows_emitted": len(cc_rows),
            "db_cc_linked_rows": cc_counts["linked_rows"],
            "db_cc_unlinked_rows": cc_counts["unlinked_rows"],
            "db_cc_unlinked_rows_with_business_payload": cc_counts["unlinked_rows_with_business_payload"],
            "db_cc_invalid_link_rows": cc_counts["invalid_link_rows"],
            "db_cc_structural_blank_rows_skipped": cc_counts["structural_blank_rows_skipped"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export local-only lifecycle reconciliation input from the Windows workbook owner.")
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    workbook = args.workbook.resolve()
    payload = build_snapshot_payload(workbook, read_core_sheet_rows(workbook))
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"STATUS={SNAPSHOT_EXTRACTION_STATUS}")
    print(f"SOURCE_WORKBOOK_SHA256={payload['source_workbook_sha256']}")
    print(f"ROW_COUNT={payload['row_count']}")
    print(f"OUTPUT={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
