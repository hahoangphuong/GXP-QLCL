"""Read-only source audit for repeated db.dkkd ID CC physical Excel columns.

Windows (from repository root): py -3 -m tools.audit_ddk_idcc_physical --workbook "D:\GXP-QLCL\legacy\Danh sách Kiểm tra GPs.xlsb" --out-dir "D:\GXP-DDK-IDCC-REVIEW"
Or use --snapshot-json with a lossless coordinate-preserving snapshot.
Never generates/approves canonical certificate links.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from backend.app.domain.legacy_snapshot import (
    _core_header_plan, _core_source_row, _range_rows, safe_text,
)
from backend.app.domain.phase2_import import normalize_row, parse_int


AUDIT_SOURCE_SHEETS = ("db.cty", "db.cso", "db.cc", "db.dkkd")


class MissingPhysicalEvidence(ValueError):
    """Flattened V1 cannot establish the original four column values."""


def excel_column_letter(number: int) -> str:
    if number < 1:
        raise ValueError("Excel column ordinals start at 1")
    result = ""
    while number:
        number, digit = divmod(number - 1, 26)
        result = chr(65 + digit) + result
    return result


def require_literal_idcc_column(has_formula: Any, column: int) -> None:
    """Excel Range.HasFormula is False only when no cells contain formulas."""
    if has_formula is not False and has_formula != 0:
        raise MissingPhysicalEvidence(
            f"db.dkkd ID CC physical column {column} contains formula cells "
            "or has unverifiable formula status; computed FKs are not literal evidence"
        )


def find_id_header_row(raw_rows: list[list[object]], sheet: str) -> int:
    """Identify one source header row by its literal ID label."""
    matching = [
        i for i, raw in enumerate(raw_rows[:10])
        if [safe_text(cell) for cell in raw].count("ID") == 1
    ]
    if len(matching) != 1:
        raise MissingPhysicalEvidence(
            f"Cannot uniquely identify the {sheet} source ID header"
        )
    return matching[0]


def find_ddk_header_row(raw_rows: list[list[object]]) -> int:
    """Require the unique physical db.dkkd header; never guess column ownership."""
    matching = [
        i for i, raw in enumerate(raw_rows[:10])
        if [safe_text(cell) for cell in raw].count("ID CC") == 4
        and "ID" in [safe_text(cell) for cell in raw]
    ]
    if len(matching) != 1:
        raise MissingPhysicalEvidence(
            "Cannot uniquely identify the db.dkkd header with four ID CC columns"
        )
    return matching[0]


def extract_readonly_workbook(path: Path) -> tuple[dict[str, list[dict[str, str]]], dict[str, Any]]:
    """Open an isolated Excel process without links, macros, or workbook writes."""
    if not path.is_file() or path.suffix.lower() != ".xlsb":
        raise ValueError("Expected an existing source .xlsb workbook")
    try:
        import win32com.client
    except ImportError as exc:
        raise RuntimeError("Reading .xlsb directly requires Windows, Excel and pywin32") from exc
    app = win32com.client.DispatchEx("Excel.Application")
    workbook = None
    try:
        app.Visible = False
        app.DisplayAlerts = False
        app.AskToUpdateLinks = False
        app.AutomationSecurity = 3  # msoAutomationSecurityForceDisable
        workbook = app.Workbooks.Open(
            str(path.resolve()), UpdateLinks=0, ReadOnly=True,
            IgnoreReadOnlyRecommended=True, AddToMru=False,
        )
        if not workbook.ReadOnly:
            raise RuntimeError("Refusing non-read-only Excel workbook")
        snapshot: dict[str, list[dict[str, str]]] = {}
        sheet_evidence: dict[str, Any] = {}
        for name in AUDIT_SOURCE_SHEETS:
            ws = workbook.Worksheets(name)
            used = ws.UsedRange
            # Read from A1 to true absolute last cell: saved source
            # ordinals always identify physical Excel columns.
            last_row = int(used.Row + used.Rows.Count - 1)
            last_col = int(used.Column + used.Columns.Count - 1)
            raw_rows = _range_rows(
                ws.Range(ws.Cells(1, 1), ws.Cells(last_row, last_col)).Value2
            )
            if not raw_rows:
                raise MissingPhysicalEvidence(f"Empty source sheet: {name}")
            if name == "db.dkkd":
                header_index = find_ddk_header_row(raw_rows)
            else:
                header_index = find_id_header_row(raw_rows, name)
            headers = [safe_text(value) for value in raw_rows[header_index]]
            if "ID" not in headers:
                raise MissingPhysicalEvidence(f"Missing ID source header: {name}")
            plan = _core_header_plan(headers)
            snapshot[name] = [
                _core_source_row(headers, row, row_num, plan=plan)
                for row_num, row in enumerate(raw_rows[header_index + 1:], start=header_index + 2)
                if any(safe_text(value) for value in row)
            ]
            if name == "db.dkkd":
                idcc_columns = [
                    index + 1 for index, label in enumerate(headers) if label == "ID CC"
                ]
                # Excel Value2 returns a cached number even for =formula cells.
                # Refuse to represent such computed results as literal source FKs.
                if last_row <= header_index + 1:
                    raise MissingPhysicalEvidence("db.dkkd has no source data rows")
                for column in idcc_columns:
                    formula_state = ws.Range(
                        ws.Cells(header_index + 2, column),
                        ws.Cells(last_row, column),
                    ).HasFormula
                    require_literal_idcc_column(formula_state, column)
                # The header band is evidence for owner review, not permission
                # to label ordinal N as GMP, GLP, GSP or GDP.
                sheet_evidence = {
                    "header_row": header_index + 1,
                    "id_cc_columns": [
                        {
                            "ordinal": column,
                            "letter": excel_column_letter(column),
                            "observed_group_header": (
                                safe_text(raw_rows[header_index - 1][column - 1])
                                if header_index > 0 else ""
                            ),
                            "header_band": [
                                {
                                    "row": row_num,
                                    "value": safe_text(raw_rows[row_num - 1][column - 1])
                                }
                                for row_num in range(max(1, header_index - 4), header_index + 1)
                                if safe_text(raw_rows[row_num - 1][column - 1])
                            ],
                        }
                        for column in idcc_columns
                    ],
                    "duplicate_headers": plan[1],
                }
        return snapshot, sheet_evidence
    finally:
        if workbook is not None:
            workbook.Close(False)
        app.Quit()


def _idcc_columns(rows: list[dict[str, str]]) -> list[int]:
    if not rows:
        raise MissingPhysicalEvidence("No db.dkkd source rows")
    observed: set[tuple[int, ...]] = set()
    for row in rows:
        raw = row.get("__excel_duplicate_headers")
        if not raw:
            raise MissingPhysicalEvidence(
                "db.dkkd has no preserved duplicate-column metadata. "
                "The flattened V1 snapshot cannot recover the four ID CC columns; "
                "re-extract from the original .xlsb using --workbook."
            )
        try:
            groups = json.loads(raw)
            matches = [item for item in groups if item["header"] == "ID CC"]
            if len(matches) != 1:
                raise ValueError("Ambiguous ID CC metadata")
            column_ordinals = matches[0]["column_ordinals"]
            if (
                not isinstance(column_ordinals, list)
                or len(column_ordinals) != 4
                or any(type(number) is not int or number < 1 for number in column_ordinals)
                or sorted(set(column_ordinals)) != column_ordinals
            ):
                raise ValueError("Expected four distinct ascending physical ID CC ordinals")
            columns = tuple(column_ordinals)
        except (ValueError, TypeError, KeyError) as exc:
            raise MissingPhysicalEvidence("Invalid four-column ID CC physical metadata") from exc
        observed.add(columns)
    if len(observed) != 1:
        raise MissingPhysicalEvidence("ID CC physical-column positions vary across rows")
    columns = list(next(iter(observed)))
    seen_physical_rows: set[int] = set()
    for row in rows:
        if any(f"ID CC [excel_column={number}]" not in row for number in columns):
            raise MissingPhysicalEvidence("Missing one or more preserved ID CC cells")
        physical_row = parse_int(row.get("__excel_row_number"))
        if physical_row is None or physical_row < 1 or physical_row in seen_physical_rows:
            raise MissingPhysicalEvidence("Missing or duplicated physical db.dkkd row number")
        seen_physical_rows.add(physical_row)
    return columns


def split_idcc_references(raw_fk: str) -> list[str]:
    """Preserve semicolon-separated literal IDs and malformed tokens independently.

    Source examples include '17; 29' and '477;885'; no business links are
    created here. Empty components are not silently discarded.
    """
    return [token.strip() for token in raw_fk.split(";")]


def _source_lookup_status(identity: int | None, records: dict[int, list[dict[str, str]]]) -> str:
    if identity is None:
        return "UNRESOLVED"
    count = len(records.get(identity, ()))
    return "MISSING" if count == 0 else ("UNIQUE" if count == 1 else "AMBIGUOUS")


def audit(snapshot: dict[str, list[dict[str, str]]], *, source_sha256: str | None = None,
          header_evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    """Audit the real source link evidence without assigning semantic roles."""
    required = set(AUDIT_SOURCE_SHEETS)
    if not required.issubset(snapshot):
        raise MissingPhysicalEvidence(f"Missing source sheets: {sorted(required - set(snapshot))}")
    raw_ddk = snapshot["db.dkkd"]
    columns = _idcc_columns(raw_ddk)
    certificates = defaultdict(list)
    for record in snapshot["db.cc"]:
        row = normalize_row(record)
        certificate_id = parse_int(row.get("ID"))
        if certificate_id is not None:
            certificates[certificate_id].append(row)
    sites: dict[int, list[dict[str, str]]] = defaultdict(list)
    for record in snapshot["db.cso"]:
        row = normalize_row(record)
        site_id = parse_int(row.get("ID"))
        if site_id is not None:
            sites[site_id].append(row)
    companies: dict[int, list[dict[str, str]]] = defaultdict(list)
    for record in snapshot["db.cty"]:
        row = normalize_row(record)
        company_id = parse_int(row.get("ID"))
        if company_id is not None:
            companies[company_id].append(row)
    column_counts: dict[int, Counter] = {column: Counter() for column in columns}
    column_types: dict[int, Counter] = {column: Counter() for column in columns}
    candidates: list[dict[str, Any]] = []
    same_row_refs: dict[int, Counter] = defaultdict(Counter)
    reference_rows: dict[int, set[int]] = defaultdict(set)
    for raw_row in raw_ddk:
        row = normalize_row(raw_row)
        ddk_id = parse_int(row.get("ID"))
        ddk_site = parse_int(row.get("site_legacy_id_ref"))
        ddk_company = parse_int(row.get("company_legacy_id_ref"))
        row_number = parse_int(row.get("__excel_row_number"))
        ddk_site_status = _source_lookup_status(ddk_site, sites)
        ddk_company_status = _source_lookup_status(ddk_company, companies)
        site_owner_company = (
            parse_int(sites[ddk_site][0].get("company_legacy_id_ref"))
            if ddk_site_status == "UNIQUE" else None
        )
        company_vs_site = (
            "UNRESOLVED"
            if ddk_company_status != "UNIQUE" or site_owner_company is None
            else ("MATCH" if site_owner_company == ddk_company else "MISMATCH")
        )
        for col in columns:
            raw_fk = safe_text(raw_row[f"ID CC [excel_column={col}]"])
            if not raw_fk:
                column_counts[col]["blank"] += 1
                continue
            column_counts[col]["populated"] += 1
            tokens = split_idcc_references(raw_fk)
            column_counts[col]["candidate_tokens"] += len(tokens)
            if len(tokens) > 1:
                column_counts[col]["multi_id_cells"] += 1
            for token_index, raw_fk_token in enumerate(tokens, start=1):
                target_id = parse_int(raw_fk_token)
                evidence: dict[str, Any] = {
                    "ddk_legacy_id": ddk_id,
                    "source_row_number": row_number,
                    "ddk_site_legacy_id": ddk_site,
                    "ddk_company_legacy_id": ddk_company,
                    "ddk_site_lookup": ddk_site_status,
                    "ddk_company_lookup": ddk_company_status,
                    "ddk_company_vs_site": company_vs_site,
                    "certificate_site_lookup": "UNVERIFIED",
                    "excel_column": col,
                    "column_letter": excel_column_letter(col),
                    "certificate_legacy_id": target_id,
                    "raw_fk": raw_fk,
                    "raw_fk_token": raw_fk_token,
                    "source_token_index": token_index,
                    "source_token_count": len(tokens),
                    "classification": None,
                    "certificate_type": None,
                    "certificate_site_legacy_id": None,
                    "reverse_id_ddk": None,
                    "reverse_relation": "UNVERIFIED",
                    "source_role": "UNVERIFIED",
                }
                if company_vs_site == "MISMATCH":
                    column_counts[col]["ddk_company_vs_site_mismatch"] += 1
                if target_id is None:
                    evidence["classification"] = "NONLITERAL_FK"
                    evidence["raw_value_sha256_prefix"] = sha256(raw_fk.encode("utf-8")).hexdigest()[:12]
                    column_counts[col]["nonliteral_fk"] += 1
                elif len(certificates[target_id]) != 1:
                    evidence["classification"] = ("MISSING_CERTIFICATE" if not certificates[target_id]
                                                  else "AMBIGUOUS_CERTIFICATE_ID")
                    column_counts[col][evidence["classification"].lower()] += 1
                else:
                    cert = certificates[target_id][0]
                    cert_site = parse_int(cert.get("site_legacy_id_ref"))
                    cert_type = safe_text(cert.get("certificate_type")).strip()
                    evidence["certificate_type"] = cert_type or None
                    evidence["certificate_site_legacy_id"] = cert_site
                    cert_site_status = _source_lookup_status(cert_site, sites)
                    evidence["certificate_site_lookup"] = cert_site_status
                    column_types[col][cert_type or "(blank)"] += 1
                    if cert_site is None or ddk_site is None:
                        evidence["classification"] = "SITE_UNRESOLVED"
                    elif cert_site != ddk_site:
                        evidence["classification"] = "CROSS_SITE"
                    elif ddk_site_status != "UNIQUE" or cert_site_status != "UNIQUE":
                        evidence["classification"] = "SITE_UNRESOLVED"
                    else:
                        evidence["classification"] = "SAME_SITE"
                    column_counts[col][evidence["classification"].lower()] += 1
                    reverse_raw = safe_text(cert.get("ID DDK"))
                    reverse_id = parse_int(reverse_raw)
                    evidence["reverse_id_ddk"] = reverse_id
                    if "ID DDK" not in cert:
                        evidence["reverse_relation"] = "REVERSE_FIELD_UNAVAILABLE"
                    elif not reverse_raw:
                        evidence["reverse_relation"] = "REVERSE_BLANK"
                    elif reverse_id is None:
                        evidence["reverse_relation"] = "REVERSE_NONLITERAL"
                    elif reverse_id == ddk_id:
                        evidence["reverse_relation"] = "REVERSE_CONFIRMS"
                    else:
                        evidence["reverse_relation"] = "REVERSE_CONFLICTS"
                    column_counts[col][evidence["reverse_relation"].lower()] += 1
                candidates.append(evidence)
                if row_number is not None and target_id is not None:
                    same_row_refs[row_number][target_id] += 1
                    reference_rows[target_id].add(row_number)
    for evidence in candidates:
        source_row = evidence["source_row_number"]
        cid = evidence["certificate_legacy_id"]
        evidence["duplicate_within_ddk"] = (
            cid is not None and same_row_refs[source_row][cid] > 1
        )
        evidence["duplicate_across_ddk_rows"] = (
            cid is not None and len(reference_rows[cid]) > 1
        )
        if evidence["duplicate_within_ddk"]:
            column_counts[evidence["excel_column"]]["duplicate_within_ddk"] += 1
        if evidence["duplicate_across_ddk_rows"]:
            column_counts[evidence["excel_column"]]["duplicate_across_ddk_rows"] += 1
    return {
        "schema": "GXP_DDK_IDCC_PHYSICAL_REVIEW_V2",
        "approval_status": "NOT_APPROVED_NO_RELATIONSHIPS_CREATED",
        "source_sha256": source_sha256,
        "ddk_source_rows": len(raw_ddk),
        "id_cc_column_count": len(columns),
        "id_cc_columns": [
            {
                "excel_column": col, "column_letter": excel_column_letter(col),
                "owner_role": "UNVERIFIED",
                "observed_group_header": next((
                    item.get("observed_group_header")
                    for item in (header_evidence or {}).get("id_cc_columns", [])
                    if item.get("ordinal") == col
                ), None),
                "counts": dict(sorted(column_counts[col].items())),
                "certificate_type_distribution": dict(sorted(column_types[col].items())),
            }
            for col in columns
        ],
        "header_evidence": header_evidence or {},
        "candidate_count": len(candidates),
        "candidates": candidates,
        "restrictions": [
            "Observed source group headers are evidence, not business approval to persist links",
            "Do not infer GMP/GLP/GSP/GDP roles from physical column order or type frequency",
            "Do not create canonical BusinessEligibilityCertificateLink from this report",
            "Do not fill forward links from db.cc.ID DDK without independent authorization",
            "Review cross-Site, nonliteral, missing, conflicting and duplicate evidence",
            "This is raw-source evidence, not proof of current rehearsal database state",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--workbook", type=Path)
    sources.add_argument("--snapshot-json", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.workbook:
            snapshot, header_evidence = extract_readonly_workbook(args.workbook)
            origin = args.workbook
        else:
            snapshot = json.loads(args.snapshot_json.read_text(encoding="utf-8"))
            header_evidence = None
            origin = args.snapshot_json
        fingerprint = sha256(origin.read_bytes()).hexdigest()
        result = audit(snapshot, source_sha256=fingerprint, header_evidence=header_evidence)
    except (MissingPhysicalEvidence, ValueError, RuntimeError) as exc:
        parser.exit(2, f"Source evidence blocked: {exc}\n")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    # Never export the entire workbook or synthesize a canonical import.
    out = args.out_dir / "ddk_idcc_physical_source_review.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote read-only evidence: {out}")
    print(f"Rows={result['ddk_source_rows']}; physical ID CC columns={result['id_cc_column_count']}; candidates={result['candidate_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
