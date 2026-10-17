from __future__ import annotations

from pathlib import Path

from tools.build_cutover_source_dependency_matrix_b6k import MATRIX


def test_cutover_dependency_matrix_covers_required_components_and_owners() -> None:
    required = {
        "B6A": "HARD_BOUND_CURRENT_SNAPSHOT",
        "B6B": "HARD_BOUND_CURRENT_SNAPSHOT",
        "B6C": "REVIEWED_SOURCE_BOUND",
        "B6H": "DATABASE_STATE_BOUND",
        "B6I": "REVIEWED_SOURCE_BOUND",
        "B6J": "DATABASE_STATE_BOUND",
        "canonical_state_exporter": "DATABASE_STATE_BOUND",
        "phase3_reviewed_artifacts": "REVIEWED_SOURCE_BOUND",
    }

    assert {key: MATRIX[key]["classification"] for key in required} == required
    for entry in MATRIX.values():
        assert entry["owner_files"]
        assert entry["binding_fields"]
        for owner_file in entry["owner_files"]:
            assert Path(owner_file).is_file()


def test_b6j_matrix_retains_all_cutover_provenance_bindings() -> None:
    assert set(MATRIX["B6J"]["binding_fields"]) >= {
        "legacy_snapshot_sha256",
        "canonical_state_sha256",
        "candidate_set_sha256",
        "candidate_set_roster_sha256",
        "candidate_set_roster_content_sha256",
        "candidate_set_roster_item_count",
        "source_alembic_revision",
        "source_database_identity",
        "plan_sha256",
    }
    assert set(MATRIX["B6J"]["external_approval_fields"]) == {
        "expected_plan_sha256", "expected_plan_file_sha256",
    }
    assert set(MATRIX["B6J"]["owner_files"]) >= {
        "backend/app/domain/production_line_population_b6j.py",
        "backend/app/domain/production_line_population_writer_b6j.py",
        "tools/plan_production_line_population_b6j.py",
        "tools/apply_production_line_population_b6j.py",
    }
    assert "independently record approved plan and file SHA" in MATRIX["B6J"]["cutover_action"]


def test_b6k_read_only_review_alignment_gate_is_explicit_in_handoff() -> None:
    gate = MATRIX["B6K_review_alignment"]
    assert gate["classification"] == "REVIEWED_SOURCE_BOUND"
    assert set(gate["binding_fields"]) >= {
        "candidate_set_sha256", "candidate_set_roster_sha256",
        "candidate_set_roster_content_sha256", "review_decision",
        "source_case_ids", "source_certificate_ids",
    }
    assert "exact reviewed B6I roster" in gate["cutover_action"]
    assert set(gate["external_approval_fields"]) == {
        "expected_plan_file_sha256", "expected_reviewed_roster_file_sha256",
    }
    assert set(gate["owner_files"]) == {
        "backend/app/domain/production_line_cutover_readiness_b6k.py",
        "tools/audit_production_line_cutover_readiness_b6k.py",
    }
    assert "resolve" in gate["cutover_action"]
    assert "blocker" in gate["cutover_action"]


def test_b6k_roster_binding_is_not_a_human_review_decision() -> None:
    assert MATRIX["B6I"]["classification"] == "REVIEWED_SOURCE_BOUND"
    assert "explicit review decisions" in MATRIX["B6I"]["cutover_action"]
    assert MATRIX["B6J"]["classification"] == "DATABASE_STATE_BOUND"
    assert "external_approval_fields" not in MATRIX["B6I"]
