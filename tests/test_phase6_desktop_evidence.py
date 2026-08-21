from tools.validate_phase6_desktop_evidence import validate_matrix_rows


def test_validate_matrix_rows_accepts_known_statuses():
    errors = validate_matrix_rows(
        [
            {"scenario_id": "a", "status": "pass"},
            {"scenario_id": "b", "status": "blocked"},
            {"scenario_id": "c", "status": "pending"},
            {"scenario_id": "d", "status": "not_tested"},
        ]
    )

    assert errors == []


def test_validate_matrix_rows_rejects_duplicate_ids_and_unknown_status():
    errors = validate_matrix_rows(
        [
            {"scenario_id": "dup", "status": "pass"},
            {"scenario_id": "dup", "status": "mystery"},
        ]
    )

    assert any("duplicate scenario_id: dup" in error for error in errors)
    assert any("dup: invalid status 'mystery'" in error for error in errors)
