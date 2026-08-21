from tools.phase3f_final_adjudication import build_phase3f_analysis


def test_phase3f_finds_single_exact_site_match_for_change_detail():
    analysis = build_phase3f_analysis()
    assert analysis["adjudicated_suggestion_count"] >= 1
    suggestion = analysis["adjudicated_suggestions"][0]
    assert suggestion["source_sheet"] == "db.Tdoi"
    assert suggestion["legacy_row_id"] == "187"
    assert suggestion["override"]["site_legacy_id"] == 85
