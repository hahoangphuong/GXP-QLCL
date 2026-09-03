from __future__ import annotations

"""Formal C.5d.2 cutover-readiness gate for the VBA-derived scope summary renderer.

The gate does not implement rendering semantics.  It re-runs the two existing
VBA-derived audits, probes the same renderer intended for production, and
verifies the persistence/read-model contracts that bound the renderer-owner
switch and recognizes the verified post-cutover state.

Historical ``db.ktra`` prose and the old Python renderer remain diagnostic only.
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

from backend.app.domain.evaluation_scope import parse_legacy_evaluation_scope, validate_evaluation_scope_spans
from backend.app.domain.evaluation_scope_vba_renderer import (
    compile_vba_readable_scope,
    compile_vba_scope_core,
)
from tools.audit_evaluation_scope_vba_shadow_corpus import audit as audit_shadow_corpus
from tools.audit_evaluation_scope_vba_taxonomy_coverage import audit as audit_taxonomy_coverage

SNAPSHOT_PATH = REPOSITORY_ROOT / "artifacts/phase3c/legacy_snapshot.json"
TAXONOMY_PATH = REPOSITORY_ROOT / "artifacts/legacy_snapshot/evaluation_scope_taxonomy.json"
OUTPUT_PATH = REPOSITORY_ROOT / "artifacts/legacy_audit/evaluation_scope_vba_cutover_readiness.json"

SPEC_PATH = REPOSITORY_ROOT / "docs/EVALUATION_SCOPE_VBA_RENDERER_SEMANTICS.md"
RENDERER_PATH = REPOSITORY_ROOT / "backend/app/domain/evaluation_scope_vba_renderer.py"
READ_SERVICE_PATH = REPOSITORY_ROOT / "backend/app/services/catalog.py"
WORKFLOW_SERVICE_PATH = REPOSITORY_ROOT / "backend/app/services/workflow.py"
WORKFLOW_ROUTER_PATH = REPOSITORY_ROOT / "backend/app/api/routers/workflow.py"
CATALOG_ROUTER_PATH = REPOSITORY_ROOT / "backend/app/api/routers/catalog.py"
MODEL_PATH = REPOSITORY_ROOT / "backend/app/db/models/phase1.py"
UI_PATH = REPOSITORY_ROOT / "frontend/src/features/search/EvaluationScopeWorkspace.tsx"
FRONTEND_API_PATH = REPOSITORY_ROOT / "frontend/src/lib/api.ts"

EXPECTED_CORPUS = {
    "structured_records": 677,
    "blocks": 717,
    "selected_nodes": 9762,
    "unkeyed_entries": 903,
}
EXPECTED_TAXONOMY_ROWS = {"GMP": 112, "GLP": 237, "GSP": 52}


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _taxonomy_rows(taxonomy: dict[str, Any], gxp_type: str) -> list[dict[str, Any]]:
    for payload in taxonomy.get("named_ranges", {}).values():
        if str(payload.get("gxp_type") or "") == gxp_type:
            return [dict(row) for row in payload.get("rows", ())]
    return []


def _record_id(row: dict[str, Any]) -> str:
    for key in ("ID", "id", "MÃ KT", "SỐ BIÊN BẢN"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _collect_unkeyed_evidence(snapshot: dict[str, Any], taxonomy: dict[str, Any]) -> dict[str, Any]:
    """Account for legacy unkeyed rows without reinterpreting or resurrecting them.

    Project owner policy is explicit: these are legacy items deliberately marked
    with a leading ``-`` so they are skipped.  They are not unresolved taxonomy
    content and must never be re-keyed or injected into readable summaries.

    The corpus count remains part of the readiness evidence only to prove that
    the cutover sees the complete imported population and applies one uniform
    skip policy to it.
    """

    counts: Counter[str] = Counter()
    per_gxp: Counter[str] = Counter()
    examples: list[dict[str, str]] = []

    for row in snapshot.get("db.ktra", ()):
        gxp_type = str(row.get("LOẠI KT") or "")
        parsed = parse_legacy_evaluation_scope(
            row.get("PHẠM VI KIỂM TRA"),
            gxp_type=gxp_type,
            taxonomy=taxonomy,
        )
        if parsed.get("classification") != "STRUCTURED_VALID":
            continue
        for scope in parsed.get("scopes", ()):
            for entry in scope.get("unkeyed_entries", ()):
                text = str(entry.get("text") or "")
                counts["total"] += 1
                per_gxp[gxp_type] += 1
                if len(examples) < 12:
                    examples.append(
                        {
                            "legacy_inspection_id": _record_id(row),
                            "gxp_type": gxp_type,
                            "text": text[:300],
                        }
                    )

    return {
        "classification": "LEGACY_SKIPPED_BY_DESIGN",
        "policy_authority": "project_owner_explicit_confirmation",
        "legacy_marker": "leading_hyphen",
        "renderer_policy": "SKIP_ALWAYS",
        "rekey_policy": "NEVER_REKEY_OR_RECOVER",
        "summary_policy": "NEVER_RENDER",
        "cutover_blocker": False,
        "persistence_policy": "MAY_RETAIN_AS_LEGACY_EVIDENCE_BUT_NOT_SEMANTIC_INPUT",
        "reason": (
            "All unkeyed entries are legacy items deliberately marked for skip by the project owner. "
            "Their presence is corpus accounting, not unresolved rendering semantics."
        ),
        "counts": dict(sorted(counts.items())),
        "per_gxp": dict(sorted(per_gxp.items())),
        "bounded_examples": examples,
    }


def _source_contains(path: Path, *needles: str) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    return all(needle in text for needle in needles)


def _discover_production_symbol_calls(symbol: str) -> list[str]:
    calls: list[str] = []
    backend_root = REPOSITORY_ROOT / "backend/app"
    for path in sorted(backend_root.rglob("*.py")):
        if path in {RENDERER_PATH, REPOSITORY_ROOT / "backend/app/domain/evaluation_scope.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        if symbol not in text:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if symbol in line:
                calls.append(f"{path.relative_to(REPOSITORY_ROOT).as_posix()}:{line_number}")
    return calls


def _probe_explicit_product_correction(taxonomy: dict[str, Any]) -> dict[str, Any]:
    rows = _taxonomy_rows(taxonomy, "GMP")
    result = compile_vba_scope_core(
        taxonomy_nodes=rows,
        selections=[{"key": "1.3", "source_order": 1, "custom_description": "1.1; 1.2"}],
        gxp_type="GMP",
    )
    expansions = [
        item
        for item in result.contributions
        if item.get("role") == "gmp_batch_release_detail_expansion"
    ]
    validate_evaluation_scope_spans(result.text, result.spans)
    return {
        "pass": (
            [item.get("node_key") for item in expansions] == ["1.1", "1.2"]
            and [item.get("matched_after_open_parenthesis") for item in expansions] == [True, False]
        ),
        "output": result.text,
        "expanded_keys": [item.get("node_key") for item in expansions],
        "matched_after_open_parenthesis": [
            item.get("matched_after_open_parenthesis") for item in expansions
        ],
    }


def _probe_block_envelope(taxonomy: dict[str, Any]) -> dict[str, Any]:
    rows = _taxonomy_rows(taxonomy, "GLP")
    first = next((row for row in rows if str(row.get("short_render") or "").strip()), None)
    if first is None:
        return {"pass": False, "reason": "GLP taxonomy has no renderable row."}
    result = compile_vba_readable_scope(
        blocks=[
            {
                "ordinal": 1,
                "name": "Khu A",
                "note": "Ghi chú A",
                "selections": [
                    {
                        "key": first["key"],
                        "source_order": 1,
                        "custom_description": "beta lactam",
                    }
                ],
            },
            {
                "ordinal": 2,
                "name": "Khu B",
                "note": "Ghi chú B",
                "selections": [
                    {
                        "key": first["key"],
                        "source_order": 1,
                        "custom_description": "thử nghiệm",
                    }
                ],
            },
        ],
        taxonomy_nodes=rows,
        limitation_text="Giới hạn X",
        gxp_type="GLP",
    )
    validate_evaluation_scope_spans(result.text, result.spans)
    roles = Counter(str(item.get("role") or "") for item in result.contributions)
    return {
        "pass": (
            len(result.blocks) == 2
            and roles["block_name"] == 2
            and roles["block_note"] == 2
            and roles["limitation"] == 1
            and roles["getdata_text_normalization"] == 1
            and not result.deferred_rules
        ),
        "block_count": len(result.blocks),
        "contribution_roles": dict(sorted(roles.items())),
        "deferred_rules": list(result.deferred_rules),
        "output": result.text,
    }


def audit(
    snapshot: dict[str, Any],
    taxonomy: dict[str, Any],
) -> dict[str, Any]:
    corpus = audit_shadow_corpus(snapshot, taxonomy)
    taxonomy_coverage = audit_taxonomy_coverage(taxonomy, snapshot)
    unkeyed = _collect_unkeyed_evidence(snapshot, taxonomy)
    correction = _probe_explicit_product_correction(taxonomy)
    envelope = _probe_block_envelope(taxonomy)

    blockers: list[dict[str, Any]] = []
    checks: dict[str, dict[str, Any]] = {}

    def check(code: str, passed: bool, evidence: Any, blocker_message: str) -> None:
        checks[code] = {"status": "PASS" if passed else "BLOCKED", "evidence": evidence}
        if not passed:
            blockers.append(
                {
                    "code": code,
                    "message": blocker_message,
                    "evidence": evidence,
                }
            )

    spec_needles = (
        "Compile_PVCN",
        "unkeyed",
        "PV_Incl_Pos",
        "beta",
        "Lactam",
        "GMPbb",
        "GDP",
        "PROSE_ONLY",
        "forward",
    )
    check(
        "VBA_SPEC_CURRENT",
        SPEC_PATH.is_file() and _source_contains(SPEC_PATH, *spec_needles),
        {
            "path": SPEC_PATH.relative_to(REPOSITORY_ROOT).as_posix(),
            "sha256": _sha(SPEC_PATH) if SPEC_PATH.is_file() else None,
            "required_markers": list(spec_needles),
        },
        "The VBA semantics specification is missing or no longer states the required cutover contracts.",
    )

    corpus_counts = corpus.get("counts", {})
    corpus_failures = corpus.get("hard_failures", {})
    check(
        "CORPUS_COMPILES",
        all(corpus_counts.get(key) == value for key, value in EXPECTED_CORPUS.items())
        and corpus_failures.get("compile_exceptions") == 0,
        {
            "expected": EXPECTED_CORPUS,
            "actual": {key: corpus_counts.get(key, 0) for key in EXPECTED_CORPUS},
            "compile_exceptions": corpus_failures.get("compile_exceptions", 0),
        },
        "The structured legacy corpus no longer matches the accepted compile baseline.",
    )
    check(
        "SPAN_PROVENANCE_INTEGRITY",
        corpus_failures.get("span_integrity_failures") == 0,
        {"span_integrity_failures": corpus_failures.get("span_integrity_failures", 0)},
        "Forward span/provenance integrity failed on the corpus.",
    )
    check(
        "DEFERRED_SEMANTIC_RULES",
        corpus_failures.get("deferred_rule_records") == 0,
        {"deferred_rule_records": corpus_failures.get("deferred_rule_records", 0)},
        "The renderer still has deferred semantic rules.",
    )

    family_evidence: dict[str, Any] = {}
    family_pass = True
    for gxp_type, expected_rows in EXPECTED_TAXONOMY_ROWS.items():
        family = taxonomy_coverage.get("families", {}).get(gxp_type, {})
        counts = family.get("counts", {})
        family_evidence[gxp_type] = {
            "expected_taxonomy_rows": expected_rows,
            "taxonomy_rows": counts.get("taxonomy_rows"),
            "blank_custom_pass": counts.get("blank_custom_pass"),
            "nonblank_custom_pass": counts.get("nonblank_custom_pass"),
            "family_blank_custom_pass": counts.get("family_blank_custom_pass"),
            "family_nonblank_custom_pass": counts.get("family_nonblank_custom_pass"),
            "family_sequence_probes": counts.get("family_sequence_probes"),
        }
        family_pass = family_pass and (
            counts.get("taxonomy_rows") == expected_rows
            and counts.get("blank_custom_pass") == expected_rows
            and counts.get("nonblank_custom_pass") == expected_rows
            and counts.get("family_blank_custom_pass") == 1
            and counts.get("family_nonblank_custom_pass") == 1
            and counts.get("family_sequence_probes") == 2
        )
    family_pass = family_pass and all(
        value == 0 for value in taxonomy_coverage.get("hard_failures", {}).values()
    )
    check(
        "EXHAUSTIVE_TAXONOMY_COVERAGE",
        family_pass,
        {
            "families": family_evidence,
            "hard_failures": taxonomy_coverage.get("hard_failures", {}),
        },
        "Exhaustive taxonomy-node or whole-family compilation is incomplete.",
    )

    check(
        "GDP_FAIL_CLOSED",
        taxonomy_coverage.get("taxonomy_unavailable", {}).get("GDP", {}).get("status") == "unavailable"
        and taxonomy_coverage.get("contract", {}).get("gdp_policy")
        == "fail_closed_when_taxonomy_unavailable",
        {
            "GDP": taxonomy_coverage.get("taxonomy_unavailable", {}).get("GDP"),
            "policy": taxonomy_coverage.get("contract", {}).get("gdp_policy"),
        },
        "GDP is not fail-closed while its legacy taxonomy remains unavailable.",
    )
    check(
        "GMPBB_DISTINCT_PROSE_ONLY",
        taxonomy_coverage.get("contract", {}).get("gmpbb_policy")
        == "distinct_legacy_prose_family_never_alias_to_gmp"
        and int(taxonomy_coverage.get("non_taxonomy_legacy_types", {}).get("GMPbb", 0)) > 0,
        {
            "GMPbb_records": taxonomy_coverage.get("non_taxonomy_legacy_types", {}).get("GMPbb", 0),
            "policy": taxonomy_coverage.get("contract", {}).get("gmpbb_policy"),
        },
        "GMPbb is no longer explicitly separated from the GMP taxonomy.",
    )
    check(
        "FIRST_KEY_PRODUCT_CORRECTION",
        bool(correction.get("pass")),
        correction,
        "The explicit first-key-after-'(' product correction is not working.",
    )
    check(
        "GETDATA_NORMALIZATION",
        corpus_counts.get("records_with_getdata_text_normalization") == 14
        and corpus_counts.get("getdata_text_normalization_replacements") == 18
        and bool(envelope.get("pass")),
        {
            "records": corpus_counts.get("records_with_getdata_text_normalization", 0),
            "replacements": corpus_counts.get("getdata_text_normalization_replacements", 0),
            "synthetic_envelope_probe": envelope,
        },
        "GetData beta/Lactam normalization or block-envelope coverage regressed.",
    )
    check(
        "MULTI_BLOCK_NAME_NOTE_LIMITATION",
        bool(envelope.get("pass")),
        envelope,
        "Multi-block/name/note/limitation semantics are not covered by the active renderer.",
    )

    unkeyed_pass = (
        unkeyed.get("classification") == "LEGACY_SKIPPED_BY_DESIGN"
        and unkeyed.get("renderer_policy") == "SKIP_ALWAYS"
        and unkeyed.get("rekey_policy") == "NEVER_REKEY_OR_RECOVER"
        and unkeyed.get("summary_policy") == "NEVER_RENDER"
        and unkeyed.get("cutover_blocker") is False
        and unkeyed.get("counts", {}).get("total") == EXPECTED_CORPUS["unkeyed_entries"]
    )
    check(
        "UNKEYED_LEGACY_SKIP_POLICY",
        unkeyed_pass,
        unkeyed,
        "Legacy unkeyed entries are not covered by the explicit skip-by-design policy.",
    )

    old_renderer_calls = _discover_production_symbol_calls("render_evaluation_scope_summary")
    vba_renderer_calls = _discover_production_symbol_calls("compile_vba_readable_scope")
    read_service_text = READ_SERVICE_PATH.read_text(encoding="utf-8")
    workflow_text = WORKFLOW_SERVICE_PATH.read_text(encoding="utf-8")
    model_text = MODEL_PATH.read_text(encoding="utf-8")
    workflow_router_text = WORKFLOW_ROUTER_PATH.read_text(encoding="utf-8")
    catalog_router_text = CATALOG_ROUTER_PATH.read_text(encoding="utf-8")
    ui_text = UI_PATH.read_text(encoding="utf-8")
    frontend_api_text = FRONTEND_API_PATH.read_text(encoding="utf-8")

    check(
        "NO_REVERSE_PROVENANCE_REQUIRED",
        corpus_failures.get("span_integrity_failures") == 0
        and corpus_failures.get("deferred_rule_records") == 0
        and "include_provenance=True" not in RENDERER_PATH.read_text(encoding="utf-8"),
        {
            "span_integrity_failures": corpus_failures.get("span_integrity_failures", 0),
            "deferred_rule_records": corpus_failures.get("deferred_rule_records", 0),
            "renderer_contract": "forward_compile_with_owned_spans_and_contributions",
        },
        "Cutover still depends on reverse ownership/provenance recovery.",
    )

    expected_call_prefix = "backend/app/services/catalog.py:"
    pre_cutover = (
        len(old_renderer_calls) == 2
        and all(call.startswith(expected_call_prefix) for call in old_renderer_calls)
        and not vba_renderer_calls
    )
    cutover_active = (
        not old_renderer_calls
        and len(vba_renderer_calls) == 2
        and all(call.startswith(expected_call_prefix) for call in vba_renderer_calls)
        and 'node_key_by_id[str(selection["taxonomy_node_id"])]' in read_service_text
        and "gxp_type=case.gxp_type" in read_service_text
    )
    renderer_state = (
        "PRE_CUTOVER_READY"
        if pre_cutover
        else "CUTOVER_ACTIVE_VERIFIED"
        if cutover_active
        else "UNKNOWN_OR_MIXED"
    )
    check(
        "PRODUCTION_BLAST_RADIUS_IDENTIFIED",
        (pre_cutover or cutover_active)
        and "summary_text" in ui_text
        and "/cases/${caseId}/workspace" in frontend_api_text
        and '"/cases/{case_id}/workspace"' in catalog_router_text
        and '"/cases/{case_id}/evaluation-scope"' in workflow_router_text,
        {
            "renderer_state": renderer_state,
            "old_renderer_symbol_occurrences_outside_domain": old_renderer_calls,
            "vba_renderer_symbol_occurrences_outside_domain": vba_renderer_calls,
            "production_summary_owner": "backend/app/services/catalog.py::CatalogReadService._serialize_evaluation_scope",
            "read_api": "GET /cases/{case_id}/workspace",
            "mutation_api": "PUT /cases/{case_id}/evaluation-scope",
            "ui_consumer": "frontend/src/features/search/EvaluationScopeWorkspace.tsx::scope.summary_text",
            "cutover_contract": "catalog read-time structured projection only; API/UI payload contract unchanged",
        },
        "The renderer ownership state is neither the audited pre-cutover state nor the verified controlled-cutover state.",
    )

    persistence_checks = {
        "historical_rendered_prose_column_retained": "rendered_prose:" in model_text,
        "raw_legacy_value_column_retained": "raw_legacy_value:" in model_text,
        "unkeyed_model_retained": "class CaseEvaluationScopeUnkeyedEntry" in model_text,
        "prose_only_read_path": 'prose_only = scope.source_classification == "PROSE_ONLY"' in read_service_text,
        "prose_only_historical_summary": 'scope.rendered_prose' in read_service_text
        and '"historical_prose" if prose_only' in read_service_text,
        "unkeyed_read_only": "has_unkeyed_entries" in read_service_text,
        "unkeyed_mutation_fail_closed": (
            "CaseEvaluationScopeUnkeyedEntry" in workflow_text
            and "remains read-only until their VBA mutation contract is proven" in workflow_text
        ),
        "structured_save_increments_version": "scope.row_version += 1" in workflow_text,
        "structured_save_replaces_canonical_children": (
            "delete(CaseEvaluationScopeSelection)" in workflow_text
            and "CaseEvaluationScopeSelection(" in workflow_text
        ),
        "reassessment_exact_scope_fields": all(
            needle in workflow_text
            for needle in (
                "taxonomy_version_id=source_scope.taxonomy_version_id",
                "source_classification=source_scope.source_classification",
                "raw_legacy_value=source_scope.raw_legacy_value",
                "rendered_prose=source_scope.rendered_prose",
                "limitation_text=source_scope.limitation_text",
            )
        ),
        "reassessment_copies_selections": "node_key_snapshot=source_selection.node_key_snapshot" in workflow_text,
        "reassessment_copies_unkeyed": "text=source_entry.text" in workflow_text,
        "summary_is_not_persisted_column": "summary_text:" not in model_text,
    }
    check(
        "PERSISTED_HISTORY_IMMUTABLE",
        all(
            persistence_checks[key]
            for key in (
                "historical_rendered_prose_column_retained",
                "raw_legacy_value_column_retained",
                "unkeyed_model_retained",
            )
        ),
        persistence_checks,
        "Persisted historical evidence would not remain intact across renderer cutover.",
    )
    check(
        "STRUCTURED_SAVE_REGENERATES_READ_SUMMARY",
        persistence_checks["structured_save_increments_version"]
        and persistence_checks["structured_save_replaces_canonical_children"]
        and "scope.row_version == 1" in read_service_text
        and "canonical_projection" in read_service_text,
        persistence_checks,
        "Structured save/read flow does not deterministically project the current canonical aggregate.",
    )
    check(
        "PROSE_ONLY_BYPASS",
        persistence_checks["prose_only_read_path"]
        and persistence_checks["prose_only_historical_summary"],
        persistence_checks,
        "PROSE_ONLY records are not guaranteed to bypass the structured renderer.",
    )
    check(
        "UNKEYED_LEGACY_DATA_NOT_RENDERER_INPUT",
        persistence_checks["unkeyed_model_retained"],
        {
            **persistence_checks,
            "semantic_policy": "legacy_skip_by_design",
            "renderer_input": False,
            "mutation_guard_is_current_implementation_detail_not_cutover_requirement": True,
        },
        "Legacy unkeyed storage is no longer represented in the canonical model.",
    )
    check(
        "REASSESSMENT_COPY_EXACT",
        persistence_checks["reassessment_exact_scope_fields"]
        and persistence_checks["reassessment_copies_selections"]
        and persistence_checks["reassessment_copies_unkeyed"],
        persistence_checks,
        "Reassessment no longer copies the exact canonical/historical evaluation-scope aggregate.",
    )
    check(
        "NO_RENDERER_SCHEMA_OR_IMPORTER_MIGRATION_REQUIRED",
        persistence_checks["summary_is_not_persisted_column"]
        and "summary_text = (" in read_service_text,
        {
            "summary_storage": "read_time_projection_not_persisted",
            "schema_change_required": False,
            "importer_change_required": False,
            "migration_change_required": False,
        },
        "The current model requires persisted summary data or a migration for renderer ownership.",
    )

    status = (
        "CUTOVER_ACTIVE_VERIFIED"
        if not blockers and renderer_state == "CUTOVER_ACTIVE_VERIFIED"
        else "READY_FOR_CONTROLLED_CUTOVER"
        if not blockers and renderer_state == "PRE_CUTOVER_READY"
        else "BLOCKED"
    )
    return {
        "schema_version": "evaluation-scope-vba-cutover-readiness/v2",
        "phase": "C.5d.2",
        "status": status,
        "blockers": blockers,
        "contract": {
            "semantic_owner": "legacy_vba_with_explicit_product_corrections",
            "historical_prose_role": "immutable_history_diagnostic_not_oracle",
            "old_python_renderer_role": "compatibility_reference_not_oracle",
            "cutover_is_separate_slice": True,
            "production_renderer_switched_by_this_gate": False,
            "observed_renderer_state": renderer_state,
            "unkeyed_entries_policy": "LEGACY_SKIPPED_BY_DESIGN",
            "unkeyed_entries_are_cutover_blockers": False,
        },
        "checks": checks,
        "unkeyed_entries": unkeyed,
        "blast_radius": checks["PRODUCTION_BLAST_RADIUS_IDENTIFIED"]["evidence"],
        "persistence_contract": persistence_checks,
        "input_evidence": {
            "snapshot_sha256": _sha(SNAPSHOT_PATH),
            "taxonomy_sha256": _sha(TAXONOMY_PATH),
            "renderer_sha256": _sha(RENDERER_PATH),
            "semantics_spec_sha256": _sha(SPEC_PATH),
            "shadow_corpus_schema_version": corpus.get("schema_version"),
            "taxonomy_coverage_schema_version": taxonomy_coverage.get("schema_version"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT_PATH)
    parser.add_argument("--taxonomy", type=Path, default=TAXONOMY_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    snapshot = _load_json(args.snapshot)
    taxonomy = _load_json(args.taxonomy)
    report = audit(snapshot, taxonomy)
    report["input_evidence"]["snapshot_sha256"] = _sha(args.snapshot)
    report["input_evidence"]["taxonomy_sha256"] = _sha(args.taxonomy)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"STATUS={report['status']}")
    print(f"BLOCKERS={len(report['blockers'])}")
    print(f"OUTPUT={args.output}")
    if report["blockers"]:
        for blocker in report["blockers"]:
            print(f"BLOCKER={blocker['code']}: {blocker['message']}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
