from __future__ import annotations

import json
from pathlib import Path

from tools.audit_evaluation_scope_vba_cutover_readiness import (
    EXPECTED_CORPUS,
    EXPECTED_TAXONOMY_ROWS,
    audit,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = REPOSITORY_ROOT / "artifacts/phase3c/legacy_snapshot.json"
TAXONOMY_PATH = REPOSITORY_ROOT / "artifacts/legacy_snapshot/evaluation_scope_taxonomy.json"
ARTIFACT_PATH = REPOSITORY_ROOT / "artifacts/legacy_audit/evaluation_scope_vba_cutover_readiness.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_c5d2_vba_cutover_readiness_gate_accepts_current_source_evidence():
    report = audit(_load(SNAPSHOT_PATH), _load(TAXONOMY_PATH))

    assert report["status"] in {"READY_FOR_CONTROLLED_CUTOVER", "CUTOVER_ACTIVE_VERIFIED"}
    assert report["blockers"] == []
    assert all(check["status"] == "PASS" for check in report["checks"].values())

    corpus = report["checks"]["CORPUS_COMPILES"]["evidence"]
    assert corpus["actual"] == EXPECTED_CORPUS
    assert corpus["compile_exceptions"] == 0
    assert report["checks"]["SPAN_PROVENANCE_INTEGRITY"]["evidence"]["span_integrity_failures"] == 0
    assert report["checks"]["DEFERRED_SEMANTIC_RULES"]["evidence"]["deferred_rule_records"] == 0

    coverage = report["checks"]["EXHAUSTIVE_TAXONOMY_COVERAGE"]["evidence"]["families"]
    for gxp_type, expected_rows in EXPECTED_TAXONOMY_ROWS.items():
        assert coverage[gxp_type]["taxonomy_rows"] == expected_rows
        assert coverage[gxp_type]["blank_custom_pass"] == expected_rows
        assert coverage[gxp_type]["nonblank_custom_pass"] == expected_rows
        assert coverage[gxp_type]["family_blank_custom_pass"] == 1
        assert coverage[gxp_type]["family_nonblank_custom_pass"] == 1

    assert report["checks"]["GDP_FAIL_CLOSED"]["status"] == "PASS"
    assert report["checks"]["GMPBB_DISTINCT_PROSE_ONLY"]["status"] == "PASS"
    assert report["checks"]["FIRST_KEY_PRODUCT_CORRECTION"]["evidence"]["expanded_keys"] == ["1.1", "1.2"]
    assert report["checks"]["FIRST_KEY_PRODUCT_CORRECTION"]["evidence"]["matched_after_open_parenthesis"] == [True, False]


def test_c5d2_readiness_artifact_makes_unkeyed_and_cutover_boundaries_explicit():
    report = _load(ARTIFACT_PATH)

    assert report["status"] == "CUTOVER_ACTIVE_VERIFIED"
    assert report["blockers"] == []
    assert report["contract"]["production_renderer_switched_by_this_gate"] is False
    assert report["contract"]["cutover_is_separate_slice"] is True
    assert report["contract"]["observed_renderer_state"] == "CUTOVER_ACTIVE_VERIFIED"
    assert report["contract"]["unkeyed_entries_policy"] == "LEGACY_SKIPPED_BY_DESIGN"
    assert report["contract"]["unkeyed_entries_are_cutover_blockers"] is False

    unkeyed = report["unkeyed_entries"]
    assert unkeyed["classification"] == "LEGACY_SKIPPED_BY_DESIGN"
    assert unkeyed["policy_authority"] == "project_owner_explicit_confirmation"
    assert unkeyed["legacy_marker"] == "leading_hyphen"
    assert unkeyed["renderer_policy"] == "SKIP_ALWAYS"
    assert unkeyed["rekey_policy"] == "NEVER_REKEY_OR_RECOVER"
    assert unkeyed["summary_policy"] == "NEVER_RENDER"
    assert unkeyed["cutover_blocker"] is False
    assert unkeyed["counts"] == {"total": 903}
    assert report["checks"]["UNKEYED_LEGACY_SKIP_POLICY"]["status"] == "PASS"
    assert report["checks"]["UNKEYED_LEGACY_DATA_NOT_RENDERER_INPUT"]["status"] == "PASS"

    blast_radius = report["blast_radius"]
    assert blast_radius["production_summary_owner"] == (
        "backend/app/services/catalog.py::CatalogReadService._serialize_evaluation_scope"
    )
    assert blast_radius["read_api"] == "GET /cases/{case_id}/workspace"
    assert blast_radius["mutation_api"] == "PUT /cases/{case_id}/evaluation-scope"
    assert blast_radius["renderer_state"] == "CUTOVER_ACTIVE_VERIFIED"
    assert blast_radius["old_renderer_symbol_occurrences_outside_domain"] == []
    vba_calls = blast_radius["vba_renderer_symbol_occurrences_outside_domain"]
    workspace_calls = blast_radius["workspace_vba_renderer_calls"]
    document_projection_calls = blast_radius["document_projection_vba_renderer_calls"]
    assert len(workspace_calls) == 2
    assert all(call.startswith("backend/app/services/catalog.py:") for call in workspace_calls)
    assert len(document_projection_calls) in {0, 2}
    assert all(
        call.startswith("backend/app/domain/evaluation_scope_document_projection.py:")
        for call in document_projection_calls
    )
    assert blast_radius["unexpected_vba_renderer_calls"] == []
    assert set(workspace_calls + document_projection_calls) == set(vba_calls)

    persistence = report["persistence_contract"]
    assert persistence["prose_only_read_path"] is True
    assert persistence["unkeyed_mutation_fail_closed"] is True
    assert persistence["reassessment_exact_scope_fields"] is True
    assert persistence["reassessment_copies_selections"] is True
    assert persistence["reassessment_copies_unkeyed"] is True
    assert persistence["summary_is_not_persisted_column"] is True
