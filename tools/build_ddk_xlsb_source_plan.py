"""Linux/VM XLSB source evidence: original four physical DDK GxP groups.

Only reads the owner-pinned original binary workbook and the confirmed-blanked
exclusions. Uses pyxlsb cached cell values (NOT Excel COM/HasFormula).
Produces one offline sealed source-only load plan, NEVER a DB write or link.

Install pyxlsb into an isolated tools-only target directory; no modification to
the backend runtime VM dependency lock is required.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable

from backend.app.domain.legacy_snapshot import safe_text
from backend.app.domain.phase2_import import parse_int
from tools.audit_ddk_idcc_physical import (
    DDK_GROUP_FIELDS, DDK_GROUP_LABELS, MissingPhysicalEvidence,
    discover_ddk_group_layout, find_ddk_header_row, source_value2_text,
    split_idcc_references,
)
from tools.plan_ddk_gxp_provenance_load import build_source_provenance_dry_run


def original_ddk_physical_evidence(
    physical_rows: Iterable[tuple[int, list[Any]]],
    workbook_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Transform pyxlsb physical rows into complete group and token evidence.

    Preserve row/column coordinates. Do not infer group from an ID CC header:
    the distinct GMP/GLP/GSP/GDP heading immediately above each repeated
    four-field block is the sole group owner.
    """
    positions: dict[int, list[Any]] = {}
    for row_number, values in physical_rows:
        if type(row_number) is not int or row_number < 1 or row_number in positions:
            raise MissingPhysicalEvidence("Duplicate or invalid original Excel row index")
        if not isinstance(values, list):
            raise MissingPhysicalEvidence("Malformed source XLSB row")
        positions[row_number] = values

    header_band = [positions.get(row, []) for row in range(1, 11)]
    header_offset = find_ddk_header_row(header_band)
    header_number = header_offset + 1
    headers = [safe_text(value) for value in positions[header_number]]
    identity_columns = [col for col, label in enumerate(headers) if label == "ID"]
    if len(identity_columns) != 1 or header_number < 2:
        raise MissingPhysicalEvidence("Missing unique physical source DDK ID/header")
    plan = discover_ddk_group_layout(
        headers,
        positions.get(header_number - 1, []),
    )
    if {p["observed_group_header"] for p in plan} != DDK_GROUP_LABELS:
        raise MissingPhysicalEvidence("Incomplete physical GxP group header ownership")
    for p in plan:
        if p["ordinal"] not in (15, 19, 23, 27):
            # The reviewed original source has O/S/W/AA group anchors.
            # These are evidence contract coordinates, not heuristic rescue.
            raise MissingPhysicalEvidence("Original GxP Excel physical columns differ from accepted source")

    heading_evidence = [
        {
            "group": item["observed_group_header"],
            "id_cc_column": item["ordinal"],
            "fields": item["group_field_columns"],
        }
        for item in plan
    ]
    rows = []
    refs = []
    for row_number in sorted(positions):
        if row_number <= header_number:
            continue
        values = positions[row_number]
        if not any(safe_text(value) for value in values):
            continue
        if len(values) <= identity_columns[0]:
            raise MissingPhysicalEvidence("Truncated original DDK ID")
        legacy_id = parse_int(values[identity_columns[0]])
        if legacy_id is None or legacy_id <= 0:
            raise MissingPhysicalEvidence("Non-positive or missing original DDK row ID")
        groups = []
        for anchor in plan:
            col = anchor["ordinal"]
            fields = {}
            for field_name, expected_heading in DDK_GROUP_FIELDS:
                field = anchor["group_field_columns"][field_name]
                ordinal = field["excel_column"]
                if ordinal > len(values):
                    raise MissingPhysicalEvidence("Truncated DDK GxP source field at physical column")
                raw_value = source_value2_text(values[ordinal - 1])
                fields[field_name] = {
                    "excel_column": ordinal,
                    "source_header": expected_heading,
                    "raw_value": raw_value,
                }
            id_cell = fields["id_cc"]["raw_value"]
            for token in split_idcc_references(id_cell) if id_cell.strip() else ():
                literal_id = parse_int(token)
                if literal_id is None or literal_id <= 0:
                    raise MissingPhysicalEvidence("Malformed ID CC token in physical source cell")
                refs.append({
                    "ddk_excel_row": row_number,
                    "physical_col": col,
                    "ddk_id": legacy_id,
                    "source_role": anchor["observed_group_header"],
                    "raw_cell": id_cell,
                    "token": token,
                    "certificate_id": literal_id,
                })
            groups.append({
                "source_group": anchor["observed_group_header"],
                "id_cc_excel_column": col,
                "fields": fields,
            })
        rows.append({
            "source_row_number": row_number,
            "ddk_legacy_id": str(legacy_id),
            "groups": groups,
        })
    grouped = {
        "schema": "GXP_DDK_GROUPED_SOURCE_EVIDENCE_V1",
        "source_sha256": workbook_sha256,
        "ddk_rows": len(rows),
        "header_evidence": heading_evidence,
        "source_rows": rows,
    }
    references = {
        "schema": "GXP_DDK_XLSB_INDEPENDENT_SOURCE_ANALYSIS_V1",
        "source_workbook_sha256": workbook_sha256,
        "summary": {
            "ddk_rows": len(rows),
            "token_references": len(refs),
        },
        "candidates": refs,
    }
    return grouped, references


def read_xlsb_ddk_rows(workbook: Path) -> list[tuple[int, list[Any]]]:
    """Use physical r/c from pyxlsb, never sheet row-list ordinals."""
    try:
        from pyxlsb import open_workbook
    except ImportError as exc:
        raise MissingPhysicalEvidence("Install pyxlsb into the isolated tool environment") from exc
    result: list[tuple[int, list[Any]]] = []
    with open_workbook(str(workbook)) as handle:
        names = list(handle.sheets)
        if "db.dkkd" not in names:
            raise MissingPhysicalEvidence("Workbook missing db.dkkd")
        with handle.get_sheet("db.dkkd") as sheet:
            for cells in sheet.rows(sparse=True):
                if not cells:
                    continue
                first = cells[0]
                physical = int(first.r) + 1
                width = max(int(cell.c) for cell in cells) + 1
                values: list[Any] = [None] * width
                for cell in cells:
                    column = int(cell.c)
                    values[column] = cell.v
                result.append((physical, values))
    return result


def create_sealed_xlsb_plan(
    workbook: Path,
    exclusions_file: Path,
    *,
    expected_sha256: str,
    expected_rows: int,
    expected_excluded_rows: int,
    expected_reference_tokens: int,
    row_loader=read_xlsb_ddk_rows,
) -> dict[str, Any]:
    if not workbook.is_file() or workbook.suffix.lower() != ".xlsb":
        raise MissingPhysicalEvidence("Original XLSB workbook file unavailable")
    workbook_bytes_before = workbook.read_bytes()
    original_sha = sha256(workbook_bytes_before).hexdigest()
    if original_sha != expected_sha256:
        raise MissingPhysicalEvidence("Original XLSB workbook SHA-256 mismatch")
    exclusions_bytes = exclusions_file.read_bytes()
    exclusions = json.loads(exclusions_bytes.decode("utf-8"))
    group_data, reference_data = original_ddk_physical_evidence(
        row_loader(workbook), original_sha,
    )
    plan = build_source_provenance_dry_run(
        group_data, reference_data, exclusions,
        accepted_workbook_sha256=original_sha,
        expected_ddk_rows=expected_rows,
        expected_excluded_ddk_rows=expected_excluded_rows,
        expected_reference_tokens=expected_reference_tokens,
    )
    if sha256(workbook.read_bytes()).hexdigest() != original_sha:
        raise MissingPhysicalEvidence("Source XLSB changed while extracting")
    if exclusions_file.read_bytes() != exclusions_bytes:
        raise MissingPhysicalEvidence("Approved exclusion evidence changed")
    # Prior independent XLSB exports are NOT recreated by an independent
    # reader here: group and reference views share this one XLSB traversal.
    # The source workbook identity and accepted external counts are verified,
    # but no Excel COM/HasFormula or independent-engine check is claimed.
    plan["physical_source_reader"] = {
        "reader": "PYXLSB_CACHED_CELLS_SINGLE_READER",
        "source_workbook_sha256": original_sha,
        "independent_reader_verification": False,
        "excel_com_formula_status": "WAIVED_NOT_CHECKED",
        "source_exclusions_file_sha256": sha256(exclusions_bytes).hexdigest(),
    }
    return plan


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workbook", type=Path, required=True)
    p.add_argument("--approved-exclusions-json", type=Path, required=True)
    p.add_argument("--expected-workbook-sha256", required=True)
    p.add_argument("--expected-ddk-rows", type=int, required=True)
    p.add_argument("--expected-excluded-ddk-rows", type=int, required=True)
    p.add_argument("--expected-reference-tokens", type=int, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(argv)
    if a.output.resolve() in {a.workbook.resolve(), a.approved_exclusions_json.resolve()}:
        p.error("Output must not overwrite source evidence")
    if a.output.exists():
        p.error("Output already exists")
    try:
        plan = create_sealed_xlsb_plan(
            a.workbook, a.approved_exclusions_json,
            expected_sha256=a.expected_workbook_sha256,
            expected_rows=a.expected_ddk_rows,
            expected_excluded_rows=a.expected_excluded_ddk_rows,
            expected_reference_tokens=a.expected_reference_tokens,
        )
        a.output.parent.mkdir(parents=True, exist_ok=True)
        # Confidential original Excel cells: ensure mode 0600 regardless of
        # operator umask, and never overwrite pre-existing evidence.
        descriptor = os.open(a.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(plan, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
        except BaseException:
            a.output.unlink(missing_ok=True)
            raise
        print(json.dumps({
            "status": plan["status"],
            "source_workbook_sha256": plan["source_workbook_sha256"],
            "payload_sha256": plan["payload_sha256"],
            "counts": plan["counts"],
            "reader": plan["physical_source_reader"]["reader"],
        }, ensure_ascii=False, sort_keys=True))
        return 0
    except (MissingPhysicalEvidence, ValueError, OSError, TypeError, KeyError) as exc:
        print("DDK_XLSB_SOURCE_PLAN_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
