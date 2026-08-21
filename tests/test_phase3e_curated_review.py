from tools.phase3e_curated_review import choose_curated_candidate, extract_years


def test_extract_years_finds_all_four_digit_years():
    assert extract_years("FT116/MH/001/2025") == [2025]
    assert extract_years("Báo cáo thanh tra 16-08-2018") == [2018]


def test_choose_curated_candidate_prefers_same_year_unique_match():
    candidates = [
        {"legacy_case_id": 1, "timeline_years": [2022]},
        {"legacy_case_id": 2, "timeline_years": [2025]},
    ]
    choice = choose_curated_candidate(2025, candidates)
    assert choice is not None
    assert choice["match_kind"] == "same_year"
    assert choice["matched_candidate"]["legacy_case_id"] == 2


def test_choose_curated_candidate_falls_back_to_previous_year_unique_match():
    candidates = [
        {"legacy_case_id": 1, "timeline_years": [2022]},
        {"legacy_case_id": 2, "timeline_years": [2025]},
    ]
    choice = choose_curated_candidate(2026, candidates)
    assert choice is not None
    assert choice["match_kind"] == "previous_year"
    assert choice["matched_candidate"]["legacy_case_id"] == 2
