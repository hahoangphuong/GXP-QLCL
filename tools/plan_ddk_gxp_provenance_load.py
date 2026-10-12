"""Prepare DDK GxP provenance INSERT-shaped data WITHOUT database connections.

Input: owner-accepted original XLSB exports (group fields and independent ID
references) plus the existing confirmed-blanked-row approval contract.
Output: immutable, exclusively-created DRY-RUN plan with logical source keys.

This tool never imports or writes to SQLAlchemy, PostgreSQL, Excel, Case,
Certificate, or BusinessEligibilityCertificateLink. No UUID is fabricated.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from backend.app.domain.phase2_import import parse_int
from tools.audit_ddk_idcc_physical import (
    DDK_GROUP_FIELDS, DDK_GROUP_LABELS, MissingPhysicalEvidence,
    split_idcc_references,
)
from tools.ddk_group_evidence_review import _approved_exclusions
from tools.reconcile_ddk_source_artifacts import reconcile, source_groups

PLAN_SCHEMA = "GXP_DDK_GXP_PROVENANCE_DRY_RUN_V1"
GROUP_TABLE = "business_eligibility_gxp_source_group"
TOKEN_TABLE = "business_eligibility_gxp_reference_evidence"


def _digest(data: Any) -> str:
    return sha256(
        json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _source_value_digest(values: list[str]) -> str:
    # Identical to the original owner source-review 4-field sequence hash.
    return sha256(
        json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _source_identity(workbook_sha: str, row: int, role: str) -> dict[str, Any]:
    return {
        "source_workbook_sha256": workbook_sha,
        "source_sheet_name": "db.dkkd",
        "source_row_number": row,
        "source_group": role,
    }


def build_source_provenance_dry_run(
    grouped: dict[str, Any],
    references: dict[str, Any],
    exclusions_contract: dict[str, Any],
    *,
    accepted_workbook_sha256: str,
    expected_ddk_rows: int,
    expected_excluded_ddk_rows: int,
    expected_reference_tokens: int,
) -> dict[str, Any]:
    """Reconcile all physical source evidence; plan no canonical links/DB writes."""
    for name, n in (
        ("expected_ddk_rows", expected_ddk_rows),
        ("expected_excluded_ddk_rows", expected_excluded_ddk_rows),
        ("expected_reference_tokens", expected_reference_tokens),
    ):
        if type(n) is not int or n < 0:
            raise MissingPhysicalEvidence(f"Invalid accepted baseline: {name}")
    if expected_ddk_rows <= 0 or expected_excluded_ddk_rows > expected_ddk_rows:
        raise MissingPhysicalEvidence("Invalid DDK/exclusion baseline population")
    if not isinstance(accepted_workbook_sha256, str) or len(accepted_workbook_sha256) != 64:
        raise MissingPhysicalEvidence("Missing original accepted binary workbook SHA-256")
    try:
        bytes.fromhex(accepted_workbook_sha256)
    except ValueError as exc:
        raise MissingPhysicalEvidence("Malformed accepted workbook fingerprint") from exc

    # Reuse the upstream lossless-field and reference multiset reconciliation,
    # not a downstream parser of already-flattened linked_certificate_ids.
    observed = reconcile(
        workbook_hash=accepted_workbook_sha256,
        grouped=grouped, links=references,
    )
    if observed["status"] != "PARTIAL_INDEPENDENT_EXPORTS_ONLY":
        raise MissingPhysicalEvidence("Unexpected source reconciliation contract")
    metrics = observed["metrics"]
    if (metrics["ddk_rows"] != expected_ddk_rows
            or metrics["source_groups"] != expected_ddk_rows * 4
            or metrics["source_field_cells"] != expected_ddk_rows * 16
            or metrics["reference_tokens"] != expected_reference_tokens):
        raise MissingPhysicalEvidence("Accepted source baseline counts have drifted")

    excluded = _approved_exclusions(exclusions_contract)
    if len(excluded) != expected_excluded_ddk_rows:
        raise MissingPhysicalEvidence("Approved exclusion count differs from accepted baseline")
    sheet_contract = exclusions_contract.get("by_sheet", {}).get("db.dkkd", {})
    accepted_keys = sheet_contract.get("source_row_keys")
    accepted_ids = sheet_contract.get("legacy_row_ids")
    if not isinstance(accepted_keys, list) or not isinstance(accepted_ids, list):
        raise MissingPhysicalEvidence("Approved exclusion ID lists are missing")
    keys = sorted(v[0] for v in excluded.values())
    if sorted(accepted_keys) != keys or sorted(accepted_ids) != keys:
        raise MissingPhysicalEvidence("Approved exclusions differ from source row ID lists")

    cells, _ = source_groups(grouped)
    all_rows = grouped["source_rows"]
    actual_source_rows = {row["source_row_number"] for row in all_rows}
    if not set(excluded).issubset(actual_source_rows):
        raise MissingPhysicalEvidence("Approved excluded physical rows are absent")
    id_by_row: dict[int, int] = {}
    for row in all_rows:
        row_no = row["source_row_number"]
        legacy_id = parse_int(row.get("ddk_legacy_id"))
        if legacy_id is None or legacy_id <= 0:
            raise MissingPhysicalEvidence("Missing literal DDK source ID in row")
        id_by_row[row_no] = legacy_id
        if row_no in excluded and legacy_id != excluded[row_no][1]:
            raise MissingPhysicalEvidence("Approved exclusion disagrees with original DDK ID")

    group_payloads: list[dict[str, Any]] = []
    token_payloads: list[dict[str, Any]] = []
    dropped_rows: list[dict[str, int]] = []
    summary: Counter = Counter()
    for row_number in sorted(id_by_row):
        legacy_id = id_by_row[row_number]
        is_excluded = row_number in excluded
        if is_excluded:
            dropped_rows.append({"source_row_number": row_number, "legacy_dkkd_id": legacy_id})
        for role in sorted(DDK_GROUP_LABELS):
            matching = [
                (col, group) for (row, col), group in cells.items()
                if row == row_number and group["source_group"] == role
            ]
            if len(matching) != 1:
                raise MissingPhysicalEvidence("Missing or duplicate source group in DDK row")
            column, group = matching[0]
            if group["ddk_legacy_id"] != str(legacy_id):
                raise MissingPhysicalEvidence("Source group and DDK row identity differ")
            values = [group["fields"][name]["raw_value"] for name, _ in DDK_GROUP_FIELDS]
            source_tokens = (
                split_idcc_references(values[0]) if values[0].strip() else []
            )
            if any(not token for token in source_tokens):
                raise MissingPhysicalEvidence("Empty source ID CC token must be reviewed before planning")
            if is_excluded:
                if any(values) or source_tokens:
                    raise MissingPhysicalEvidence("Approved excluded row has populated source group")
                continue
            group_key = _source_identity(accepted_workbook_sha256, row_number, role)
            expected_columns = [column + i for i in range(4)]
            payload = {
                **group_key,
                "legacy_dkkd_id": legacy_id,
                "id_cc_excel_column": expected_columns[0],
                "certificate_scope_excel_column": expected_columns[1],
                "applicable_standard_excel_column": expected_columns[2],
                "business_activity_excel_column": expected_columns[3],
                "id_cc_raw": values[0],
                "certificate_scope_raw": values[1],
                "applicable_standard_raw": values[2],
                "business_activity_raw": values[3],
                "source_values_sha256": _source_value_digest(values),
            }
            group_payloads.append({"logical_source_key": group_key, "values": payload})
            summary[f"groups_{role}"] += 1
            summary["group_rows"] += 1
            summary["field_positions"] += 4
            if not values[0].strip() and any(x.strip() for x in values[1:]):
                summary["companion_without_id_cc"] += 1
            if role == "GDP" and values[3].strip() and not values[0].strip():
                summary["gdp_business_activity_without_id_cc"] += 1
            for index, token in enumerate(source_tokens, 1):
                legacy_cert_id = parse_int(token)
                if legacy_cert_id is None or legacy_cert_id <= 0:
                    raise MissingPhysicalEvidence("Non-positive or nonliteral source Certificate token")
                token_payloads.append({
                    "source_group_key": group_key,
                    "values": {
                        "token_index": index,
                        "raw_token": token,
                        "parsed_legacy_certificate_id": legacy_cert_id,
                    },
                })
                summary[f"tokens_{role}"] += 1
                summary["reference_tokens"] += 1

    summary["excluded_ddk_rows"] = len(dropped_rows)
    summary["effective_ddk_rows"] = len(id_by_row) - len(dropped_rows)
    summary["original_ddk_rows"] = len(id_by_row)
    if (summary["group_rows"] != summary["effective_ddk_rows"] * 4
            or summary["field_positions"] != summary["effective_ddk_rows"] * 16
            or summary["reference_tokens"] != expected_reference_tokens):
        raise MissingPhysicalEvidence("Planned provenance population differs from accepted source")
    if len({(p["values"]["source_row_number"], p["values"]["source_group"])
            for p in group_payloads}) != len(group_payloads):
        raise MissingPhysicalEvidence("Duplicate planned source-group natural key")
    if len({(x["source_group_key"]["source_row_number"],
             x["source_group_key"]["source_group"], x["values"]["token_index"])
            for x in token_payloads}) != len(token_payloads):
        raise MissingPhysicalEvidence("Duplicate planned token ordinal")

    payload = {
        "group_table": GROUP_TABLE,
        "token_table": TOKEN_TABLE,
        "source_groups": group_payloads,
        "reference_tokens": token_payloads,
    }
    return {
        "schema": PLAN_SCHEMA,
        "status": "DRY_RUN_ONLY_NOT_APPLIED",
        "source_workbook_sha256": accepted_workbook_sha256,
        "source_baseline": {
            "ddk_rows": expected_ddk_rows,
            "excluded_ddk_rows": expected_excluded_ddk_rows,
            "reference_tokens": expected_reference_tokens,
            "source_validation": observed["status"],
            "excel_com_check": "WAIVED_BY_OWNER_NOT_PERFORMED",
        },
        "target": {
            "alembic_revision_required": "20261012_0023",
            "database_state": "NOT_CONNECTED_NOT_INSPECTED",
            "foreign_key_to_canonical_certificate": False,
            "canonical_link_changes": 0,
            "sql_writes_executed": 0,
            "uuid_allocation": "NOT_PERFORMED",
        },
        "counts": dict(sorted(summary.items())),
        "excluded_source_rows": dropped_rows,
        "payload_sha256": _digest(payload),
        "payload": payload,
        "restrictions": [
            "Review-only candidate payload; no database connection or transaction",
            "Source physical identity is not a BusinessEligibilityVersion identity",
            "No canonical Certificate FK, BusinessEligibilityCertificateLink, Site coverage or case relation",
            "No inferred approval based on matching source GxP type, Company, Site or reverse ID",
            "Fresh database-state guard and explicit separate apply authorization are required",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups-json", type=Path, required=True)
    parser.add_argument("--references-json", type=Path, required=True)
    parser.add_argument("--approved-exclusions-json", type=Path, required=True)
    parser.add_argument("--expected-workbook-sha256", required=True)
    parser.add_argument("--expected-ddk-rows", type=int, required=True)
    parser.add_argument("--expected-excluded-ddk-rows", type=int, required=True)
    parser.add_argument("--expected-reference-tokens", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs = (args.groups_json, args.references_json, args.approved_exclusions_json)
    try:
        if args.output.resolve() in {x.resolve() for x in inputs}:
            raise MissingPhysicalEvidence("Refusing to overwrite any input evidence")
        original_bytes = [path.read_bytes() for path in inputs]
        grouped, references, exclusions = [
            json.loads(data.decode("utf-8")) for data in original_bytes
        ]
        result = build_source_provenance_dry_run(
            grouped, references, exclusions,
            accepted_workbook_sha256=args.expected_workbook_sha256,
            expected_ddk_rows=args.expected_ddk_rows,
            expected_excluded_ddk_rows=args.expected_excluded_ddk_rows,
            expected_reference_tokens=args.expected_reference_tokens,
        )
        result["input_artifact_sha256"] = {
            label: sha256(content).hexdigest()
            for label, content in zip(
                ("groups_json", "references_json", "approved_exclusions_json"),
                original_bytes,
            )
        }
        if [path.read_bytes() for path in inputs] != original_bytes:
            raise MissingPhysicalEvidence("Input evidence changed during dry-run planning")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as destination:
            json.dump(result, destination, ensure_ascii=False, indent=2)
            destination.write("\n")
    except (MissingPhysicalEvidence, ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, f"Source dry-run blocked: {exc}\n")
    print(json.dumps({
        "status": result["status"],
        "source_workbook_sha256": result["source_workbook_sha256"],
        "payload_sha256": result["payload_sha256"],
        "counts": result["counts"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
