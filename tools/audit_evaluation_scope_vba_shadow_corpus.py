from __future__ import annotations

"""Corpus diagnostic for the VBA-derived evaluation-scope shadow renderer.

This audit deliberately keeps three projections separate:
1. historical ``db.ktra`` rendered prose (migration/history evidence),
2. the current Python canonical renderer (compatibility/reference), and
3. the VBA-derived shadow renderer (forward semantic target).

Equality with (1) or (2) is diagnostic only.  Hard failures are limited to
conditions that make the shadow projection internally invalid: compile errors,
unresolved deferred rules, or broken provenance/span coverage.
"""

import argparse
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.app.domain.evaluation_scope import (
    parse_legacy_evaluation_scope,
    render_evaluation_scope_summary,
    validate_evaluation_scope_spans,
)
from backend.app.domain.evaluation_scope_vba_renderer import compile_vba_readable_scope

SNAPSHOT_PATH = REPOSITORY_ROOT / "artifacts/phase3c/legacy_snapshot.json"
TAXONOMY_PATH = REPOSITORY_ROOT / "artifacts/legacy_snapshot/evaluation_scope_taxonomy.json"
OUTPUT_PATH = REPOSITORY_ROOT / "artifacts/legacy_audit/evaluation_scope_vba_shadow_corpus.json"
MAX_EXAMPLES_PER_CATEGORY = 12


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _record_id(row: dict[str, Any]) -> str:
    return str(row.get("ID ĐỢT KTRA") or row.get("ID") or row.get("Mã hồ sơ") or "(blank)")


def _normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _comparison_normalize(value: str) -> str:
    """Conservative comparison normalization; no semantic punctuation rewrite."""
    text = _normalize_newlines(value).strip()
    return "\n".join(line.rstrip() for line in text.split("\n"))


def _compact_compare(value: str) -> str:
    """Whitespace-insensitive diagnostic only; punctuation and text stay intact."""
    return re.sub(r"\s+", " ", _comparison_normalize(value)).strip()


def _similarity(left: str, right: str) -> float:
    return round(SequenceMatcher(None, _compact_compare(left), _compact_compare(right)).ratio(), 6)


def _first_difference(left: str, right: str, context: int = 90) -> dict[str, Any] | None:
    a = _comparison_normalize(left)
    b = _comparison_normalize(right)
    if a == b:
        return None
    limit = min(len(a), len(b))
    index = 0
    while index < limit and a[index] == b[index]:
        index += 1
    start = max(0, index - context)
    return {
        "offset": index,
        "left_fragment": a[start : index + context],
        "right_fragment": b[start : index + context],
    }


def _add_example(store: defaultdict[str, list[dict[str, Any]]], category: str, payload: dict[str, Any]) -> None:
    if len(store[category]) < MAX_EXAMPLES_PER_CATEGORY:
        store[category].append(payload)


def _taxonomy_by_gxp(taxonomy: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        str(definition["gxp_type"]): [dict(row) for row in definition["rows"]]
        for definition in taxonomy["named_ranges"].values()
    }


def _build_inputs(parsed: dict[str, Any], taxonomy_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    # Give the compatibility renderer stable IDs while keeping the VBA shadow on
    # source keys.  Both projections consume the same parsed structured payload.
    nodes = [{**node, "id": str(index)} for index, node in enumerate(taxonomy_rows, start=1)]
    node_by_key = {str(node["key"]): node for node in nodes}
    vba_blocks: list[dict[str, Any]] = []
    canonical_blocks: list[dict[str, Any]] = []

    for ordinal, scope in enumerate(parsed["scopes"], start=1):
        vba_selections: list[dict[str, Any]] = []
        canonical_selections: list[dict[str, Any]] = []
        for item in scope["selected_nodes"]:
            key = str(item["key"])
            if item.get("key_kind") == "RUNTIME_SYNTHETIC_NODE":
                # Runtime + keys are UI children of the parent custom string,
                # not independent taxonomy rows.  STRUCTURED_VALID corpus should
                # not require them as standalone compile owners.
                continue
            node = node_by_key.get(key)
            if node is None:
                raise ValueError(f"Structured-valid selection {key!r} is absent from taxonomy.")
            vba_selections.append(
                {
                    "key": key,
                    "source_order": int(item["source_order"]),
                    "custom_description": str(item.get("description") or ""),
                }
            )
            canonical_selections.append(
                {
                    "taxonomy_node_id": node["id"],
                    "source_order": int(item["source_order"]),
                    "custom_description": str(item.get("description") or ""),
                }
            )

        common = {
            "id": str(ordinal),
            "ordinal": ordinal,
            "name": scope.get("name") or "",
            "note": scope.get("note") or "",
        }
        vba_blocks.append({**common, "selections": vba_selections, "raw_block_value": scope.get("raw_value")})
        canonical_blocks.append(
            {
                **common,
                "selections": canonical_selections,
                "unkeyed_entries": [dict(entry) for entry in scope.get("unkeyed_entries") or ()],
            }
        )
    return vba_blocks, canonical_blocks




def _record_semantic_signals(
    *,
    parsed: dict[str, Any],
    taxonomy_rows: list[dict[str, Any]],
    vba_blocks: list[dict[str, Any]],
    canonical_blocks: list[dict[str, Any]],
    vba_result: Any,
) -> tuple[str, ...]:
    """Return deterministic input/output features that can explain projection deltas.

    These are diagnostic *signals*, not claims that historical prose is correct.
    Multiple signals may apply to one record.  The purpose is to partition corpus
    differences by concrete source-owned semantics before any production cutover.
    """
    by_key = {str(row.get("key") or ""): row for row in taxonomy_rows}
    signals: set[str] = set()

    if len(vba_blocks) > 1:
        signals.add("multi_block")
    if any(str(block.get("name") or "") for block in vba_blocks):
        signals.add("block_name")
    if any(str(block.get("note") or "") for block in vba_blocks):
        signals.add("block_note")
    if str(parsed.get("limitation_text") or "").strip():
        signals.add("limitation")
    if any(block.get("unkeyed_entries") for block in canonical_blocks):
        signals.add("unkeyed_entries")

    for block in vba_blocks:
        for selected in block.get("selections") or ():
            key = str(selected.get("key") or "")
            node = by_key.get(key) or {}
            short_render = str(node.get("short_render") or "")
            custom = str(selected.get("custom_description") or "")
            marker_body = short_render[1:] if short_render.startswith("<") else short_render
            if custom:
                signals.add("custom_description")
            if "$$" in short_render:
                signals.add("dollar_template")
            if marker_body.startswith("&"):
                signals.add("ampersand_marker")
            if short_render.startswith("<"):
                signals.add("continuation_marker")
            cleaned = short_render.replace(" ($$)", "", 1).replace("($$)", "", 1)
            cleaned = cleaned.replace(" $$", "", 1).replace("$$", "", 1)
            if cleaned.strip().endswith("("):
                signals.add("group_parenthesis")
            source_text = " ".join((short_render, custom, str(node.get("description") or ""))).lower()
            if "beta" in source_text or "lactam" in source_text:
                signals.add("getdata_beta_lactam_normalization")

    roles = [str(item.get("role") or "") for item in vba_result.contributions]
    if "getdata_text_normalization" in roles:
        signals.add("getdata_normalization_applied")
    if "gmp_packaging_detail_expansion" in roles:
        signals.add("gmp_packaging_detail_expansion")
    if "gmp_batch_release_detail_expansion" in roles:
        signals.add("gmp_batch_release_detail_expansion")
    if any(
        item.get("role") == "gmp_batch_release_detail_expansion"
        and item.get("matched_after_open_parenthesis") is True
        for item in vba_result.contributions
    ):
        signals.add("product_correction_first_key_after_parenthesis")

    # The VBA core intentionally emits CR-separated lines and often no space
    # after a colon before a child contribution.  These are renderer-format
    # semantics, not missing source data.
    signals.add("vba_line_and_separator_formatting")
    return tuple(sorted(signals))

def audit(snapshot: dict[str, Any], taxonomy: dict[str, Any]) -> dict[str, Any]:
    rows_by_gxp = _taxonomy_by_gxp(taxonomy)
    counts: Counter[str] = Counter()
    per_gxp: defaultdict[str, Counter[str]] = defaultdict(Counter)
    examples: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    similarity_buckets: Counter[str] = Counter()
    mismatch_signal_counts: Counter[str] = Counter()
    mismatch_profiles: Counter[str] = Counter()

    for row in snapshot["db.ktra"]:
        gxp = str(row.get("LOẠI KT") or "")
        parsed = parse_legacy_evaluation_scope(
            row.get("PHẠM VI KIỂM TRA"),
            gxp_type=gxp,
            taxonomy=taxonomy,
        )
        if parsed["classification"] != "STRUCTURED_VALID":
            continue

        counts["structured_records"] += 1
        per_gxp[gxp]["structured_records"] += 1
        taxonomy_rows = rows_by_gxp.get(gxp)
        if taxonomy_rows is None:
            counts["taxonomy_unavailable"] += 1
            per_gxp[gxp]["taxonomy_unavailable"] += 1
            _add_example(examples, "taxonomy_unavailable", {"legacy_inspection_id": _record_id(row), "gxp_type": gxp})
            continue

        try:
            vba_blocks, canonical_blocks = _build_inputs(parsed, taxonomy_rows)
            vba = compile_vba_readable_scope(
                blocks=vba_blocks,
                taxonomy_nodes=taxonomy_rows,
                limitation_text=parsed.get("limitation_text"),
                gxp_type=gxp,
            )
            canonical = render_evaluation_scope_summary(
                blocks=canonical_blocks,
                taxonomy_nodes=[{**node, "id": str(index)} for index, node in enumerate(taxonomy_rows, start=1)],
                limitation_text=parsed.get("limitation_text"),
                include_provenance=True,
            )
        except Exception as exc:  # audit must retain bounded evidence before failing
            counts["compile_exceptions"] += 1
            per_gxp[gxp]["compile_exceptions"] += 1
            _add_example(
                examples,
                "compile_exceptions",
                {"legacy_inspection_id": _record_id(row), "gxp_type": gxp, "detail": f"{type(exc).__name__}: {exc}"},
            )
            continue

        counts["blocks"] += len(vba.blocks)
        per_gxp[gxp]["blocks"] += len(vba.blocks)
        counts["selected_nodes"] += sum(len(block["selections"]) for block in vba_blocks)
        counts["unkeyed_entries"] += sum(len(block["unkeyed_entries"]) for block in canonical_blocks)
        counts["gmp_packaging_expansions"] += sum(1 for item in vba.contributions if item.get("role") == "gmp_packaging_detail_expansion")
        counts["gmp_batch_release_expansions"] += sum(1 for item in vba.contributions if item.get("role") == "gmp_batch_release_detail_expansion")
        normalization_items = [item for item in vba.contributions if item.get("role") == "getdata_text_normalization"]
        if normalization_items:
            counts["records_with_getdata_text_normalization"] += 1
            counts["getdata_text_normalization_replacements"] += sum(int(item.get("replacement_count") or 0) for item in normalization_items)

        if vba.deferred_rules:
            counts["deferred_rule_records"] += 1
            per_gxp[gxp]["deferred_rule_records"] += 1
            _add_example(
                examples,
                "deferred_rules",
                {"legacy_inspection_id": _record_id(row), "gxp_type": gxp, "rules": list(vba.deferred_rules)},
            )

        try:
            validate_evaluation_scope_spans(vba.text, vba.spans)
        except ValueError as exc:
            counts["span_integrity_failures"] += 1
            per_gxp[gxp]["span_integrity_failures"] += 1
            _add_example(
                examples,
                "span_integrity_failures",
                {"legacy_inspection_id": _record_id(row), "gxp_type": gxp, "detail": str(exc)},
            )

        historical = str(parsed.get("rendered_prose") or "")
        python_text = str(canonical.text)
        vba_text = str(vba.text)
        semantic_signals = _record_semantic_signals(
            parsed=parsed,
            taxonomy_rows=taxonomy_rows,
            vba_blocks=vba_blocks,
            canonical_blocks=canonical_blocks,
            vba_result=vba,
        )

        pairs = (
            ("historical_vs_vba", historical, vba_text),
            ("python_vs_vba", python_text, vba_text),
            ("historical_vs_python", historical, python_text),
        )
        for label, left, right in pairs:
            exact = _comparison_normalize(left) == _comparison_normalize(right)
            compact = _compact_compare(left) == _compact_compare(right)
            counts[f"{label}_exact_equal"] += int(exact)
            counts[f"{label}_exact_mismatch"] += int(not exact)
            counts[f"{label}_whitespace_only_mismatch"] += int(not exact and compact)
            if label in {"historical_vs_vba", "python_vs_vba"} and not exact:
                for signal in semantic_signals:
                    mismatch_signal_counts[f"{label}::{signal}"] += 1
                profile = "+".join(semantic_signals) if semantic_signals else "NO_KNOWN_SIGNAL"
                mismatch_profiles[f"{label}::{profile}"] += 1
                score = _similarity(left, right)
                bucket = "0.99+" if score >= 0.99 else "0.95-0.99" if score >= 0.95 else "0.80-0.95" if score >= 0.80 else "<0.80"
                similarity_buckets[f"{label}::{bucket}"] += 1
                _add_example(
                    examples,
                    label,
                    {
                        "legacy_inspection_id": _record_id(row),
                        "gxp_type": gxp,
                        "similarity": score,
                        "semantic_signals": list(semantic_signals),
                        "first_difference": _first_difference(left, right),
                        "historical_fragment": historical[:500],
                        "python_fragment": python_text[:500],
                        "vba_fragment": vba_text[:500],
                    },
                )

        # Historical prose can legitimately contain stale text.  Count whether
        # the user's intentional first-key correction is exercised, but do not
        # turn historical disagreement into a failure gate.
        first_key_corrections = [
            item
            for item in vba.contributions
            if item.get("role") == "gmp_batch_release_detail_expansion"
            and item.get("matched_after_open_parenthesis") is True
        ]
        if first_key_corrections:
            counts["records_using_first_key_product_correction"] += 1
            counts["first_key_product_correction_expansions"] += len(first_key_corrections)

    # Keep zero-valued contract counters explicit so artifact diffs remain easy
    # to review even when a branch is not exercised by the current corpus.
    for key in (
        "records_using_first_key_product_correction",
        "first_key_product_correction_expansions",
        "records_with_getdata_text_normalization",
        "getdata_text_normalization_replacements",
    ):
        counts[key] += 0

    hard_failures = {
        "taxonomy_unavailable": counts["taxonomy_unavailable"],
        "compile_exceptions": counts["compile_exceptions"],
        "deferred_rule_records": counts["deferred_rule_records"],
        "span_integrity_failures": counts["span_integrity_failures"],
    }
    return {
        "schema_version": "evaluation-scope-vba-shadow-corpus/v1",
        "contract": {
            "semantic_owner": "legacy_vba_with_explicit_product_corrections",
            "historical_prose_role": "history_diagnostic_not_oracle",
            "current_python_renderer_role": "compatibility_reference_not_oracle",
            "hard_failure_fields": list(hard_failures),
            "known_product_corrections": ["expand_first_gmp_detail_key_immediately_after_open_parenthesis"],
            "port_coverage": {
                "core_compile_node_and_ancestors": "ported",
                "group_and_continuation": "ported",
                "block_name_note_limitation": "ported",
                "multi_block_join": "ported",
                "gmp_packaging_detail_expansion": "ported",
                "gmp_batch_release_detail_expansion": "ported_with_explicit_product_correction",
                "getdata_beta_lactam_normalization": "ported_with_forward_provenance",
                "unkeyed_entries": "preserved_but_not_rendered_by_vba_core",
                "historical_prose": "diagnostic_only",
            },
        },
        "counts": dict(sorted(counts.items())),
        "hard_failures": hard_failures,
        "per_gxp": {key: dict(sorted(value.items())) for key, value in sorted(per_gxp.items())},
        "similarity_buckets": dict(sorted(similarity_buckets.items())),
        "mismatch_signal_counts": dict(sorted(mismatch_signal_counts.items())),
        "top_mismatch_profiles": [
            {"comparison_and_profile": key, "records": value}
            for key, value in mismatch_profiles.most_common(30)
        ],
        "bounded_examples": {key: value for key, value in sorted(examples.items())},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT_PATH)
    parser.add_argument("--taxonomy", type=Path, default=TAXONOMY_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    taxonomy = json.loads(args.taxonomy.read_text(encoding="utf-8"))
    result = audit(snapshot, taxonomy)
    result["snapshot_sha256"] = _sha(args.snapshot)
    result["taxonomy_sha256"] = _sha(args.taxonomy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if any(result["hard_failures"].values()):
        raise SystemExit("VBA shadow corpus audit failed; inspect hard_failures and bounded_examples.")


if __name__ == "__main__":
    main()
