"""Read-only reconciliation of two prior .xlsb exports and optional Excel-COM V3.

The two prior exports may use the SAME underlying XLSB reader. This tool
checks conservation, source-coordinate fidelity, and output agreement; it
does not independently prove formula status or approve canonical GxP links.

Run from repository root:
  py -3 -m tools.reconcile_ddk_source_artifacts --workbook SOURCE.xlsb
      --groups-json GROUPS.json --references-json REFERENCES.json
      --audit-v3-json COM_V3.json --output OUT.json

Omit --audit-v3-json for an explicitly partial independent-export-only check.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from tools.audit_ddk_idcc_physical import (
    DDK_GROUP_FIELDS, DDK_GROUP_LABELS, MissingPhysicalEvidence,
    split_idcc_references,
)

GROUP_SCHEMA = "GXP_DDK_GROUPED_SOURCE_EVIDENCE_V1"
LINK_SCHEMA = "GXP_DDK_XLSB_INDEPENDENT_SOURCE_ANALYSIS_V1"
COM_SCHEMA = "GXP_DDK_IDCC_PHYSICAL_REVIEW_V3"


def require(condition: bool, explanation: str) -> None:
    if not condition:
        raise MissingPhysicalEvidence(explanation)


def source_groups(groups: dict[str, Any]) -> tuple[dict[tuple[int, int], dict[str, Any]], Counter]:
    require(groups.get("schema") == GROUP_SCHEMA, "Unsupported grouped source export")
    rows = groups.get("source_rows")
    require(isinstance(rows, list), "Missing grouped source rows")
    require(len(rows) == groups.get("ddk_rows"), "Grouped source row count disagrees")
    layout = groups.get("header_evidence")
    require(isinstance(layout, list) and len(layout) == 4, "Four group headers required")
    positions: dict[int, str] = {}
    for item in layout:
        require(isinstance(item, dict), "Invalid group header evidence")
        col, role = item.get("id_cc_column"), item.get("group")
        require(type(col) is int and col > 0 and col not in positions
                and role in DDK_GROUP_LABELS, "Ambiguous source group identity")
        for offset, (key, label) in enumerate(DDK_GROUP_FIELDS):
            field = item.get("fields", {}).get(key)
            require(isinstance(field, dict) and field.get("source_header") == label
                    and field.get("excel_column") == col + offset,
                    "Original grouped field columns do not agree with source headers")
        positions[col] = role
    require(set(positions.values()) == DDK_GROUP_LABELS, "Source has duplicate GxP labels")

    cells: dict[tuple[int, int], dict[str, Any]] = {}
    metrics: Counter = Counter()
    seen: set[int] = set()
    for row in rows:
        require(isinstance(row, dict), "Invalid grouped source row")
        row_no = row.get("source_row_number")
        require(type(row_no) is int and row_no > 0 and row_no not in seen,
                "Missing or duplicate physical DDK row")
        seen.add(row_no)
        sections = row.get("groups")
        require(isinstance(sections, list) and len(sections) == 4,
                "DDK row does not conserve all four GxP groups")
        for section in sections:
            require(isinstance(section, dict), "Malformed GxP source group")
            col, role = section.get("id_cc_excel_column"), section.get("source_group")
            require(col in positions and positions[col] == role,
                    "Source group ownership contradicts physical header")
            key = (row_no, col)
            require(key not in cells, "Duplicate physical source group")
            fields = section.get("fields")
            require(isinstance(fields, dict) and set(fields) == {n for n, _ in DDK_GROUP_FIELDS},
                    "Source group missing one of four physical cells")
            for offset, (name, label) in enumerate(DDK_GROUP_FIELDS):
                field = fields[name]
                require(isinstance(field, dict) and field.get("excel_column") == col + offset
                        and field.get("source_header") == label
                        and isinstance(field.get("raw_value"), str),
                        "Group value or original cell coordinate is corrupt")
                metrics["source_field_cells"] += 1
                if field["raw_value"].strip():
                    metrics[f"{role}_{name}_populated"] += 1
            cells[key] = {"ddk_legacy_id": str(row.get("ddk_legacy_id")),
                          "source_group": role, "fields": fields}
            metrics["source_groups"] += 1
    require(len(cells) == len(rows) * 4, "Source group conservation failed")
    metrics["ddk_rows"] = len(rows)
    return cells, metrics


def observed_tokens(cells: dict[tuple[int, int], dict[str, Any]]) -> Counter:
    tokens: Counter = Counter()
    for key, group in cells.items():
        raw = group["fields"]["id_cc"]["raw_value"]
        if not raw.strip():
            continue
        parts = split_idcc_references(raw)
        require(all(part for part in parts),
                "Malformed or empty original source ID CC token cannot be silently skipped")
        for value in parts:
            tokens[(key[0], key[1], group["ddk_legacy_id"], group["source_group"], value)] += 1
    return tokens


def independent_references(links: dict[str, Any], cells: dict) -> Counter:
    require(links.get("schema") == LINK_SCHEMA, "Unsupported source-reference export")
    records = links.get("candidates")
    require(isinstance(records, list), "Missing source-reference candidates")
    require(len(records) == links.get("summary", {}).get("token_references"),
            "Reference export candidate count differs from declared count")
    actual: Counter = Counter()
    for item in records:
        require(isinstance(item, dict), "Invalid reference candidate")
        row, col = item.get("ddk_excel_row"), item.get("physical_col")
        key = (row, col)
        require(key in cells, "Reference lacks original physical source group")
        source = cells[key]
        require(str(item.get("ddk_id")) == source["ddk_legacy_id"],
                "Reference assigned to wrong source DDK identity")
        require(item.get("source_role") == source["source_group"],
                "Reference assigned to wrong GxP physical group")
        require(isinstance(item.get("raw_cell"), str)
                and item["raw_cell"].strip() == source["fields"]["id_cc"]["raw_value"].strip(),
                "Reference raw cell differs from original source group cell")
        token = item.get("token")
        require(isinstance(token, str) and token == token.strip(),
                "Reference source token lost or mutated")
        actual[(row, col, source["ddk_legacy_id"], source["source_group"], token)] += 1
    return actual


def compare_com_v3(audit: dict[str, Any], cells: dict, tokens: Counter,
                   workbook_sha256: str) -> None:
    require(audit.get("schema") == COM_SCHEMA
            and audit.get("grouped_source_status") == "COMPLETE_SOURCE_GROUP_PROJECTION",
            "Missing complete physically headed Excel-COM V3 source report")
    require(audit.get("source_sha256") == workbook_sha256,
            "V3 source fingerprint differs from original workbook")
    require(audit.get("approval_status") == "NOT_APPROVED_NO_RELATIONSHIPS_CREATED",
            "V3 has unexpected business approval state")
    projected = audit.get("grouped_source_rows")
    require(isinstance(projected, list), "Missing V3 grouped source rows")
    require(len(projected) * 4 == len(cells), "V3 source row count disagrees")
    checked: set[tuple[int, int]] = set()
    for row in projected:
        require(isinstance(row, dict), "Invalid V3 source row")
        row_no = row.get("source_row_number")
        for section in row.get("groups", []):
            col = section.get("id_cc_excel_column")
            key = (row_no, col)
            require(key in cells and key not in checked, "V3 group row/column mismatch")
            original = cells[key]
            require(section.get("source_group") == original["source_group"]
                    and str(row.get("ddk_legacy_id")) == original["ddk_legacy_id"],
                    "V3 source group assigned to wrong DDK/role")
            for name, _ in DDK_GROUP_FIELDS:
                value = section.get("fields", {}).get(name, {}).get("raw_value")
                require(isinstance(value, str), "V3 group value is missing")
                # Prior independent exports used .strip(), but newer COM V3
                # retains original Value2 source spaces and line breaks.
                require(value.strip() == original["fields"][name]["raw_value"].strip(),
                        "V3 source cell differs from independently exported XLSB value")
            checked.add(key)
    require(checked == set(cells), "Unreconciled V3 physical source cells")
    v3refs = audit.get("candidates")
    require(isinstance(v3refs, list) and len(v3refs) == audit.get("candidate_count"),
            "Missing or incomplete V3 reference candidates")
    actual: Counter = Counter()
    for item in v3refs:
        require(isinstance(item, dict), "Invalid V3 candidate record")
        key = (item.get("source_row_number"), item.get("excel_column"))
        require(key in cells, "V3 candidate is outside original group")
        group = cells[key]
        require(item.get("raw_fk_token") is not None
                and item.get("observed_group_header") == group["source_group"]
                and str(item.get("ddk_legacy_id")) == group["ddk_legacy_id"],
                "V3 candidate assigned to wrong source group/token")
        actual[(key[0], key[1], group["ddk_legacy_id"], group["source_group"],
                item["raw_fk_token"])] += 1
    require(actual == tokens, "V3 references disagree with original 861-token source multiset")


def reconcile(*, workbook_hash: str, grouped: dict, links: dict,
              v3_audit: dict | None = None) -> dict[str, Any]:
    require(len(workbook_hash) == 64, "Source workbook hash must be SHA-256")
    require(grouped.get("source_sha256") == workbook_hash
            and links.get("source_workbook_sha256") == workbook_hash,
            "Input artifact fingerprints differ from original binary workbook")
    cells, metrics = source_groups(grouped)
    source_counter = observed_tokens(cells)
    actual = independent_references(links, cells)
    require(source_counter == actual, "Independent references disagree with original source")
    require(links.get("summary", {}).get("ddk_rows") == metrics["ddk_rows"],
            "Independent source row counts disagree")
    if v3_audit is not None:
        compare_com_v3(v3_audit, cells, source_counter, workbook_hash)
    metrics["reference_tokens"] = sum(source_counter.values())
    return {
        "schema": "GXP_DDK_SOURCE_RECONCILIATION_V1",
        "status": (
            "COM_V3_AND_INDEPENDENT_EXPORTS_CONSISTENT"
            if v3_audit is not None else "PARTIAL_INDEPENDENT_EXPORTS_ONLY"
        ),
        "approval_status": "NOT_APPROVED_NO_LINKS_CREATED",
        "original_workbook_sha256": workbook_hash,
        "metrics": dict(sorted(metrics.items())),
        "caveats": [
            "Prior grouped/reference exports may share the same XLSB reader; agreement does not prove independent engines",
            "Prior exports normalized leading/trailing whitespace; comparison with COM V3 trims only for compatibility",
            "Only Excel COM validates HasFormula and literal ID CC evidence; partial mode cannot assert this gate",
            "No approved Certificate, CertificateVersion, DDK historical version, or Site coverage links created",
            "PostgreSQL rehearsal and production databases were not accessed",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--groups-json", type=Path, required=True)
    parser.add_argument("--references-json", type=Path, required=True)
    parser.add_argument("--audit-v3-json", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs = [args.workbook, args.groups_json, args.references_json]
    if args.audit_v3_json is not None:
        inputs.append(args.audit_v3_json)
    try:
        if args.output.resolve() in {p.resolve() for p in inputs}:
            raise MissingPhysicalEvidence("Output path overlaps an input source")
        workbook_sha = sha256(args.workbook.read_bytes()).hexdigest()
        source_bytes = [p.read_bytes() for p in inputs[1:]]
        grouped = json.loads(source_bytes[0].decode("utf-8"))
        linked = json.loads(source_bytes[1].decode("utf-8"))
        audit_v3 = json.loads(source_bytes[2].decode("utf-8")) if len(source_bytes) == 3 else None
        result = reconcile(workbook_hash=workbook_sha, grouped=grouped,
                           links=linked, v3_audit=audit_v3)
        # Seal the precise input JSON bytes independently of the original binary.
        result["input_artifact_sha256"] = {
            path.name: sha256(content).hexdigest()
            for path, content in zip(inputs[1:], source_bytes)
        }
        if sha256(args.workbook.read_bytes()).hexdigest() != workbook_sha:
            raise MissingPhysicalEvidence("Source workbook changed during reconciliation")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    except (MissingPhysicalEvidence, OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"DDK source reconciliation blocked: {exc}\n")
    print(json.dumps({"status": result["status"], "metrics": result["metrics"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
