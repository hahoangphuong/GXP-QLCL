"""Fail-closed, read-only review manifest for physical db.dkkd GxP groups.

Requires a complete V3 source audit; rejects the flattened legacy snapshot.
This module never creates canonical BusinessEligibilityCertificateLink rows,
version identities, approval decisions, migrations or DB writes.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from backend.app.domain.phase2_import import parse_int
from tools.audit_ddk_idcc_physical import (
    DDK_GROUP_FIELDS, DDK_GROUP_LABELS, MissingPhysicalEvidence,
    split_idcc_references,
)

REVIEW_SCHEMA = "GXP_DDK_GXP_GROUP_REVIEW_MANIFEST_V1"
SOURCE_SCHEMA = "GXP_DDK_IDCC_PHYSICAL_REVIEW_V3"


def _fingerprint(values: list[str]) -> str:
    return sha256(
        json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _required_source_layout(report: dict[str, Any]) -> dict[int, dict[str, Any]]:
    if report.get("schema") != SOURCE_SCHEMA:
        raise MissingPhysicalEvidence("Requires complete V3 grouped source audit")
    if report.get("grouped_source_status") != "COMPLETE_SOURCE_GROUP_PROJECTION":
        raise MissingPhysicalEvidence("Source group layout not physically verified")
    if report.get("approval_status") != "NOT_APPROVED_NO_RELATIONSHIPS_CREATED":
        raise MissingPhysicalEvidence("Unexpected audit source approval state")
    checksum = report.get("source_sha256")
    if not isinstance(checksum, str) or len(checksum) != 64 or any(
        char not in "0123456789abcdef" for char in checksum.lower()
    ):
        raise MissingPhysicalEvidence("Missing SHA-256 identity of source workbook")
    header_evidence = report.get("header_evidence")
    if not isinstance(header_evidence, dict):
        raise MissingPhysicalEvidence("Missing original physical header evidence")
    layouts = header_evidence.get("id_cc_columns")
    if not isinstance(layouts, list) or len(layouts) != 4:
        raise MissingPhysicalEvidence("Expected exactly four verified GxP group headers")
    by_column: dict[int, dict[str, Any]] = {}
    labels: set[str] = set()
    for item in layouts:
        if not isinstance(item, dict):
            raise MissingPhysicalEvidence("Malformed source group header evidence")
        col = item.get("ordinal")
        label = item.get("observed_group_header")
        fields = item.get("group_field_columns")
        if type(col) is not int or col <= 0 or col in by_column or label in labels:
            raise MissingPhysicalEvidence("Duplicate or invalid GxP group identity")
        if label not in DDK_GROUP_LABELS or not isinstance(fields, dict):
            raise MissingPhysicalEvidence("Missing GxP source group provenance")
        if set(fields) != {name for name, _ in DDK_GROUP_FIELDS}:
            raise MissingPhysicalEvidence("Missing or extra GxP companion source fields")
        for offset, (name, header) in enumerate(DDK_GROUP_FIELDS):
            part = fields[name]
            if not isinstance(part, dict) or part.get("excel_column") != col + offset or part.get("source_header") != header:
                raise MissingPhysicalEvidence("Group field column/header ownership mismatch")
        by_column[col] = item
        labels.add(label)
    if labels != DDK_GROUP_LABELS:
        raise MissingPhysicalEvidence("Four unique GMP/GLP/GSP/GDP source groups required")
    return by_column


def _approved_exclusions(
    contract: dict[str, Any] | None,
) -> dict[int, tuple[str, int]]:
    """Return only explicitly approved and row-bound DDK exclusions."""
    if contract is None:
        return {}
    if contract.get("confirmation_source") != "user_review_of_anomaly_report":
        raise MissingPhysicalEvidence("Unapproved confirmed-blanked contract")
    excluded: dict[int, tuple[str, int]] = {}
    contract_rows = contract.get("rows")
    if not isinstance(contract_rows, list):
        raise MissingPhysicalEvidence("Missing approved exclusion contract rows")
    for record in contract_rows:
        if not isinstance(record, dict):
            raise MissingPhysicalEvidence("Malformed approved exclusion record")
        if record.get("source_sheet") != "db.dkkd":
            continue
        row_num = parse_int(record.get("source_row_number"))
        legacy_id = parse_int(record.get("legacy_row_id"))
        source_key = record.get("source_row_key")
        if (
            row_num is None or legacy_id is None or str(legacy_id) != str(source_key)
            or record.get("classification") != "confirmed_blanked_row"
            or record.get("migration_action") != "exclude_from_business_import"
            or record.get("confirmation_source") != "user_review_of_anomaly_report"
            or row_num in excluded
        ):
            raise MissingPhysicalEvidence("Malformed or duplicated approved DDK exclusion")
        excluded[row_num] = (str(source_key), legacy_id)
    by_sheet = contract.get("by_sheet")
    if not isinstance(by_sheet, dict) or not isinstance(by_sheet.get("db.dkkd"), dict):
        raise MissingPhysicalEvidence("Missing approved DDK exclusion summary")
    declared = by_sheet["db.dkkd"].get("row_count")
    if declared != len(excluded):
        raise MissingPhysicalEvidence("Exclusion count contradicts approved contract")
    return excluded


def build_group_review_manifest(
    audit_report: dict[str, Any], *,
    approved_exclusions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconcile every physical group cell and token; yield NO canonical links."""
    layouts = _required_source_layout(audit_report)
    excluded_rows = _approved_exclusions(approved_exclusions)
    source_rows = audit_report.get("grouped_source_rows")
    candidates = audit_report.get("candidates")
    if not isinstance(source_rows, list) or not isinstance(candidates, list):
        raise MissingPhysicalEvidence("Missing grouped rows or token audit")
    if len(source_rows) != audit_report.get("ddk_source_rows"):
        raise MissingPhysicalEvidence("Source DDK row count differs from projection")
    if len(candidates) != audit_report.get("candidate_count"):
        raise MissingPhysicalEvidence("Candidate total differs from audited references")

    token_map: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise MissingPhysicalEvidence("Malformed source candidate evidence")
        row_num = candidate.get("source_row_number")
        column = candidate.get("excel_column")
        if type(row_num) is not int or type(column) is not int:
            raise MissingPhysicalEvidence("Candidate lacks physical row/column identity")
        if column not in layouts:
            raise MissingPhysicalEvidence("Candidate is outside physical ID CC group")
        token_map[(row_num, column)].append(candidate)

    records: list[dict[str, Any]] = []
    used_pairs: set[tuple[int, int]] = set()
    seen_rows: set[int] = set()
    metrics: Counter = Counter()
    for row in source_rows:
        if not isinstance(row, dict):
            raise MissingPhysicalEvidence("Malformed physical source row")
        row_num = row.get("source_row_number")
        legacy_id = row.get("ddk_legacy_id")
        if type(row_num) is not int or row_num <= 0 or row_num in seen_rows:
            raise MissingPhysicalEvidence("Duplicate or invalid physical DDK row")
        seen_rows.add(row_num)
        group_values = row.get("groups")
        if not isinstance(group_values, list) or len(group_values) != 4:
            raise MissingPhysicalEvidence("DDK row missing one or more group projections")
        roles_this_row: set[str] = set()
        row_excluded = row_num in excluded_rows
        if row_excluded and parse_int(legacy_id) != excluded_rows[row_num][1]:
            raise MissingPhysicalEvidence("Approved exclusion conflicts with original DDK row ID")

        for group in group_values:
            if not isinstance(group, dict):
                raise MissingPhysicalEvidence("Malformed physical source group")
            column = group.get("id_cc_excel_column")
            layout = layouts.get(column)
            if layout is None or group.get("source_group") != layout["observed_group_header"]:
                raise MissingPhysicalEvidence("Projected group contradicts original physical header")
            role = group["source_group"]
            if role in roles_this_row:
                raise MissingPhysicalEvidence("Duplicate source group in DDK row")
            roles_this_row.add(role)
            fields = group.get("fields")
            if not isinstance(fields, dict) or set(fields) != {name for name, _ in DDK_GROUP_FIELDS}:
                raise MissingPhysicalEvidence("Missing source companion cells")
            source_values: list[str] = []
            source_fields: dict[str, dict[str, Any]] = {}
            for offset, (name, header) in enumerate(DDK_GROUP_FIELDS):
                field = fields[name]
                if (
                    not isinstance(field, dict)
                    or field.get("excel_column") != column + offset
                    or field.get("source_header") != header
                    or not isinstance(field.get("raw_value"), str)
                ):
                    raise MissingPhysicalEvidence("Source group cell identity mismatch")
                raw_value = field["raw_value"]
                source_values.append(raw_value)
                source_fields[name] = {
                    "excel_column": column + offset,
                    "source_header": header,
                    "raw_value": raw_value,
                    "raw_value_sha256": sha256(raw_value.encode("utf-8")).hexdigest(),
                }

            if row_excluded and any(source_values):
                raise MissingPhysicalEvidence("Approved excluded DDK row has live grouped source data")
            key = (row_num, column)
            used_pairs.add(key)
            raw_fk = source_values[0]
            expected_tokens = split_idcc_references(raw_fk) if raw_fk.strip() else []
            refs = token_map.get(key, [])
            if len(refs) != len(expected_tokens):
                raise MissingPhysicalEvidence("Candidate token count differs from physical ID CC cell")
            refs_by_index: dict[int, dict[str, Any]] = {}
            for candidate in refs:
                i = candidate.get("source_token_index")
                if type(i) is not int or i <= 0 or i in refs_by_index:
                    raise MissingPhysicalEvidence("Duplicate or absent physical token index")
                refs_by_index[i] = candidate
            flags: set[str] = set()
            reference_evidence: list[dict[str, Any]] = []
            for token_no, token in enumerate(expected_tokens, start=1):
                c = refs_by_index.get(token_no)
                if c is None or (
                    c.get("raw_fk") != raw_fk
                    or c.get("raw_fk_token") != token
                    or c.get("source_token_count") != len(expected_tokens)
                    or c.get("certificate_legacy_id") != parse_int(token)
                ):
                    raise MissingPhysicalEvidence("Candidate FK token lost or reinterpreted")
                if parse_int(c.get("ddk_legacy_id")) != parse_int(legacy_id):
                    raise MissingPhysicalEvidence("Candidate DDK identity differs from physical source")
                if c.get("observed_group_header") != role:
                    raise MissingPhysicalEvidence("Candidate GxP heading contradicts source group")
                if c.get("classification") not in {
                    "SAME_SITE", "CROSS_SITE", "SITE_UNRESOLVED",
                    "NONLITERAL_FK", "MISSING_CERTIFICATE", "AMBIGUOUS_CERTIFICATE_ID",
                }:
                    raise MissingPhysicalEvidence("Unknown source reference classification")
                if c.get("classification") != "SAME_SITE":
                    flags.add("SITE_OR_REFERENCE_REVIEW")
                source_type = c.get("certificate_type_vs_source_header")
                if source_type not in {"MATCH", "MISMATCH", "UNVERIFIED"}:
                    raise MissingPhysicalEvidence("Invalid source type comparison")
                if source_type != "MATCH":
                    flags.add("CERTIFICATE_TYPE_REVIEW")
                if (
                    c.get("ddk_company_vs_site") != "MATCH"
                    or c.get("certificate_company_vs_ddk") != "MATCH"
                ):
                    flags.add("COMPANY_OWNER_REVIEW")
                if c.get("reverse_relation") in ("REVERSE_CONFLICTS", "REVERSE_NONLITERAL"):
                    flags.add("REVERSE_EVIDENCE_REVIEW")
                reference_evidence.append({
                    "token_index": token_no,
                    "raw_token": token,
                    "legacy_certificate_id": c.get("certificate_legacy_id"),
                    "source_classification": c.get("classification"),
                    "source_type_comparison": c.get("certificate_type_vs_source_header"),
                    "reverse_relation": c.get("reverse_relation"),
                    "ddk_company_vs_site": c.get("ddk_company_vs_site"),
                    "certificate_company_vs_ddk": c.get("certificate_company_vs_ddk"),
                })
            any_companion = any(value.strip() for value in source_values[1:])
            if not raw_fk.strip() and any_companion:
                flags.add("COMPANION_WITHOUT_ID_CC")
            if raw_fk and not raw_fk.strip():
                flags.add("WHITESPACE_ONLY_ID_CC")
            if row_excluded:
                status = "CONFIRMED_BLANKED_SOURCE_ROW"
            elif not any(source_values):
                status = "EMPTY_SOURCE_GROUP"
            elif flags:
                status = "SOURCE_REVIEW_REQUIRED"
            else:
                status = "SOURCE_OBSERVED_NOT_APPROVED"
            metrics["group_count"] += 1
            metrics["source_cell_count"] += len(DDK_GROUP_FIELDS)
            metrics["candidate_token_count"] += len(refs)
            metrics[status.lower()] += 1
            for flag in flags:
                metrics["flag_" + flag.lower()] += 1
            records.append({
                "source_row_number": row_num,
                "ddk_legacy_id": legacy_id,
                "source_group": role,
                "id_cc_excel_column": column,
                "source_values_sha256": _fingerprint(source_values),
                "source_fields": source_fields,
                "source_field_excel_columns": [column + i for i in range(4)],
                "has_companion_without_id_cc": not raw_fk.strip() and bool(any_companion),
                "reference_evidence": reference_evidence,
                "review_flags": sorted(flags),
                "status": status,
                "approval_status": "NOT_APPROVED",
            })
        if roles_this_row != DDK_GROUP_LABELS:
            raise MissingPhysicalEvidence("Source row has incomplete GxP group coverage")
    if len(records) != len(source_rows) * len(DDK_GROUP_LABELS):
        raise MissingPhysicalEvidence("Grouped source conservation count mismatch")
    if set(token_map) != {pair for pair in used_pairs if token_map.get(pair)}:
        raise MissingPhysicalEvidence("Orphan candidate outside group source projection")
    if excluded_rows and not set(excluded_rows).issubset(seen_rows):
        raise MissingPhysicalEvidence("Approved exclusion refers to absent physical DDK row")
    return {
        "schema": REVIEW_SCHEMA,
        "source_workbook_sha256": audit_report["source_sha256"],
        "approval_status": "SOURCE_REVIEW_ONLY_NOT_APPROVED",
        "approved_exclusion_reconciliation": (
            "EXACT_BY_PHYSICAL_ROW_AND_DDK_ID" if approved_exclusions is not None
            else "NOT_CHECKED"
        ),
        "excluded_source_rows": len(excluded_rows) if approved_exclusions is not None else None,
        "metrics": dict(sorted(metrics.items())),
        "records": records,
        "restrictions": [
            "No inferred BusinessEligibilityVersion, version history or Certificate relationship",
            "No Canonical BusinessEligibilityCertificateLink created or approved",
            "Source group header ownership does not authorize a relational backfill",
            "Site, Company, GxP and reverse-FK evidence must be adjudicated independently",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-json", required=True, type=Path)
    parser.add_argument("--approved-exclusions-json", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        audit_bytes = args.audit_json.read_bytes()
        audit_data = json.loads(audit_bytes.decode("utf-8"))
        exclusion_bytes = (
            args.approved_exclusions_json.read_bytes()
            if args.approved_exclusions_json is not None else None
        )
        exclusions = (
            json.loads(exclusion_bytes.decode("utf-8"))
            if exclusion_bytes is not None else None
        )
        result = build_group_review_manifest(audit_data, approved_exclusions=exclusions)
        # These fingerprint the exact input JSON bytes, distinct from the
        # independently computed original binary Excel workbook checksum.
        result["input_artifact_sha256"] = {
            "v3_audit_json": sha256(audit_bytes).hexdigest(),
            "approved_exclusions_json": (
                sha256(exclusion_bytes).hexdigest()
                if exclusion_bytes is not None else None
            ),
        }
    except (MissingPhysicalEvidence, ValueError, OSError) as exc:
        parser.exit(2, f"Source review blocked: {exc}\n")
    inputs = [args.audit_json]
    if args.approved_exclusions_json is not None:
        inputs.append(args.approved_exclusions_json)
    if any(args.output.resolve() == path.resolve() for path in inputs):
        parser.exit(2, "Source review blocked: output cannot overwrite an input source\n")
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create prevents clobbering an earlier sealed review or input.
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    except FileExistsError:
        parser.exit(2, "Source review blocked: output already exists; choose a new review path\n")
    except OSError as exc:
        parser.exit(2, f"Source review blocked: {exc}\n")
    print(json.dumps({
        "status": result["approval_status"], "source_sha256": result["source_workbook_sha256"],
        "metrics": result["metrics"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
