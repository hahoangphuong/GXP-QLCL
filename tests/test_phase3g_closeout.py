from tools.phase3g_closeout import classify_unresolved_row


def test_classify_unresolved_row_marks_placeholder_rows_as_archival():
    row = {"source_sheet": "db.ktra", "legacy_row_id": "257"}
    placeholder_rows = {"db.ktra": {"257"}}
    queue_lookup = {}
    assert classify_unresolved_row(row, placeholder_rows, queue_lookup) == "archival_placeholder"


def test_classify_unresolved_row_marks_candidate_rows_as_external_evidence():
    row = {"source_sheet": "db.cc", "legacy_row_id": "1456"}
    placeholder_rows = {"db.cc": set()}
    queue_lookup = {("db.cc", "1456"): {"candidate_cases": [{"legacy_case_id": 988}]}}
    assert classify_unresolved_row(row, placeholder_rows, queue_lookup) == "needs_external_evidence"


def test_classify_unresolved_row_falls_back_to_hard_unresolved():
    row = {"source_sheet": "db.dkkd", "legacy_row_id": "704"}
    placeholder_rows = {"db.dkkd": set()}
    queue_lookup = {("db.dkkd", "704"): {"candidate_cases": []}}
    assert classify_unresolved_row(row, placeholder_rows, queue_lookup) == "hard_unresolved"
