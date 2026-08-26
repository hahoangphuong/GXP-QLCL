from tools.build_phase3t_projection_conflict_review_pack import (
    build_candidate_detail_lines,
    build_decision_question,
    build_review_pack,
    build_review_focus,
)


def test_build_review_focus_for_certificate_conflict():
    focus = build_review_focus(
        {"classification": "blank_ma_dc_non_case_backed_multi_current"}
    )

    assert "current certificate winner" in focus


def test_build_decision_question_for_case_conflict():
    question = build_decision_question({"projection_type": "current_case_projection"})

    assert "current case projection" in question


def test_build_candidate_detail_lines_for_certificate_rows():
    lines = build_candidate_detail_lines(
        {
            "rows": [
                {
                    "legacy_row_id": "1241",
                    "certificate_no": "OGYEI/895-7/2023",
                    "issue_date": "2023-10-16",
                    "expiry_date": "2026-05-01",
                }
            ]
        },
        "current_certificate_projection",
    )

    assert "certificate_no=OGYEI/895-7/2023" in lines[0]


def test_build_review_pack_carries_phase3p_and_decision_provenance():
    payload = build_review_pack()

    assert payload["source_phase3p_path"] == "artifacts/phase3p/current_projection_conflicts.json"
    assert payload["source_decision_contract_path"] == "artifacts/phase3s/current_projection_conflict_decisions.template.json"
    assert payload["source_conflict_count"] == 14
