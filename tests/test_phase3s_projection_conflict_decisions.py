from tools.validate_phase3s_projection_conflict_decisions import validate_decisions


def test_validate_decisions_accepts_well_formed_winner():
    errors = validate_decisions(
        [
            {
                "conflict_key": "db.cc::GMP-1",
                "candidate_legacy_ids": ["10", "11"],
                "decision_action": "winner",
                "selected_candidate_legacy_id": "10",
                "reviewer": "tester",
                "reviewed_on": "2026-08-14",
                "decision_rationale": "Chosen by evidence.",
            }
        ]
    )

    assert errors == []


def test_validate_decisions_rejects_invalid_pending_payload():
    errors = validate_decisions(
        [
            {
                "conflict_key": "db.cc::GMP-1",
                "candidate_legacy_ids": ["10", "11"],
                "decision_action": "pending",
                "selected_candidate_legacy_id": None,
                "reviewer": "tester",
                "reviewed_on": "",
                "decision_rationale": "",
            }
        ]
    )

    assert any("pending action must not include reviewer/rationale/date" in error for error in errors)


def test_validate_decisions_accepts_default_pending_template_row():
    errors = validate_decisions(
        [
            {
                "conflict_key": "db.cc::GMP-2",
                "candidate_legacy_ids": ["1241", "1598"],
                "decision_action": "pending",
                "selected_candidate_legacy_id": None,
                "reviewer": None,
                "reviewed_on": None,
                "decision_rationale": "",
            }
        ]
    )

    assert errors == []
