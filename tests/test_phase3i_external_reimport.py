from tools.phase3i_external_reimport import compare_counts


def test_compare_counts_returns_only_changed_keys():
    baseline = {"db.cc": 10, "db.dkkd": 5}
    current = {"db.cc": 12, "db.dkkd": 5, "db.Tdoi": 1}
    deltas = compare_counts(baseline, current)
    assert deltas == {
        "db.Tdoi": {"baseline": 0, "current": 1, "delta": 1},
        "db.cc": {"baseline": 10, "current": 12, "delta": 2},
    }


def test_compare_counts_returns_empty_when_equal():
    baseline = {"inspection_event": 5}
    current = {"inspection_event": 5}
    assert compare_counts(baseline, current) == {}
