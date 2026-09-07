from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.domain.legacy_inspection_storage_anchor import (
    LegacyInspectionStorageAnchorSourceRow,
    projection_payloads,
    read_legacy_inspection_storage_anchor_rows,
)


def audit(
    source_rows: Iterable[LegacyInspectionStorageAnchorSourceRow],
    *,
    source_version: str,
    projection_rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    source_rows = list(source_rows)
    expected = projection_payloads(source_rows, source_version=source_version)
    source_ids = [row["legacy_inspection_id"] for row in expected]
    duplicate_source_case_ids = sorted(
        legacy_id for legacy_id in set(source_ids) if source_ids.count(legacy_id) > 1
    )
    expected_by_id = {row["legacy_inspection_id"]: row for row in expected}
    actual_rows = list(projection_rows)
    actual_by_id: dict[int, dict[str, Any]] = {}
    duplicate_projection_ids: list[int] = []
    for row in actual_rows:
        legacy_id = row.get("legacy_inspection_id")
        if not isinstance(legacy_id, int):
            raise ValueError("Projection audit rows require integer legacy_inspection_id values.")
        if legacy_id in actual_by_id:
            duplicate_projection_ids.append(legacy_id)
        actual_by_id[legacy_id] = row

    missing_case_ids = sorted(set(expected_by_id) - set(actual_by_id))
    extra_case_ids = sorted(set(actual_by_id) - set(expected_by_id))
    field_mismatches: list[dict[str, Any]] = []
    compared_fields = (
        "source_sheet",
        "source_row",
        "registration_submission_raw",
        "registration_submission_year",
        "registration_submission_status",
        "inspection_date_raw",
        "inspection_year",
        "inspection_year_status",
        "source_hash",
        "source_version",
    )
    for legacy_id in sorted(set(expected_by_id) & set(actual_by_id)):
        expected_row = expected_by_id[legacy_id]
        actual_row = actual_by_id[legacy_id]
        differences = {
            field: {"expected": expected_row[field], "actual": actual_row.get(field)}
            for field in compared_fields
            if expected_row[field] != actual_row.get(field)
        }
        if differences:
            field_mismatches.append({"legacy_inspection_id": legacy_id, "differences": differences})

    registration_usable_count = sum(
        row.registration_submission.status == "usable" for row in source_rows
    )
    inspection_fallback_usable_count = sum(
        row.registration_submission.status != "usable" and row.inspection_date.status == "usable"
        for row in source_rows
    )
    no_anchor_count = sum(
        row.registration_submission.status != "usable" and row.inspection_date.status != "usable"
        for row in source_rows
    )
    return {
        "source_version": source_version,
        "effective_case_count": len(source_rows),
        "registration_usable_year_count": registration_usable_count,
        "inspection_fallback_usable_year_count": inspection_fallback_usable_count,
        "no_anchor_count": no_anchor_count,
        "registration_conflict_count": sum(
            row.registration_submission.status == "conflict" for row in source_rows
        ),
        "inspection_conflict_count": sum(row.inspection_date.status == "conflict" for row in source_rows),
        "duplicate_source_case_ids": duplicate_source_case_ids,
        "duplicate_projection_case_ids": sorted(set(duplicate_projection_ids)),
        "missing_case_ids": missing_case_ids,
        "extra_case_ids": extra_case_ids,
        "field_mismatches": field_mismatches,
        "parity_passed": not (
            missing_case_ids
            or extra_case_ids
            or duplicate_source_case_ids
            or duplicate_projection_ids
            or field_mismatches
        ),
    }


def _load_projection_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("Projection JSON must be a list of projection row objects or an object containing rows.")
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only parity audit for source-faithful legacy inspection storage anchors."
    )
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--projection-json", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    source_rows, source_version = read_legacy_inspection_storage_anchor_rows(args.workbook)
    report = audit(
        source_rows,
        source_version=source_version,
        projection_rows=_load_projection_rows(args.projection_json),
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        print(rendered, end="")
    return 0 if report["parity_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
