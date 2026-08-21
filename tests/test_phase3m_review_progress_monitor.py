from tools.phase3m_review_progress_monitor import parse_iso_date, validate_tracker_row


def test_parse_iso_date_accepts_valid_date():
    parsed = parse_iso_date("2026-08-13")
    assert parsed is not None
    assert parsed.isoformat() == "2026-08-13"


def test_validate_tracker_row_rejects_future_started_on():
    row = {
        "lane": "lane_alpha",
        "group_key": "site:85",
        "review_keys": ["db.cc:1"],
        "status": "in_progress",
        "assignee": "reviewer.a",
        "started_on": "2026-08-14",
        "completed_on": "",
        "decision_file_updated": False,
        "notes": "",
    }
    errors = validate_tracker_row(row)
    assert any("cannot be in the future" in error for error in errors)


def test_validate_tracker_row_requires_completed_on_for_completed_status():
    row = {
        "lane": "lane_bravo",
        "group_key": "site:90",
        "review_keys": ["db.cc:2"],
        "status": "completed",
        "assignee": "reviewer.b",
        "started_on": "2026-08-12",
        "completed_on": "",
        "decision_file_updated": True,
        "notes": "",
    }
    errors = validate_tracker_row(row)
    assert any("completed rows require completed_on" in error for error in errors)


def test_validate_tracker_row_requires_notes_for_blocked_status():
    row = {
        "lane": "lane_charlie",
        "group_key": "site:91",
        "review_keys": ["db.cc:3"],
        "status": "blocked",
        "assignee": "reviewer.c",
        "started_on": "2026-08-12",
        "completed_on": "",
        "decision_file_updated": False,
        "notes": "",
    }
    errors = validate_tracker_row(row)
    assert any("blocked rows require notes" in error for error in errors)
