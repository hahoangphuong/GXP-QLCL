"""Deterministically audit canonical evaluation-scope projections from snapshots."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.domain.evaluation_scope import parse_legacy_evaluation_scope, render_evaluation_scope_summary


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _syntax_findings(text: str) -> list[str]:
    findings: list[str] = []
    if re.search(r":;|;;|::|\(\)|[ \t]+[;:).]", text):
        findings.append("renderer_punctuation")
    if text.count("(") != text.count(")"):
        findings.append("unbalanced_parentheses")
    if "\n\n\n" in text:
        findings.append("triple_blank_line")
    if any(not line.strip() for line in text.splitlines()[1:-1]):
        findings.append("empty_generated_line")
    return findings


def audit(snapshot: dict, taxonomy: dict) -> dict:
    ranges = {item["gxp_type"]: item["rows"] for item in taxonomy["named_ranges"].values()}
    counts: Counter[str] = Counter()
    by_gxp: defaultdict[str, Counter[str]] = defaultdict(Counter)
    examples: list[dict] = []
    for row in snapshot["db.ktra"]:
        gxp = row.get("LOẠI KT")
        parsed = parse_legacy_evaluation_scope(row.get("PHẠM VI KIỂM TRA"), gxp_type=gxp, taxonomy=taxonomy)
        if parsed["classification"] != "STRUCTURED_VALID":
            continue
        source_nodes = ranges[gxp]
        nodes = [{**node, "id": str(index)} for index, node in enumerate(source_nodes, 1)]
        by_key = {node["key"]: node for node in nodes}
        blocks = []
        for ordinal, scope in enumerate(parsed["scopes"], 1):
            selections = [
                {"taxonomy_node_id": by_key[item["key"]]["id"], "source_order": item["source_order"], "custom_description": item["description"]}
                for item in scope["selected_nodes"]
            ]
            blocks.append({"id": str(ordinal), "ordinal": ordinal, "name": scope["name"], "note": scope["note"], "selections": selections, "unkeyed_entries": scope["unkeyed_entries"]})
        summary = render_evaluation_scope_summary(blocks=blocks, taxonomy_nodes=nodes, limitation_text=parsed["limitation_text"])
        counts["records"] += 1; by_gxp[gxp]["records"] += 1
        selected = [item for block in blocks for item in block["selections"]]
        counts["selected_nodes"] += len(selected); by_gxp[gxp]["selected_nodes"] += len(selected)
        for item in selected:
            node = nodes[int(item["taxonomy_node_id"]) - 1]
            if not str(node.get("short_render") or "").strip():
                counts["structural_only_nodes"] += 1; by_gxp[gxp]["structural_only_nodes"] += 1
            if item["custom_description"].strip():
                counts["custom_descriptions"] += 1; by_gxp[gxp]["custom_descriptions"] += 1
                # The renderer receives this selection directly; exact contribution
                # ownership is guaranteed by one selection-to-node mapping.
                if item["custom_description"].strip() not in summary:
                    counts["missing_custom_descriptions"] += 1
                    examples.append({"legacy_inspection_id": row.get("ID"), "gxp_type": gxp, "category": "missing_custom_description", "node_key": node["key"]})
        for finding in _syntax_findings(summary):
            counts[finding] += 1; by_gxp[gxp][finding] += 1
            examples.append({"legacy_inspection_id": row.get("ID"), "gxp_type": gxp, "category": finding, "summary_fragment": summary[:300]})
        counts["unkeyed_entries"] += sum(len(block["unkeyed_entries"]) for block in blocks)
        if parsed["limitation_text"] and summary.count("(*") != 1:
            counts["duplicate_limitation"] += 1
    return {"schema_version": "evaluation-scope-canonical-projection-audit/v1", "renderer_contract": "canonical_projection/v1-not-vba-fidelity", "structured_records": counts["records"], "counts": dict(sorted(counts.items())), "per_gxp": {key: dict(sorted(value.items())) for key, value in sorted(by_gxp.items())}, "representative_findings": examples[:20]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=Path("artifacts/phase3c/legacy_snapshot.json"))
    parser.add_argument("--taxonomy", type=Path, default=Path("artifacts/legacy_snapshot/evaluation_scope_taxonomy.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/legacy_audit/evaluation_scope_canonical_projection_audit.json"))
    args = parser.parse_args()
    result = audit(json.loads(args.snapshot.read_text(encoding="utf-8")), json.loads(args.taxonomy.read_text(encoding="utf-8")))
    result["snapshot_sha256"] = _sha(args.snapshot); result["taxonomy_sha256"] = _sha(args.taxonomy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
