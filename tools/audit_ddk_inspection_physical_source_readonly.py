r"""Physical db.cso/db.ktra identity proof from the accepted legacy .xlsb.

Windows Excel COM is required.  The workbook is opened READ ONLY with macros
disabled and links not updated.  No workbook content, Site IDs, inspection
numbers, company IDs or paths are printed or committed.  Request stays private.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Any

from backend.app.domain.legacy_snapshot import _range_rows, safe_text
from backend.app.domain.phase2_import import (
    FIELD_ALIASES, normalize_inspection_gxp_type, parse_int,
)

SCHEMA = "GXP_DDK_CASE_INSPECTION_PHYSICAL_SOURCE_WITNESS_V1"
REQUEST_SCHEMA = "GXP_DDK_CASE_INSPECTION_PHYSICAL_SOURCE_REQUEST_V1"


class PhysicalSourceBlocked(ValueError):
    pass


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise PhysicalSourceBlocked(message)


def _column(headers: list[str], canonical: str) -> int:
    aliases = FIELD_ALIASES.get(canonical, set())
    matched = [
        i + 1 for i, value in enumerate(headers)
        if value == canonical or value in aliases
    ]
    _require(len(matched) == 1, "Required physical source column absent or ambiguous")
    return matched[0]


def _read_unique_rows(wb: Any, *, sheet: str, keys: tuple[str, ...],
                      identities: tuple[int, ...]) -> dict[int, dict[str, Any]]:
    """Scan *ID column only*, then capture exact cells with formula checks."""
    ws = wb.Worksheets(sheet)
    used = ws.UsedRange
    last_row = int(used.Row + used.Rows.Count - 1)
    last_col = int(used.Column + used.Columns.Count - 1)
    _require(1 <= last_row <= 100000 and 1 <= last_col <= 500,
             "Unexpected legacy source worksheet dimensions")
    header_raw = _range_rows(ws.Range(ws.Cells(1, 1),
                                      ws.Cells(min(last_row, 10), last_col)).Value2)
    candidate = []
    for i, row in enumerate(header_raw, start=1):
        if [safe_text(v) for v in row].count("ID") == 1:
            candidate.append((i, [safe_text(v) for v in row]))
    _require(len(candidate) == 1, "Physical ID source heading is ambiguous")
    header_row, headers = candidate[0]
    columns = {"ID": _column(headers, "ID")}
    for key in keys:
        columns[key] = _column(headers, key)
    id_col = columns["ID"]
    id_range = ws.Range(ws.Cells(header_row + 1, id_col),
                        ws.Cells(last_row, id_col))
    values = _range_rows(id_range.Value2)
    wanted = set(identities)
    found: dict[int, dict[str, Any]] = {}
    for physical_row, cells in enumerate(values, start=header_row + 1):
        value = parse_int(safe_text(cells[0])) if cells else None
        if value not in wanted:
            continue
        _require(value not in found and value is not None,
                 "Nonunique physical ID source record")
        info: dict[str, Any] = {"excel_row": physical_row}
        for field, col in columns.items():
            cell = ws.Cells(physical_row, col)
            _require(cell.HasFormula is False or cell.HasFormula == 0,
                     "Physical source identity field contains formula")
            info[field] = safe_text(cell.Value2)
        found[value] = info
    _require(set(found) == wanted,
             "Selected physical source identity absent or incomplete")
    return found


def evaluate_physical_rows(
    request: dict[str, Any],
    sites: dict[int, dict[str, Any]],
    cases: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    """Pure strict comparison, no fallback or mutated canonical ownership."""
    _require(request.get("schema") == REQUEST_SCHEMA
             and request.get("approval_status") == "NOT_APPROVED"
             and isinstance(request.get("source_workbook_sha256"), str)
             and re.fullmatch(r"[0-9a-f]{64}", request["source_workbook_sha256"])
             and type(request.get("source_site_legacy_id")) is int
             and type(request.get("observed_site_legacy_id_unverified")) is int
             and type(request.get("legacy_inspection_id")) is int
             and type(request.get("source_case_row_number")) is int
             and type(request.get("source_company_legacy_id")) is int
             and request["source_site_legacy_id"] > 0
             and request["observed_site_legacy_id_unverified"] > 0
             and request["legacy_inspection_id"] > 0
             and request["source_case_row_number"] > 0
             and request["source_company_legacy_id"] > 0
             and isinstance(request.get("inspection_code"), str)
             and request["source_site_legacy_id"] != request["observed_site_legacy_id_unverified"],
             "Not a protected one-Case physical source request")
    original_id = request["source_site_legacy_id"]
    observed_id = request["observed_site_legacy_id_unverified"]
    case_id = request["legacy_inspection_id"]
    _require(
        set(sites) == {original_id, observed_id} and set(cases) == {case_id},
        "Unexpected physical Case/Site record population")
    source = sites[original_id]
    alternate = sites[observed_id]
    case = cases[case_id]
    _require(
        parse_int(source["ID"]) == original_id
        and parse_int(alternate["ID"]) == observed_id
        and parse_int(case["ID"]) == case_id,
        "Original physical ID cells disagree with source request")
    company_a = parse_int(source["company_legacy_id_ref"])
    company_b = parse_int(alternate["company_legacy_id_ref"])
    case_site = parse_int(case["site_legacy_id_ref"])
    type_value = normalize_inspection_gxp_type(case["inspection_gxp_type"])
    code = (
        f"KT-{case_id}-{type_value}"
        if type_value is not None else None
    )
    case_row_matches = case["excel_row"] == request["source_case_row_number"]
    source_site_matches = case_site == original_id
    source_code_matches = code == request["inspection_code"]
    company_equal = company_a is not None and company_a == company_b
    company_matches_imported = company_a == request["source_company_legacy_id"]
    status = (
        "SOURCE_ROW_AND_SITE_MATCH_IMPORTED_CASE"
        if case_row_matches and source_site_matches and source_code_matches
        and company_equal and company_matches_imported
        else "SOURCE_WORKBOOK_CONFLICT_REQUIRES_OWNER_AUDIT"
    )
    return {
        "schema": SCHEMA,
        "status": status,
        "approval_status": "NOT_APPROVED",
        "source_case_excel_row_matches_anchor": case_row_matches,
        "source_case_site_fk_matches_imported": source_site_matches,
        "source_case_inspection_code_matches_imported": source_code_matches,
        "physical_both_sites_same_company": company_equal,
        "physical_site_company_matches_imported": company_matches_imported,
        "observed_nas_site_id_approved_as_case_owner": False,
        "workbook_verified_against_pinned_sha256": True,
        "workbook_modified": False,
        "database_access": "NONE",
        "database_writes": 0,
        "storage_connected": False,
        "storage_writes": 0,
        "canonical_links_created": 0,
    }


def audit_workbook(request: dict[str, Any], workbook: Path) -> dict[str, Any]:
    _require(workbook.is_file() and workbook.suffix.lower() == ".xlsb",
             "Existing .xlsb workbook required")
    fingerprint = sha256(workbook.read_bytes()).hexdigest()
    _require(fingerprint == request.get("source_workbook_sha256"),
             "Workbook fingerprint differs from pinned physical source")
    try:
        import win32com.client
    except ImportError as exc:
        raise PhysicalSourceBlocked("Windows Excel/pywin32 required") from exc
    app = win32com.client.DispatchEx("Excel.Application")
    wb = None
    try:
        app.Visible = False
        app.DisplayAlerts = False
        app.AskToUpdateLinks = False
        app.AutomationSecurity = 3
        wb = app.Workbooks.Open(str(workbook.resolve()), UpdateLinks=0,
                                ReadOnly=True, IgnoreReadOnlyRecommended=True,
                                AddToMru=False)
        _require(bool(wb.ReadOnly), "Workbook did not open read-only")
        sites = _read_unique_rows(
            wb, sheet="db.cso", keys=("company_legacy_id_ref",),
            identities=(request["source_site_legacy_id"],
                        request["observed_site_legacy_id_unverified"]),
        )
        cases = _read_unique_rows(
            wb, sheet="db.ktra", keys=("site_legacy_id_ref", "inspection_gxp_type"),
            identities=(request["legacy_inspection_id"],),
        )
        report = evaluate_physical_rows(request, sites, cases)
    finally:
        if wb is not None:
            wb.Close(False)
        app.Quit()
    _require(sha256(workbook.read_bytes()).hexdigest() == fingerprint,
             "Workbook changed during source verification")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--private-request", type=Path, required=True)
    parser.add_argument("--private-report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        _require(args.private_request.is_file()
                 and not args.private_request.is_symlink()
                 and not args.private_report.exists()
                 and not args.private_report.is_symlink()
                 and args.private_report.parent.is_dir()
                 and args.private_report.resolve() != args.private_request.resolve(),
                 "Protected source request/output path check failed")
        request = json.loads(args.private_request.read_text(encoding="utf-8"))
        report = audit_workbook(request, args.workbook)
        # Exclusive create; never overwrite a prior evidence report.
        with args.private_report.open("x", encoding="utf-8") as output:
            json.dump(report, output, ensure_ascii=False, indent=2, sort_keys=True)
            output.write("\n")
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        # Never leak physical cell values, paths or source IDs to stdout/stderr.
        print("PHYSICAL_SOURCE_AUDIT_BLOCKED: " + type(exc).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
