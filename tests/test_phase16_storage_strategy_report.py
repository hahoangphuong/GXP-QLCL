from tools.build_phase16_storage_strategy_report import build_report


def test_phase16_storage_strategy_report_prefers_external_bridge_for_planning():
    report = build_report()

    assert report["planning_recommendation"] == "external_bridge"
    assert report["current_direct_storage_baseline"] == "nfs_volume"


def test_phase16_storage_strategy_report_contains_both_options_and_rankings():
    report = build_report()

    assert {"nfs_volume", "external_bridge"} == set(report["options"].keys())
    assert len(report["ranking"]) == 2
    assert report["ranking"][0]["weighted_total"] >= report["ranking"][1]["weighted_total"]
