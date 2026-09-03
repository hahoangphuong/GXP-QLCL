from __future__ import annotations

"""Exhaustive taxonomy-branch coverage for the VBA-derived evaluation-scope compiler.

Historical structured corpus currently exercises GMP and GLP only.  This audit
therefore walks every row of every available extracted taxonomy family and
compiles each row twice:

1. with a blank custom description, and
2. with a deterministic nonblank custom description.

It also compiles each complete family in source order.  This is a structural
coverage gate for taxonomy branches, especially GSP, not a historical-prose
parity oracle.
"""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.app.domain.evaluation_scope import validate_evaluation_scope_spans
from backend.app.domain.evaluation_scope_vba_renderer import compile_vba_scope_core

TAXONOMY_PATH = REPOSITORY_ROOT / "artifacts/legacy_snapshot/evaluation_scope_taxonomy.json"
SNAPSHOT_PATH = REPOSITORY_ROOT / "artifacts/phase3c/legacy_snapshot.json"
OUTPUT_PATH = REPOSITORY_ROOT / "artifacts/legacy_audit/evaluation_scope_vba_taxonomy_coverage.json"
MAX_EXAMPLES = 20


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _marker_profile(short_render: str) -> tuple[str, ...]:
    value = str(short_render or "")
    signals: list[str] = []
    if not value.strip():
        signals.append("blank")
    else:
        signals.append("nonblank")
    if value.startswith("<"):
        signals.append("continuation")
    if value.lstrip("<").startswith("&"):
        signals.append("ampersand")
    if "$$" in value:
        signals.append("dollar_template")
    if value.rstrip().endswith("("):
        signals.append("group_open")
    return tuple(signals)


def _record_example(examples: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    if len(examples) < MAX_EXAMPLES:
        examples.append(payload)


def _validate_result(result: Any) -> None:
    validate_evaluation_scope_spans(result.text, result.spans)
    if result.deferred_rules:
        raise ValueError(f"Unexpected deferred rules: {list(result.deferred_rules)}")


def _selection(row: dict[str, Any], custom_description: str) -> dict[str, Any]:
    return {
        "key": str(row["key"]),
        "source_order": int(row["source_order"]),
        "custom_description": custom_description,
    }


def audit(taxonomy: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    family_results: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []

    legacy_type_counts = Counter(str(row.get("LOẠI KT") or "") for row in snapshot["db.ktra"])

    definitions = sorted(
        taxonomy["named_ranges"].values(),
        key=lambda item: str(item["gxp_type"]),
    )
    for definition in definitions:
        gxp = str(definition["gxp_type"])
        rows = sorted(
            (dict(row) for row in definition["rows"]),
            key=lambda row: int(row["source_order"]),
        )
        family_counts: Counter[str] = Counter()
        family_counts["taxonomy_rows"] = len(rows)
        family_counts["legacy_records"] = legacy_type_counts[gxp]

        for row in rows:
            profile = _marker_profile(str(row.get("short_render") or ""))
            for marker in profile:
                family_counts[f"marker::{marker}"] += 1
                counts[f"marker::{gxp}::{marker}"] += 1

            for mode, custom in (
                ("blank_custom", ""),
                ("nonblank_custom", f"SYNTHETIC CUSTOM {gxp} {row['key']}"),
            ):
                counts["node_compile_probes"] += 1
                family_counts["node_compile_probes"] += 1
                try:
                    result = compile_vba_scope_core(
                        selections=[_selection(row, custom)],
                        taxonomy_nodes=rows,
                        block_ordinal=1,
                        gxp_type=gxp,
                    )
                    _validate_result(result)
                    family_counts[f"{mode}_pass"] += 1
                except Exception as exc:
                    family_counts[f"{mode}_failure"] += 1
                    counts["node_compile_failures"] += 1
                    _record_example(
                        failures,
                        {
                            "kind": "node_compile_failure",
                            "gxp_type": gxp,
                            "node_key": str(row["key"]),
                            "source_order": int(row["source_order"]),
                            "mode": mode,
                            "short_render": str(row.get("short_render") or ""),
                            "detail": f"{type(exc).__name__}: {exc}",
                        },
                    )

        # Whole-family source-order probes exercise interactions between
        # ancestors, continuation joins and group open/close state.
        for mode, custom_factory in (
            ("family_blank_custom", lambda row: ""),
            ("family_nonblank_custom", lambda row: f"SYNTHETIC CUSTOM {gxp} {row['key']}"),
        ):
            counts["family_sequence_probes"] += 1
            family_counts["family_sequence_probes"] += 1
            try:
                result = compile_vba_scope_core(
                    selections=[
                        _selection(row, custom_factory(row))
                        for row in rows
                    ],
                    taxonomy_nodes=rows,
                    block_ordinal=1,
                    gxp_type=gxp,
                )
                _validate_result(result)
                family_counts[f"{mode}_pass"] += 1
            except Exception as exc:
                family_counts[f"{mode}_failure"] += 1
                counts["family_sequence_failures"] += 1
                _record_example(
                    failures,
                    {
                        "kind": "family_sequence_failure",
                        "gxp_type": gxp,
                        "mode": mode,
                        "detail": f"{type(exc).__name__}: {exc}",
                    },
                )

        family_results[gxp] = {
            "source_name": str(definition.get("source_name") or ""),
            "historical_corpus_exercised": bool(legacy_type_counts[gxp]),
            "coverage_role": (
                "historical_plus_exhaustive_taxonomy"
                if legacy_type_counts[gxp]
                else "exhaustive_taxonomy_synthetic_only"
            ),
            "counts": {
                key: value
                for key, value in sorted(family_counts.items())
            },
        }

    availability = taxonomy.get("taxonomy_availability") or {}
    unavailable = {
        str(gxp): dict(info)
        for gxp, info in sorted(availability.items())
        if str(info.get("status") or "") != "available"
    }

    # GMPbb exists in legacy data but is not an extracted taxonomy family.
    # It must remain distinct and must never be silently aliased to GMP.
    non_taxonomy_legacy_types = {
        gxp: count
        for gxp, count in sorted(legacy_type_counts.items())
        if gxp and gxp not in family_results
    }

    hard_failures = {
        "node_compile_failures": counts["node_compile_failures"],
        "family_sequence_failures": counts["family_sequence_failures"],
    }

    return {
        "schema_version": "evaluation-scope-vba-taxonomy-coverage/v1",
        "contract": {
            "semantic_owner": "legacy_vba_with_explicit_product_corrections",
            "purpose": "exhaustive_structural_taxonomy_coverage_not_historical_parity",
            "available_families_must_compile_every_row_blank_and_nonblank_custom": True,
            "available_families_must_compile_full_source_order_sequence": True,
            "gdp_policy": "fail_closed_when_taxonomy_unavailable",
            "gmpbb_policy": "distinct_legacy_prose_family_never_alias_to_gmp",
            "known_product_corrections": [
                "expand_first_gmp_detail_key_immediately_after_open_parenthesis"
            ],
        },
        "families": family_results,
        "taxonomy_unavailable": unavailable,
        "non_taxonomy_legacy_types": non_taxonomy_legacy_types,
        "counts": dict(sorted(counts.items())),
        "hard_failures": hard_failures,
        "bounded_failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--taxonomy", type=Path, default=TAXONOMY_PATH)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    taxonomy = json.loads(args.taxonomy.read_text(encoding="utf-8"))
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    result = audit(taxonomy, snapshot)
    result["taxonomy_sha256"] = _sha(args.taxonomy)
    result["snapshot_sha256"] = _sha(args.snapshot)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if any(result["hard_failures"].values()):
        raise SystemExit(
            "VBA taxonomy coverage audit failed; inspect hard_failures and bounded_failures."
        )


if __name__ == "__main__":
    main()
