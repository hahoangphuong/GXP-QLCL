from tools.phase3o_adjudication_cycle_simulator import (
    build_simulated_decisions,
    choose_simulation_rows,
)


def test_choose_simulation_rows_prefers_small_candidate_b1_rows():
    rows = choose_simulation_rows(limit=3)
    assert rows
    assert len(rows) <= 3
    assert all(row["classification"] == "needs_external_evidence" for row in rows)
    assert all(1 <= row["candidate_count"] <= 3 for row in rows)


def test_build_simulated_decisions_selects_first_candidate():
    rows = [
        {
            "review_key": "db.cc:1153",
            "source_sheet": "db.cc",
            "legacy_row_id": "1153",
            "candidate_legacy_ids": [836, 1171, 1205],
            "legacy_context": {"certificate_number": "5130408003836"},
        }
    ]
    decisions = build_simulated_decisions(rows)
    assert decisions[0]["selected_legacy_id"] == 836
    assert decisions[0]["decision"] == "approve_override"
