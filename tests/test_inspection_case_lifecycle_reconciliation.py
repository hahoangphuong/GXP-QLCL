from __future__ import annotations

from datetime import date
import inspect
import json
from pathlib import Path

import pytest

from backend.app.domain import phase2_import
from tools.plan_inspection_case_lifecycle_reconciliation import (
    build_reconciliation_plan,
    _period_start_end,
    require_rehearsal_database,
)


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "artifacts" / "legacy_audit" / "inspection_case_lifecycle_canonical_owner_contract.json"


def _legacy_row(**overrides: str) -> dict[str, str]:
    row = {
        "ID": "41",
        "decision_reference": "540/QD-KT 05/05/2026",
        "bbkt_reference": "2026-05-05 00:00:00+00:00",
        "inspected_at": "17-19/07/2026",
        "submitted_at": "14-01-2026",
        "dossier_code": "HS-41",
        "applicable_standard": "WHO-GMP",
        "inspection_type": "Tai",
        "certificate_issue_date": "2026-08-21",
        "certificate_expiry_date": "2029-08-19",
    }
    row.update(overrides)
    return row


def _canonical_case(**overrides: object) -> dict[str, object]:
    case: dict[str, object] = {
        "id": "case-41",
        "legacy_inspection_id": 41,
        "gxp_type": "GMP",
        "applicable_standard": "WHO-GMP",
        "inspection_type": "Tai",
        "application": {"dossier_code": "HS-41", "submitted_on": date(2026, 1, 14)},
        "plan": {},
        "outcome": {"inspected_on": date(2026, 7, 17), "inspected_to_on": date(2026, 7, 19), "decision_reference": "legacy-copy", "bbkt_reference": "legacy-copy"},
        "certificate": {"issue_date": date(2026, 8, 21), "expiry_date": date(2029, 8, 19)},
    }
    case.update(overrides)
    return case


def test_rehearsal_database_guard_is_explicit_and_name_independent_of_case_data():
    require_rehearsal_database("postgresql+psycopg://user:password@127.0.0.1:5432/gxp_legacy_rehearsal")
    with pytest.raises(RuntimeError, match="requires a PostgreSQL rehearsal"):
        require_rehearsal_database("sqlite:///gxp_legacy_rehearsal.db")
    with pytest.raises(RuntimeError, match="expected rehearsal database"):
        require_rehearsal_database("postgresql+psycopg://user:password@127.0.0.1:5432/another_database")


def test_plan_joins_by_stable_legacy_id_and_never_persists_raw_business_values():
    report = build_reconciliation_plan([_legacy_row()], [_canonical_case()])
    assert report["summary"]["matched_cases"] == 1
    assert report["summary"]["unmatched"] == 0
    assert report["summary"]["identity_conflicts"] == 0
    assert report["source_policy"]["legacy_values_raw_persisted"] is False
    assert all(fact["candidate_value"] is None for fact in report["facts"] if isinstance(fact["candidate_sha256"], str))


def test_plan_marks_b_ban_only_inspection_date_match_as_provenance_contamination():
    report = build_reconciliation_plan(
        [_legacy_row(bbkt_reference="2026-05-05", inspected_at="17-19/07/2026")],
        [_canonical_case(outcome={"inspected_on": date(2026, 5, 5), "inspected_to_on": None, "decision_reference": None, "bbkt_reference": "legacy"})],
    )
    actual = next(fact for fact in report["facts"] if fact["canonical_fact"] == "actual_inspection_period")
    assert actual["provenance_status"] == "MATCHES_BBKT_SOURCE_ONLY"
    assert actual["reconciliation_status"] == "BLOCKED_PROVENANCE_CONTAMINATION"


def test_plan_keeps_owner_missing_and_manual_reconciliation_fail_closed():
    report = build_reconciliation_plan(
        [_legacy_row(certificate_expiry_date="9-9", decision_reference="540/QD-KT")],
        [_canonical_case(plan={}, certificate={"issue_date": None, "expiry_date": None})],
    )
    by_fact = {fact["canonical_fact"]: fact for fact in report["facts"]}
    assert by_fact["inspection_decision_reference"]["reconciliation_status"] == "BLOCKED_OWNER_MISSING"
    assert by_fact["inspection_decision_date"]["legacy_morphology"] == "no_trailing_date"
    assert by_fact["certificate_expiry_date"]["reconciliation_status"] == "MANUAL_RECONCILIATION_REQUIRED"


def test_plan_reports_identity_not_found_and_conflict_without_guessing():
    not_found = build_reconciliation_plan([_legacy_row()], [])
    assert not_found["summary"]["unmatched"] == 1
    assert not_found["facts"][0]["reconciliation_status"] == "CASE_NOT_FOUND"
    conflict = build_reconciliation_plan([_legacy_row()], [_canonical_case(id="a"), _canonical_case(id="b")])
    assert conflict["summary"]["identity_conflicts"] == 1
    assert conflict["facts"][0]["reconciliation_status"] == "CASE_IDENTITY_CONFLICT"


def test_contract_and_importer_keep_all_four_misrouting_paths_in_sync():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    paths = contract["legacy_misrouting_paths"]
    assert len(paths) == 4
    source = inspect.getsource(phase2_import)
    assert paths[0]["current_target_field"] == "dossier_reference"
    assert paths[1]["current_target_field"] == "decision_reference"
    assert "dossier_reference" in source
    assert "decision_reference" in source
    assert "bbkt_reference" in source
    assert "parse_date(row.get(\"bbkt_reference\", \"\")) or parse_date(row.get(\"inspected_at\", \"\"))" in source
    assert source.index("parse_date(row.get(\"bbkt_reference\", \"\"))") < source.index("parse_date(row.get(\"inspected_at\", \"\"))")


def test_read_only_runner_has_no_orm_write_operations_and_uses_read_only_transaction():
    from tools import plan_inspection_case_lifecycle_reconciliation as planner

    source = inspect.getsource(planner.run_read_only_plan)
    assert "SET TRANSACTION READ ONLY" in source
    assert ".commit(" not in source
    assert ".flush(" not in source
    assert ".add(" not in source
    assert ".delete(" not in source


def test_period_parser_preserves_deterministic_same_and_cross_month_ranges():
    assert _period_start_end("20-21/10/2017") == (date(2017, 10, 20), date(2017, 10, 21))
    assert _period_start_end("31/07 - 01/08/2009") == (date(2009, 7, 31), date(2009, 8, 1))
    assert _period_start_end("01/12-12/12/2017") == (date(2017, 12, 1), date(2017, 12, 12))
