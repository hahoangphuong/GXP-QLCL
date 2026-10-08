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
    }
