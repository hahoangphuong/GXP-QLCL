from __future__ import annotations

"""Legacy evaluation-scope taxonomy and payload evidence helpers.

These helpers deliberately classify legacy data; they never infer selections from
rendered prose.  Canonical persistence is intentionally deferred to Slice C.5c.
"""

from collections import Counter, defaultdict
from hashlib import sha256
import json
import re
from typing import Any, Iterable


TAXONOMY_SCHEMA_VERSION = "evaluation-scope-taxonomy/v1"
PARSER_SCHEMA_VERSION = "evaluation-scope-parser/v1"
# DCForm.Init_PVCN loads these workbook-level ranges for the active legacy modes.
# The current workbook has no PVCN_GDP definition, even though a dormant Case 6
# branch still references that name.  Do not fabricate an empty GDP taxonomy.
TAXONOMY_RANGE_DEFINITIONS = (
    ("PVCN_GMP", "GMP", True),
    ("PVCN_GLP", "GLP", True),
    ("PVCN_GSP", "GSP", True),
    ("PVCN_GDP", "GDP", False),
)
KEY_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")
# DCForm.SetNodeValue appends an ordinal and '+' when it renders a temporary
# semicolon subnode.  It is not a source-taxonomy key.
RUNTIME_SYNTHETIC_KEY_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+)+\+$")


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def taxonomy_content_hash(named_ranges: dict[str, dict[str, Any]]) -> str:
    """Hash semantic source data, excluding volatile workbook/export metadata."""
    semantic = {
        name: {
            "gxp_type": item["gxp_type"],
            "source_name": item["source_name"],
            "source_columns": item["source_columns"],
            "rows": item["rows"],
        }
        for name, item in sorted(named_ranges.items())
    }
    return sha256(_canonical_json(semantic)).hexdigest()


def build_taxonomy_artifact(
    *,
    workbook_name: str,
    workbook_sha256: str | None,
    ranges: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build a deterministic, source-preserving taxonomy artifact from COM rows."""
    named_ranges: dict[str, dict[str, Any]] = {}
    for source_name, gxp_type, required in TAXONOMY_RANGE_DEFINITIONS:
        source = ranges.get(source_name)
        if source is None:
            if required:
                raise ValueError(f"Required named range is missing: {source_name}")
            continue
        values = source["values"]
        if not isinstance(values, list):
            raise ValueError(f"Named range {source_name} values must be a list.")
        start_row = int(source["start_row"])
        sheet_name = str(source["sheet_name"])
        rows: list[dict[str, Any]] = []
        for index, raw_cells in enumerate(values, start=1):
            cells = ["" if value is None else str(value).strip() for value in raw_cells]
            # VBA uses columns 1, 2, 4, 6, 7 and 8. Preserve every cell too.
            def cell(column: int) -> str:
                return cells[column - 1] if len(cells) >= column else ""

            rows.append(
                {
                    "source_order": index,
                    "source_excel_row": start_row + index - 1,
                    "key": cell(1),
                    "description": cell(2),
                    "hint": cell(4),
                    "main_topic": cell(6),
                    "short_render": cell(7),
                    "no_expand": cell(8),
                    "raw_cells": cells,
                }
            )
        named_ranges[source_name] = {
            "gxp_type": gxp_type,
            "source_name": source_name,
            "sheet_name": sheet_name,
            "source_columns": {
                "key": 1,
                "description": 2,
                "hint": 4,
                "main_topic": 6,
                "short_render": 7,
                "no_expand": 8,
            },
            "rows": rows,
        }
    availability = {
        gxp_type: (
            {"status": "available", "source_name": source_name}
            if source_name in named_ranges
            else {"status": "unavailable", "reason": "not_defined_in_legacy_workbook"}
        )
        for source_name, gxp_type, _ in TAXONOMY_RANGE_DEFINITIONS
    }
    return {
        "schema_version": TAXONOMY_SCHEMA_VERSION,
        "source_workbook": workbook_name,
        "source_workbook_sha256": workbook_sha256,
        "named_ranges": named_ranges,
        "taxonomy_availability": availability,
        "taxonomy_content_sha256": taxonomy_content_hash(named_ranges),
    }


def _parent_keys(key: str) -> list[str]:
    pieces = key.split(".")
    return [".".join(pieces[:index]) for index in range(1, len(pieces))]


def validate_taxonomy_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    results: dict[str, Any] = {"ranges": {}, "anomaly_count": 0}
    for name, definition in artifact["named_ranges"].items():
        rows = definition["rows"]
        keys: dict[str, int] = {}
        anomalies: list[dict[str, Any]] = []
        synthetic: set[str] = set()
        for row in rows:
            key = row["key"]
            order = row["source_order"]
            if not key:
                anomalies.append({"kind": "blank_key", "source_order": order})
                continue
            if not KEY_PATTERN.fullmatch(key):
                anomalies.append({"kind": "malformed_key", "key": key, "source_order": order})
                continue
            if key in keys:
                anomalies.append({"kind": "duplicate_key", "key": key, "source_order": order, "first_source_order": keys[key]})
            else:
                keys[key] = order
        for key in keys:
            synthetic.update(parent for parent in _parent_keys(key) if parent not in keys)
        results["ranges"][name] = {
            "gxp_type": definition["gxp_type"],
            "source_node_count": len(keys),
            "synthetic_structural_parent_keys": sorted(synthetic, key=lambda item: tuple(int(x) for x in item.split("."))),
            "anomalies": anomalies,
        }
        results["anomaly_count"] += len(anomalies)
    return results


def validate_taxonomy_integrity(artifact: dict[str, Any]) -> dict[str, Any]:
    """Fail closed on unsupported or internally inconsistent taxonomy evidence."""
    if artifact.get("schema_version") != TAXONOMY_SCHEMA_VERSION:
        raise ValueError(f"Unsupported taxonomy schema version: {artifact.get('schema_version')!r}")
    named_ranges = artifact.get("named_ranges")
    if not isinstance(named_ranges, dict):
        raise ValueError("Taxonomy artifact named_ranges must be an object.")
    expected_range_names = {source_name for source_name, _, _ in TAXONOMY_RANGE_DEFINITIONS}
    unexpected_ranges = sorted(set(named_ranges) - expected_range_names)
    if unexpected_ranges:
        raise ValueError(f"Taxonomy artifact has unsupported named ranges: {', '.join(unexpected_ranges)}")
    expected_hash = artifact.get("taxonomy_content_sha256")
    actual_hash = taxonomy_content_hash(named_ranges)
    if expected_hash != actual_hash:
        raise ValueError("Taxonomy artifact semantic hash does not match its named ranges.")

    availability = artifact.get("taxonomy_availability")
    if not isinstance(availability, dict):
        raise ValueError("Taxonomy artifact taxonomy_availability must be an object.")
    for source_name, gxp_type, required in TAXONOMY_RANGE_DEFINITIONS:
        definition = named_ranges.get(source_name)
        declared = availability.get(gxp_type)
        if required and definition is None:
            raise ValueError(f"Required taxonomy range is missing: {source_name}")
        if definition is not None:
            if definition.get("source_name") != source_name or definition.get("gxp_type") != gxp_type:
                raise ValueError(f"Taxonomy range source consistency failure: {source_name}")
            if not isinstance(definition.get("rows"), list):
                raise ValueError(f"Taxonomy range rows must be a list: {source_name}")
            if declared != {"status": "available", "source_name": source_name}:
                raise ValueError(f"Taxonomy availability consistency failure: {gxp_type}")
        elif declared is None or declared.get("status") != "unavailable":
            raise ValueError(f"Taxonomy availability is missing for {gxp_type}")

    validation = validate_taxonomy_artifact(artifact)
    for source_name, _, required in TAXONOMY_RANGE_DEFINITIONS:
        if not required:
            continue
        duplicate = any(item["kind"] == "duplicate_key" for item in validation["ranges"][source_name]["anomalies"])
        if duplicate:
            raise ValueError(f"Required taxonomy range has duplicate source keys: {source_name}")
    return {
        "schema_version": artifact["schema_version"],
        "taxonomy_content_sha256": actual_hash,
        "taxonomy_availability": availability,
        "validation": validation,
    }


def taxonomy_statistics(artifact: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    """Produce deterministic source-shape facts for the future canonical model."""
    result: dict[str, Any] = {}
    for name, definition in artifact["named_ranges"].items():
        rows = definition["rows"]
        valid_keys = [row["key"] for row in rows if KEY_PATTERN.fullmatch(row["key"])]
        range_validation = validation["ranges"][name]
        result[definition["gxp_type"]] = {
            "source_name": name,
            "source_sheet": definition["sheet_name"],
            "source_row_count": len(rows),
            "source_node_count": range_validation["source_node_count"],
            "source_row_span": [min(row["source_excel_row"] for row in rows), max(row["source_excel_row"] for row in rows)] if rows else None,
            "duplicate_key_count": sum(item["kind"] == "duplicate_key" for item in range_validation["anomalies"]),
            "malformed_key_count": sum(item["kind"] == "malformed_key" for item in range_validation["anomalies"]),
            "synthetic_structural_parent_count": len(range_validation["synthetic_structural_parent_keys"]),
            "synthetic_structural_parent_keys": range_validation["synthetic_structural_parent_keys"],
            "maximum_hierarchy_depth": max((key.count(".") + 1 for key in valid_keys), default=0),
            "root_level_node_count": sum("." not in key for key in valid_keys),
            "main_topic_count": sum(bool(row["main_topic"]) for row in rows),
            "no_expand_count": sum(bool(row["no_expand"]) for row in rows),
            "semicolon_runtime_candidate_count": sum(";" in row["description"] for row in rows),
        }
    return dict(sorted(result.items()))


def _parse_entries(payload: str, diagnostics: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    unkeyed: list[dict[str, Any]] = []
    for order, raw_line in enumerate(payload.replace("\n", "").split("\r"), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("- "):
            unkeyed.append({"source_order": order, "text": line})
            continue
        separator = ":" if ":" in line else (" " if " " in line else None)
        key, description = (line.split(separator, 1) if separator else (line, ""))
        key, description = key.strip(), description.strip()
        key_kind = "SOURCE_NODE" if KEY_PATTERN.fullmatch(key) else "RUNTIME_SYNTHETIC_NODE" if RUNTIME_SYNTHETIC_KEY_PATTERN.fullmatch(key) else None
        if key_kind is None:
            # DCForm.LoadNodeList preserves non-taxonomy lines as free entries.
            unkeyed.append({"source_order": order, "text": line})
            continue
        selected.append({"source_order": order, "key": key, "description": description, "key_kind": key_kind})
    return selected, unkeyed


def _taxonomy_validation_state(taxonomy: dict[str, Any], gxp_type: str | None) -> dict[str, str]:
    if gxp_type is None:
        return {"status": "unavailable", "reason": "missing_gxp_context"}
    availability = taxonomy.get("taxonomy_availability", {})
    declared = availability.get(gxp_type)
    if declared is not None:
        return dict(declared)
    if any(definition["gxp_type"] == gxp_type for definition in taxonomy["named_ranges"].values()):
        return {"status": "available"}
    return {"status": "unavailable", "reason": "not_defined_in_legacy_workbook"}


def parse_legacy_evaluation_scope(raw_value: str | None, *, gxp_type: str | None = None, taxonomy: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = "" if raw_value is None else str(raw_value)
    result: dict[str, Any] = {
        "parser_schema_version": PARSER_SCHEMA_VERSION,
        "raw_value": raw,
        "gxp_type": gxp_type,
        "classification": "BLANK",
        "rendered_prose": "",
        "limitation_text": None,
        "scopes": [],
        "diagnostics": [],
        "taxonomy_validation": {"status": "not_provided"},
    }
    if taxonomy is not None:
        result["taxonomy_validation"] = _taxonomy_validation_state(taxonomy, gxp_type)
    if not raw.strip():
        return result
    if not raw.rstrip().endswith("}*"):
        # Braces are only structural in the persisted VBA suffix.  Treat a
        # partial suffix as malformed rather than silently accepting it as prose.
        if "{" in raw or "}*" in raw:
            result["classification"] = "STRUCTURED_MALFORMED"
            result["diagnostics"].append({"kind": "truncated_or_invalid_structured_suffix"})
            return result
        result["classification"] = "PROSE_ONLY"
        result["rendered_prose"] = raw
        return result
    close_start = len(raw.rstrip()) - 2
    open_index = raw.rfind("{", 0, close_start)
    if open_index < 0:
        result["classification"] = "STRUCTURED_MALFORMED"
        result["diagnostics"].append({"kind": "missing_open_brace"})
        return result
    prefix = raw[:open_index]
    payload = raw[open_index + 1 : close_start]
    limitation_start = prefix.rfind("(*")
    if limitation_start >= 0:
        limitation_end = prefix.rfind("*)")
        if limitation_end < limitation_start:
            result["classification"] = "STRUCTURED_MALFORMED"
            result["diagnostics"].append({"kind": "unterminated_limitation"})
            return result
        result["limitation_text"] = prefix[limitation_start + 2 : limitation_end].strip()
        prefix = prefix[:limitation_start]
    result["rendered_prose"] = prefix.rstrip("\r\n")
    for scope_order, raw_scope in enumerate(payload.split("§"), start=1):
        name, note, selection_payload = "", "", raw_scope
        if "¶" in selection_payload:
            name, selection_payload = selection_payload.split("¶", 1)
        if "¿" in selection_payload:
            selection_payload, note = selection_payload.rsplit("¿", 1)
        selected, unkeyed = _parse_entries(selection_payload, result["diagnostics"])
        seen: set[str] = set()
        for item in selected:
            item["taxonomy_status"] = "NOT_EVALUATED"
            if item["key"] in seen:
                result["diagnostics"].append({"kind": "duplicate_selected_key", "key": item["key"]})
            seen.add(item["key"])
        result["scopes"].append({
            "source_order": scope_order,
            "name": name.strip(),
            "note": note.strip(),
            "selected_nodes": selected,
            "unkeyed_entries": unkeyed,
            "raw_value": raw_scope,
        })
    if not result["scopes"] or not any(scope["selected_nodes"] or scope["unkeyed_entries"] for scope in result["scopes"]):
        result["classification"] = "STRUCTURED_MALFORMED"
        result["diagnostics"].append({"kind": "empty_structured_payload"})
        return result
    if taxonomy is not None:
        is_available = result["taxonomy_validation"]["status"] == "available"
        known = {
            row["key"]
            for definition in taxonomy["named_ranges"].values()
            if definition["gxp_type"] == gxp_type
            for row in definition["rows"]
            if row["key"]
        }
        for scope in result["scopes"]:
            for item in scope["selected_nodes"]:
                if item["key_kind"] == "RUNTIME_SYNTHETIC_NODE":
                    parent_key = item["key"][:-1].rsplit(".", 1)[0]
                    item["runtime_parent_key"] = parent_key
                    item["taxonomy_status"] = "RUNTIME_SYNTHETIC_NODE"
                    if is_available and parent_key not in known:
                        item["taxonomy_status"] = "UNRESOLVED_RUNTIME_NODE"
                        result["diagnostics"].append({"kind": "unresolved_runtime_node", "key": item["key"]})
                else:
                    item["taxonomy_status"] = (
                        "KNOWN_NODE"
                        if is_available and item["key"] in known
                        else "UNKNOWN_NODE"
                        if is_available
                        else "TAXONOMY_UNAVAILABLE"
                    )
                if item["taxonomy_status"] == "UNKNOWN_NODE":
                    result["diagnostics"].append({"kind": "unknown_node_key", "key": item["key"]})
    diagnostic_kinds = {item["kind"] for item in result["diagnostics"]}
    result["classification"] = "STRUCTURED_PARTIAL" if diagnostic_kinds & {"duplicate_selected_key", "unknown_node_key", "invalid_selection_line", "unresolved_runtime_node"} else "STRUCTURED_VALID"
    return result


def _record_identity(row: dict[str, Any]) -> dict[str, Any]:
    code = row.get("Mã hồ sơ")
    return {
        "legacy_inspection_id": row.get("ID"),
        "legacy_inspection_code": code if code not in {None, "", "-"} else None,
    }


def _selection_record(row: dict[str, Any], parsed: dict[str, Any], scope: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    return {
        **_record_identity(row),
        "gxp_type": parsed["gxp_type"],
        "scope_ordinal": scope["source_order"],
        "source_order": item["source_order"],
        "key": item["key"],
        "description": item["description"],
        "taxonomy_status": item["taxonomy_status"],
        "raw_value": parsed["raw_value"],
    }


def _unknown_record(row: dict[str, Any], parsed: dict[str, Any], scope: dict[str, Any], item: dict[str, Any], taxonomy: dict[str, Any] | None) -> dict[str, Any]:
    record = _selection_record(row, parsed, scope, item)
    other_gxps = sorted(
        {
            definition["gxp_type"]
            for definition in (taxonomy or {}).get("named_ranges", {}).values()
            if definition["gxp_type"] != parsed["gxp_type"]
            for source_row in definition["rows"]
            if source_row["key"] == item["key"]
        }
    )
    record["unknown_key_family"] = "FOREIGN_GXP_KEY" if other_gxps else "UNRESOLVED_UNKNOWN"
    if other_gxps:
        record["foreign_gxp_types"] = other_gxps
    return record


def _unknown_key_analysis(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_key: Counter[str] = Counter(record["key"] for record in records)
    by_gxp: Counter[str] = Counter(str(record["gxp_type"] or "(blank)") for record in records)
    by_family: Counter[str] = Counter(record["unknown_key_family"] for record in records)
    representatives: dict[str, Any] = {}
    for record in records:
        representatives.setdefault(record["key"], record["legacy_inspection_id"])
    return {
        "count": len(records),
        "count_by_key": dict(sorted(by_key.items())),
        "count_by_gxp": dict(sorted(by_gxp.items())),
        "count_by_family": dict(sorted(by_family.items())),
        "representative_legacy_inspection_id_by_key": dict(sorted(representatives.items())),
        "records": records,
    }


def _update_importability(counts: Counter[str], parsed: dict[str, Any]) -> None:
    classification = parsed["classification"]
    if classification == "BLANK":
        counts["BLANK"] += 1
    elif classification == "PROSE_ONLY":
        counts["RAW_ONLY_PROSE"] += 1
    elif classification == "STRUCTURED_MALFORMED":
        counts["RAW_ONLY_MALFORMED"] += 1
    elif classification == "STRUCTURED_PARTIAL":
        counts["PARTIAL_REVIEW_REQUIRED"] += 1
    elif parsed["taxonomy_validation"]["status"] != "available":
        counts["TAXONOMY_UNAVAILABLE"] += 1
    else:
        counts["CANONICALIZABLE"] += 1


def classify_scope_corpus(rows: Iterable[dict[str, Any]], *, taxonomy: dict[str, Any] | None = None) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    by_gxp: dict[str, Counter[str]] = defaultdict(Counter)
    diagnostics: Counter[str] = Counter()
    validation: dict[str, Counter[str]] = defaultdict(Counter)
    node_statuses: Counter[str] = Counter()
    node_statuses_by_gxp: dict[str, Counter[str]] = defaultdict(Counter)
    node_statuses_by_classification: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    importability: Counter[str] = Counter()
    custom_descriptions: Counter[str] = Counter()
    multi_scope: Counter[str] = Counter()
    unknown_records: list[dict[str, Any]] = []
    runtime_records: list[dict[str, Any]] = []
    known_descriptions = {
        (definition["gxp_type"], row["key"]): row["description"]
        for definition in (taxonomy or {}).get("named_ranges", {}).values()
        for row in definition["rows"]
        if row["key"]
    }
    records: list[dict[str, Any]] = []
    for row in rows:
        gxp_type = str(row.get("LOẠI KT") or "") or None
        parsed = parse_legacy_evaluation_scope(row.get("PHẠM VI KIỂM TRA"), gxp_type=gxp_type, taxonomy=taxonomy)
        counts[parsed["classification"]] += 1
        by_gxp[gxp_type or "(blank)"][parsed["classification"]] += 1
        validation[gxp_type or "(blank)"][parsed["taxonomy_validation"]["status"]] += 1
        _update_importability(importability, parsed)
        if len(parsed["scopes"]) > 1:
            multi_scope["cases_with_multiple_scope_blocks"] += 1
        if parsed["limitation_text"] is not None:
            multi_scope["cases_with_limitation"] += 1
        for diagnostic in parsed["diagnostics"]:
            diagnostics[diagnostic["kind"]] += 1
        for scope in parsed["scopes"]:
            if scope["name"]:
                multi_scope["named_scope_blocks"] += 1
            if scope["note"]:
                multi_scope["scope_notes"] += 1
            multi_scope["unkeyed_entries"] += len(scope["unkeyed_entries"])
            for item in scope["selected_nodes"]:
                status = item["taxonomy_status"]
                node_statuses[status] += 1
                node_statuses_by_gxp[gxp_type or "(blank)"][status] += 1
                node_statuses_by_classification[gxp_type or "(blank)"][parsed["classification"]][status] += 1
                if status == "KNOWN_NODE":
                    source_description = known_descriptions[(gxp_type, item["key"])]
                    custom_descriptions["blank_custom_description" if not item["description"] else "exact_source_description" if item["description"] == source_description else "changed_custom_description"] += 1
                if status == "UNKNOWN_NODE":
                    unknown_records.append(_unknown_record(row, parsed, scope, item, taxonomy))
                if status in {"RUNTIME_SYNTHETIC_NODE", "UNRESOLVED_RUNTIME_NODE"}:
                    runtime_records.append(_selection_record(row, parsed, scope, item))
        if parsed["classification"] not in {"BLANK", "STRUCTURED_VALID", "PROSE_ONLY"}:
            records.append({**_record_identity(row), "gxp_type": gxp_type, "classification": parsed["classification"], "diagnostics": parsed["diagnostics"], "raw_value": parsed["raw_value"]})
    return {
        "parser_schema_version": PARSER_SCHEMA_VERSION,
        "taxonomy_validation_available": taxonomy is not None,
        "counts": dict(sorted(counts.items())),
        "counts_by_gxp": {key: dict(sorted(value.items())) for key, value in sorted(by_gxp.items())},
        "taxonomy_validation_by_gxp": {key: dict(sorted(value.items())) for key, value in sorted(validation.items())},
        "selected_node_status_counts": dict(sorted(node_statuses.items())),
        "selected_node_status_counts_by_gxp": {key: dict(sorted(value.items())) for key, value in sorted(node_statuses_by_gxp.items())},
        "selected_node_status_counts_by_gxp_and_classification": {gxp: {classification: dict(sorted(statuses.items())) for classification, statuses in sorted(classifications.items())} for gxp, classifications in sorted(node_statuses_by_classification.items())},
        "custom_description_counts": dict(sorted(custom_descriptions.items())),
        "multi_scope_statistics": dict(sorted(multi_scope.items())),
        "importability_counts": dict(sorted(importability.items())),
        "unknown_key_analysis": _unknown_key_analysis(unknown_records),
        "runtime_synthetic_node_records": runtime_records,
        "diagnostic_counts": dict(sorted(diagnostics.items())),
        "anomaly_records": records,
    }
