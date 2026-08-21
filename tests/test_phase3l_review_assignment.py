from tools.phase3l_review_assignment import (
    assign_bundles_to_lanes,
    build_site_group_key,
    estimate_effort_points,
)


def test_estimate_effort_points_penalizes_hard_unresolved_more():
    hard_row = {"classification": "hard_unresolved", "candidate_count": 0, "priority": "medium"}
    normal_row = {"classification": "needs_external_evidence", "candidate_count": 2, "priority": "medium"}
    assert estimate_effort_points(hard_row) > estimate_effort_points(normal_row)


def test_build_site_group_key_prefers_site_legacy_id():
    row = {"review_key": "db.cc:1", "legacy_context": {"site_legacy_id": "85", "site_name": "Ignored Name"}}
    assert build_site_group_key(row) == "site:85"


def test_assign_bundles_to_lanes_spreads_work_by_effort():
    bundles = [
        {"group_key": "a", "effort_points": 8, "row_count": 4, "review_keys": ["a1"], "rows": []},
        {"group_key": "b", "effort_points": 7, "row_count": 3, "review_keys": ["b1"], "rows": []},
        {"group_key": "c", "effort_points": 6, "row_count": 3, "review_keys": ["c1"], "rows": []},
        {"group_key": "d", "effort_points": 2, "row_count": 1, "review_keys": ["d1"], "rows": []},
    ]
    assignments = assign_bundles_to_lanes(bundles, ["lane_a", "lane_b", "lane_c"])
    lane_sizes = {lane: sum(bundle["effort_points"] for bundle in items) for lane, items in assignments.items()}
    assert max(lane_sizes.values()) - min(lane_sizes.values()) <= 6
