from tools.phase3n_review_starter_pack import build_live_tracker_seed, build_submission_checklist


def test_build_live_tracker_seed_returns_rows():
    rows = build_live_tracker_seed()
    assert rows
    assert all("lane" in row for row in rows)
    assert all("review_keys" in row for row in rows)


def test_build_submission_checklist_contains_phase3j_gate_step():
    checklist = build_submission_checklist()
    assert any(step["title"] == "Run Phase 3j decision quality gate" for step in checklist)
