from __future__ import annotations

"""Audit B1a shadow-node parity without changing the production renderer."""

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.app.domain.evaluation_scope import (
    _canonical_node_text,
    build_shadow_node_render_spans,
    parse_legacy_evaluation_scope,
    validate_evaluation_scope_spans,
)


SNAPSHOT_PATH = REPOSITORY_ROOT / "artifacts/phase3c/legacy_snapshot.json"
TAXONOMY_PATH = REPOSITORY_ROOT / "artifacts/legacy_snapshot/evaluation_scope_taxonomy.json"
OUTPUT_PATH = REPOSITORY_ROOT / "artifacts/legacy_audit/evaluation_scope_shadow_node_parity.json"
MAX_FINDINGS = 25


def _marker_family(short_render: str) -> str:
    stripped = short_render.strip()
    if not stripped:
        return "BLANK"
    markers = "".join(
        marker
        for marker, present in (
            ("CONTINUATION", stripped.startswith("<")),
            ("AMPERSAND", stripped.lstrip("<").startswith("&")),
            ("DOLLAR_TEMPLATE", "$$" in stripped),
        )
        if present
    )
    return markers or "PLAIN"


def _custom_disposition(short_render: str, custom_description: str, rendered_text: str) -> str:
    if not rendered_text:
        return "STRUCTURAL_ONLY"
    if not custom_description.strip():
        return "NOT_APPLICABLE"
    return "TEMPLATE_SUBSTITUTED" if "$$" in short_render else "APPENDED"


def _record_finding(findings: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    if len(findings) < MAX_FINDINGS:
        findings.append(payload)


def _node_occurrences(parsed: dict[str, Any], taxonomy_rows: list[dict[str, Any]]) -> list[tuple[int, str, dict[str, Any], str, str]]:
    """Mirror production's per-block selected/ancestor traversal and de-duplication."""
    nodes = [{**node, "id": str(index)} for index, node in enumerate(taxonomy_rows, start=1)]
    node_by_key = {str(node["key"]): node for node in nodes}
    occurrences: list[tuple[int, str, dict[str, Any], str, str]] = []
    for block_ordinal, scope in enumerate(parsed["scopes"], start=1):
        selected = {str(item["key"]): str(item.get("description") or "") for item in scope["selected_nodes"]}
        emitted: set[str] = set()
        for selected_key in sorted(selected, key=lambda key: int(node_by_key[key]["source_order"])):
            for length in range(1, len(selected_key.split("."))):
                ancestor_key = ".".join(selected_key.split(".")[:length])
                ancestor = node_by_key[ancestor_key]
                if ancestor["id"] not in emitted:
                    emitted.add(ancestor["id"])
                    occurrences.append((block_ordinal, "required_ancestor", ancestor, ancestor_key, selected.get(ancestor_key, "")))
            node = node_by_key[selected_key]
            if node["id"] not in emitted:
                emitted.add(node["id"])
                occurrences.append((block_ordinal, "selected_node", node, selected_key, selected[selected_key]))
    return occurrences


def main() -> None:
    snapshot_bytes = SNAPSHOT_PATH.read_bytes()
    taxonomy_bytes = TAXONOMY_PATH.read_bytes()
    snapshot = json.loads(snapshot_bytes)
    taxonomy = json.loads(taxonomy_bytes)
    rows_by_gxp = {definition["gxp_type"]: definition["rows"] for definition in taxonomy["named_ranges"].values()}
    counts: Counter[str] = Counter()
    unique_combinations: set[tuple[str, str, str, str, str]] = set()
    findings: list[dict[str, Any]] = []

    for inspection in snapshot["db.ktra"]:
        gxp_type = str(inspection.get("LOẠI KT") or "")
        parsed = parse_legacy_evaluation_scope(inspection.get("PHẠM VI KIỂM TRA"), gxp_type=gxp_type, taxonomy=taxonomy)
        if parsed["classification"] != "STRUCTURED_VALID":
            continue
        counts["structured_records"] += 1
        for block_ordinal, role, node, node_key, custom_description in _node_occurrences(parsed, rows_by_gxp[gxp_type]):
            short_render = str(node.get("short_render") or "")
            contribution_id = f"{gxp_type}:{inspection.get('ID ĐỢT KTRA') or inspection.get('ID') or '(blank)'}:{block_ordinal}:{node_key}"
            expected_text, expected_continuation, expected_opens_group = _canonical_node_text(short_render, custom_description)
            shadow = build_shadow_node_render_spans(node, custom_description, contribution_id)
            actual_text = "".join(span.text for span in shadow.spans)
            counts["total_render_occurrences"] += 1
            counts[role] += 1
            counts[f"marker::{_marker_family(short_render)}"] += 1
            counts[f"disposition::{_custom_disposition(short_render, custom_description, expected_text)}"] += 1
            if not expected_text:
                counts["structural_only"] += 1
            unique_combinations.add((gxp_type, node_key, short_render, custom_description, role))
            if actual_text != expected_text:
                counts["text_mismatches"] += 1
                _record_finding(findings, {"kind": "text_mismatch", "contribution_id": contribution_id, "expected": expected_text, "actual": actual_text})
            if shadow.continuation != expected_continuation:
                counts["continuation_mismatches"] += 1
                _record_finding(findings, {"kind": "continuation_mismatch", "contribution_id": contribution_id})
            if shadow.opens_group != expected_opens_group:
                counts["opens_group_mismatches"] += 1
                _record_finding(findings, {"kind": "opens_group_mismatch", "contribution_id": contribution_id})
            if any(not span.text for span in shadow.spans):
                counts["unexpected_empty_spans"] += 1
            if any(not span.contribution_id or span.owner_type not in {"source", "renderer"} for span in shadow.spans):
                counts["ownership_failures"] += 1
            try:
                validate_evaluation_scope_spans(actual_text, shadow.spans)
            except ValueError as exc:
                counts["span_integrity_failures"] += 1
                _record_finding(findings, {"kind": "span_integrity_failure", "contribution_id": contribution_id, "detail": str(exc)})

    result = {
        "schema_version": "evaluation-scope-shadow-node-parity/v1",
        "snapshot_sha256": sha256(snapshot_bytes).hexdigest(),
        "taxonomy_sha256": sha256(taxonomy_bytes).hexdigest(),
        "structured_records": counts["structured_records"],
        "selected_node_occurrences": counts["selected_node"],
        "required_ancestor_occurrences": counts["required_ancestor"],
        "total_render_occurrences": counts["total_render_occurrences"],
        "unique_combinations": len(unique_combinations),
        "marker_distribution": {key.removeprefix("marker::"): value for key, value in sorted(counts.items()) if key.startswith("marker::")},
        "custom_description_disposition": {key.removeprefix("disposition::"): value for key, value in sorted(counts.items()) if key.startswith("disposition::")},
        "structural_only": counts["structural_only"],
        "text_mismatches": counts["text_mismatches"],
        "continuation_mismatches": counts["continuation_mismatches"],
        "opens_group_mismatches": counts["opens_group_mismatches"],
        "ownership_failures": counts["ownership_failures"],
        "span_integrity_failures": counts["span_integrity_failures"],
        "unexpected_empty_spans": counts["unexpected_empty_spans"],
        "bounded_findings": findings,
    }
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failed = (
        "text_mismatches",
        "continuation_mismatches",
        "opens_group_mismatches",
        "ownership_failures",
        "span_integrity_failures",
        "unexpected_empty_spans",
    )
    if any(result[key] for key in failed):
        raise SystemExit("Shadow node parity audit failed; see artifact for bounded findings.")


if __name__ == "__main__":
    main()
