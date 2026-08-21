from tools.validate_phase7_cutover_checklist import validate_rows


def test_validate_rows_accepts_known_statuses():
    errors = validate_rows(
        [
            {"item_id": "a", "status": "pass"},
            {"item_id": "b", "status": "blocked"},
            {"item_id": "c", "status": "pending"},
            {"item_id": "d", "status": "not_started"},
        ]
    )

    assert errors == []


def test_validate_rows_rejects_duplicate_ids_and_unknown_status():
    errors = validate_rows(
        [
            {"item_id": "dup", "status": "pass"},
            {"item_id": "dup", "status": "mystery"},
        ]
    )

    assert any("duplicate item_id: dup" in error for error in errors)
    assert any("dup: invalid status 'mystery'" in error for error in errors)
