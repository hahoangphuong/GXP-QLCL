from __future__ import annotations

import json
from hashlib import sha256

import pytest

from tools import profile_legacy_semantics as profiler


def _snapshot(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    return {"db.ktra": rows}


def test_profiles_sentinels_morphology_cardinality_and_composites() -> None:
    inventory = profiler.build_inventory(
        _snapshot(
            [
                {"ID": "1", "Date": "01/02/2026", "Refs": "A; B", "State": "???"},
                {"ID": "2", "Date": "01/02-03/02/2026", "Refs": "A; B", "State": "-"},
                {"ID": "3", "Date": "01/02/2026, 03/02/2026", "Refs": "A\nB", "State": ""},
            ]
        ),
        contracts={},
    )
    by_header = {field["legacy_header"]: field for field in inventory["fields"]}
    assert by_header["Date"]["source_profile"]["morphology"] == {
        "DATE_RANGE": 1,
        "MULTI_DATE_OR_PERIOD": 1,
        "SINGLE_DATE": 1,
    }
    assert by_header["Date"]["cardinality"] == "0..n"
    assert by_header["Date"]["composite_value_evidence"] is True
    assert by_header["Refs"]["source_profile"]["newline_or_multiline_count"] == 1
    assert by_header["Refs"]["cardinality"] == "0..n"
    assert by_header["State"]["sentinels"] == {"pending_input": 1, "not_applicable": 1, "missing": 1}


def test_detects_low_cardinality_enums_references_and_unmapped_fields() -> None:
    inventory = profiler.build_inventory(
        _snapshot(
            [{"ID": str(index), "Mã hồ sơ": f"HS-{index}", "Status": "A" if index % 2 else "B"} for index in range(1, 12)]
        ),
        contracts={},
    )
    by_header = {field["legacy_header"]: field for field in inventory["fields"]}
    assert "IDENTITY" in by_header["ID"]["observed_shapes"]
    assert "REFERENCE" in by_header["Mã hồ sơ"]["observed_shapes"]
    assert "SCALAR_ENUM_LIKE" in by_header["Status"]["observed_shapes"]
    assert by_header["Status"]["owner_status"] == "NOT_MAPPED"


def test_detects_identical_and_embedded_cross_field_relationships() -> None:
    rows = [
        {"ID": str(index), "Copy": f"REF-{index}", "Also copy": f"REF-{index}", "Composite": f"prefix REF-{index} suffix"}
        for index in range(1, 12)
    ]
    relationships = profiler.build_inventory(_snapshot(rows), contracts={})["relationships"]
    kinds = {(item["left"], item["right"], item["kind"]) for item in relationships}
    assert ("Copy", "Also copy", "IDENTICAL_NONEMPTY_VALUES") in kinds
    assert ("Copy", "Composite", "EMBEDDED_VALUE_RELATIONSHIP") in kinds


def test_owner_contract_and_period_reference_do_not_restore_bbkt_as_timing_owner() -> None:
    inventory = profiler.build_inventory(
        _snapshot([{"ID": str(index), "Ngày K.tra": "01/02/2026", "B. bản": "02/02/2026"} for index in range(1, 12)])
    )
    by_header = {field["legacy_header"]: field for field in inventory["fields"]}
    assert by_header["Ngày K.tra"]["canonical_owner"] == "InspectionPeriodSegment ordered by ordinal"
    assert by_header["B. bản"]["owner_status"] == "OWNER_MISMATCH"
    assert "not an actual inspection-date source" in by_header["B. bản"]["current_mapping"]["notes"]


def test_period_source_states_are_derived_from_the_existing_parser() -> None:
    inventory = profiler.build_inventory(
        _snapshot([
            {"ID": "1", "Ngày K.tra": "01/02/2026"},
            {"ID": "2", "Ngày K.tra": "???"},
            {"ID": "3", "Ngày K.tra": "-"},
            {"ID": "4", "Ngày K.tra": ""},
            {"ID": "5", "Ngày K.tra": "Theo kế hoạch"},
            {"ID": "", "Ngày K.tra": ""},
        ])
    )
    period = next(field for field in inventory["fields"] if field["legacy_header"] == "Ngày K.tra")
    assert period["source_profile"]["inspection_period_source_state"] == {
        "KNOWN": 1,
        "MISSING": 1,
        "NON_DATE_EXPRESSION": 1,
        "NOT_APPLICABLE": 1,
        "PENDING_INPUT": 1,
    }


def test_risk_classification_and_questions_are_deterministic() -> None:
    inventory = profiler.build_inventory(_snapshot([{"ID": "1", "Kết quả": "Đạt"}]))
    result = next(field for field in inventory["fields"] if field["legacy_header"] == "Kết quả")
    assert result["risk"] == "CRITICAL"
    assert inventory["unresolved_business_questions"] == profiler.build_inventory(_snapshot([{"ID": "1", "Kết quả": "Đạt"}]))["unresolved_business_questions"]


def test_snapshot_sha_guard_rejects_wrong_snapshot_before_output(tmp_path) -> None:
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(_snapshot([{"ID": "1"}])), encoding="utf-8")
    with pytest.raises(RuntimeError, match="snapshot SHA256"):
        profiler.main(
            [
                "--snapshot", str(snapshot_path),
                "--output", str(tmp_path / "out.json"),
                "--questions-output", str(tmp_path / "questions.json"),
                "--report-output", str(tmp_path / "report.md"),
                "--expected-snapshot-sha256", "0" * 64,
            ]
        )
    assert not (tmp_path / "out.json").exists()


def test_cli_accepts_matching_snapshot_hash_and_writes_deterministically(tmp_path) -> None:
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(_snapshot([{"ID": "1", "Status": "A"}])), encoding="utf-8")
    expected = sha256(snapshot_path.read_bytes()).hexdigest()
    args = [
        "--snapshot", str(snapshot_path),
        "--output", str(tmp_path / "out.json"),
        "--questions-output", str(tmp_path / "questions.json"),
        "--report-output", str(tmp_path / "report.md"),
        "--expected-snapshot-sha256", expected,
    ]
    assert profiler.main(args) == 0
    first = (tmp_path / "out.json").read_bytes()
    assert profiler.main(args) == 0
    assert (tmp_path / "out.json").read_bytes() == first


@pytest.mark.parametrize(
    ("dialect", "database_name", "read_only"),
    [
        ("sqlite", "gxp_legacy_rehearsal", True),
        ("postgresql", "gxp", True),
        ("postgresql", "gxp_legacy_rehearsal", False),
    ],
)
def test_readonly_rehearsal_guard_rejects_wrong_target_or_transaction(dialect: str, database_name: str, read_only: bool) -> None:
    with pytest.raises(RuntimeError):
        profiler.validate_readonly_rehearsal_target(dialect=dialect, database_name=database_name, transaction_read_only=read_only)


def test_readonly_rehearsal_guard_accepts_only_readonly_postgresql_rehearsal() -> None:
    profiler.validate_readonly_rehearsal_target(dialect="postgresql", database_name="gxp_legacy_rehearsal", transaction_read_only=True)
