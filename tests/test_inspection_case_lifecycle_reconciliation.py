from __future__ import annotations

from datetime import date, datetime, timezone
import inspect
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backend.app.domain import phase2_import
from tools.plan_inspection_case_lifecycle_reconciliation import (
    _date_candidate_status,
    _domain_candidate_status,
    DATE_COMPARISON_POLICY,
    build_reconciliation_plan,
    _period_start_end,
    _verify_read_only_rehearsal_connection,
    require_rehearsal_database,
    run_read_only_plan_from_snapshot,
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


def test_date_candidates_fail_closed_for_datetime_until_business_timezone_is_owned():
    assert _date_candidate_status("2026-08-21", date(2026, 8, 21))[0] == "ALREADY_MATCHES"
    assert _date_candidate_status("2026-08-21", date(2026, 8, 22))[0] == "CONFLICT_EXISTING_CANONICAL"
    assert _date_candidate_status("not-a-date", date(2026, 8, 21))[0] == "BLOCKED_AMBIGUOUS_LEGACY"
    assert _date_candidate_status("2026-01-14", datetime(2026, 1, 14, 16, 30, tzinfo=timezone.utc))[0] == "BLOCKED_TIMEZONE_POLICY_UNPROVEN"
    assert _date_candidate_status("2026-01-14", datetime(2026, 1, 14, 17, 30, tzinfo=timezone.utc))[0] == "BLOCKED_TIMEZONE_POLICY_UNPROVEN"
    assert _date_candidate_status("2026-01-15", datetime(2026, 1, 15, 0, 30, tzinfo=ZoneInfo("Asia/Bangkok")))[0] == "BLOCKED_TIMEZONE_POLICY_UNPROVEN"
    assert _date_candidate_status("2026-01-14", datetime(2026, 1, 14, 9, 0))[0] == "BLOCKED_TIMEZONE_POLICY_UNPROVEN"
    assert _date_candidate_status("", date(2026, 1, 14))[0] == "LEGACY_SOURCE_MISSING"
    assert _date_candidate_status("-", date(2026, 1, 14))[0] == "LEGACY_SOURCE_MISSING"
    assert _date_candidate_status("not-a-date", date(2026, 1, 14))[0] == "BLOCKED_AMBIGUOUS_LEGACY"


def test_period_reconciliation_requires_a_matching_start_and_end_pair():
    wrong_end = build_reconciliation_plan(
        [_legacy_row(inspected_at="17-19/07/2026", bbkt_reference="")],
        [_canonical_case(outcome={"inspected_on": date(2026, 7, 17), "inspected_to_on": date(2026, 7, 18)})],
    )
    actual = next(fact for fact in wrong_end["facts"] if fact["canonical_fact"] == "actual_inspection_period")
    assert actual["reconciliation_status"] == "CONFLICT_EXISTING_CANONICAL"
    assert actual["provenance_status"] == "MATCHES_NEITHER"
    assert actual["current_value_comparable"] is True
    assert actual["current_period_start_present"] is True
    assert actual["current_period_end_present"] is True

    missing_end = build_reconciliation_plan(
        [_legacy_row(inspected_at="17-19/07/2026", bbkt_reference="")],
        [_canonical_case(outcome={"inspected_on": date(2026, 7, 17), "inspected_to_on": None})],
    )
    actual = next(fact for fact in missing_end["facts"] if fact["canonical_fact"] == "actual_inspection_period")
    assert actual["reconciliation_status"] == "SAFE_UPDATE_IF_EMPTY"
    assert actual["current_value_present"] is True
    assert actual["current_value_comparable"] is True
    assert actual["current_period_start_present"] is True
    assert actual["current_period_end_present"] is False
    assert actual["current_period_start_matches_candidate"] is True

    exact = build_reconciliation_plan(
        [_legacy_row(inspected_at="17-19/07/2026", bbkt_reference="")],
        [_canonical_case(outcome={"inspected_on": date(2026, 7, 17), "inspected_to_on": date(2026, 7, 19)})],
    )
    actual = next(fact for fact in exact["facts"] if fact["canonical_fact"] == "actual_inspection_period")
    assert actual["reconciliation_status"] == "ALREADY_MATCHES"
    assert actual["provenance_status"] == "MATCHES_ACTUAL_SOURCE"

    empty = build_reconciliation_plan(
        [_legacy_row(inspected_at="17-19/07/2026", bbkt_reference="")],
        [_canonical_case(outcome={"inspected_on": None, "inspected_to_on": None})],
    )
    actual = next(fact for fact in empty["facts"] if fact["canonical_fact"] == "actual_inspection_period")
    assert actual["reconciliation_status"] == "SAFE_INSERT"
    assert actual["current_value_present"] is False
    assert actual["current_value_comparable"] is True
    assert actual["current_period_start_present"] is False
    assert actual["current_period_end_present"] is False

    bbkt_start_only = build_reconciliation_plan(
        [_legacy_row(inspected_at="17-19/07/2026", bbkt_reference="2026-07-17")],
        [_canonical_case(outcome={"inspected_on": date(2026, 7, 17), "inspected_to_on": date(2026, 7, 18)})],
    )
    actual = next(fact for fact in bbkt_start_only["facts"] if fact["canonical_fact"] == "actual_inspection_period")
    assert actual["reconciliation_status"] == "BLOCKED_PROVENANCE_CONTAMINATION"
    assert actual["provenance_status"] == "MATCHES_BBKT_SOURCE_ONLY"


def test_plan_blocks_datetime_submission_but_compares_pure_certificate_dates():
    report = build_reconciliation_plan(
        [_legacy_row()],
        [_canonical_case(application={"dossier_code": "HS-41", "submitted_on": datetime(2026, 1, 14, 12, tzinfo=timezone.utc)}, certificate={"issue_date": date(2026, 8, 21), "expiry_date": date(2029, 8, 19)})],
    )
    statuses = {fact["canonical_fact"]: fact["reconciliation_status"] for fact in report["facts"]}
    assert statuses["application_submitted_on"] == "BLOCKED_TIMEZONE_POLICY_UNPROVEN"
    assert statuses["certificate_issue_date"] == "ALREADY_MATCHES"
    assert statuses["certificate_expiry_date"] == "ALREADY_MATCHES"


def test_plan_reports_missing_legacy_sources_without_reclassifying_malformed_values():
    report = build_reconciliation_plan(
        [_legacy_row(dossier_code="-", submitted_at="", applicable_standard="", inspected_at="", bbkt_reference="")],
        [_canonical_case(application={"dossier_code": None, "submitted_on": None}, applicable_standard=None, outcome={"inspected_on": None, "inspected_to_on": None})],
    )
    facts = {fact["canonical_fact"]: fact for fact in report["facts"]}
    assert facts["dossier_code"]["reconciliation_status"] == "LEGACY_SOURCE_MISSING"
    assert facts["application_submitted_on"]["reconciliation_status"] == "LEGACY_SOURCE_MISSING"
    assert facts["applicable_standard"]["reconciliation_status"] == "LEGACY_SOURCE_MISSING"
    assert facts["actual_inspection_period"]["reconciliation_status"] == "LEGACY_SOURCE_MISSING"
    assert all(fact["recommended_future_action"] == "no_write" for fact in facts.values() if fact["reconciliation_status"] == "LEGACY_SOURCE_MISSING")

    malformed = build_reconciliation_plan(
        [_legacy_row(submitted_at="not-a-date")],
        [_canonical_case()],
    )
    submitted = next(fact for fact in malformed["facts"] if fact["canonical_fact"] == "application_submitted_on")
    assert submitted["reconciliation_status"] == "BLOCKED_AMBIGUOUS_LEGACY"


def test_certificate_source_missing_has_no_candidate_and_no_write_action():
    report = build_reconciliation_plan(
        [{"__source_ktra": _legacy_row(), "__certificate_sources": []}],
        [_canonical_case(certificates=[])],
    )
    certificate_facts = [
        fact
        for fact in report["facts"]
        if fact["canonical_fact"] in {"certificate_issue_date", "certificate_expiry_date"}
    ]
    assert {fact["reconciliation_status"] for fact in certificate_facts} == {"CERTIFICATE_SOURCE_MISSING"}
    assert {fact["legacy_certificate_candidate_count"] for fact in certificate_facts} == {0}
    assert {fact["canonical_certificate_candidate_count"] for fact in certificate_facts} == {0}
    assert {fact["recommended_future_action"] for fact in certificate_facts} == {"no_write"}


def test_date_fact_presence_is_distinct_from_comparability_and_does_not_leak_datetime():
    aware = datetime(2026, 1, 14, 17, 30, tzinfo=timezone.utc)
    report = build_reconciliation_plan(
        [_legacy_row()],
        [_canonical_case(application={"dossier_code": "HS-41", "submitted_on": aware})],
    )
    submitted = next(fact for fact in report["facts"] if fact["canonical_fact"] == "application_submitted_on")
    assert submitted["reconciliation_status"] == "BLOCKED_TIMEZONE_POLICY_UNPROVEN"
    assert submitted["current_value_present"] is True
    assert submitted["current_value_comparable"] is False
    assert submitted["current_comparison_blocker"] == "BLOCKED_UNPROVEN_BUSINESS_TIMEZONE"
    serialized = json.dumps(report, default=str)
    assert aware.isoformat() not in serialized
    assert str(aware) not in serialized


def test_date_fact_reports_naive_datetime_as_present_but_uncomparable():
    report = build_reconciliation_plan(
        [_legacy_row()],
        [_canonical_case(application={"dossier_code": "HS-41", "submitted_on": datetime(2026, 1, 14, 9, 0)})],
    )
    submitted = next(fact for fact in report["facts"] if fact["canonical_fact"] == "application_submitted_on")
    assert submitted["current_value_present"] is True
    assert submitted["current_value_comparable"] is False
    assert submitted["current_comparison_blocker"] == "BLOCKED_UNPROVEN_TIMEZONE"


def test_date_fact_reports_pure_date_and_null_current_value_deterministically():
    matching = build_reconciliation_plan([_legacy_row()], [_canonical_case()])
    submitted = next(fact for fact in matching["facts"] if fact["canonical_fact"] == "application_submitted_on")
    assert submitted["reconciliation_status"] == "ALREADY_MATCHES"
    assert submitted["current_value_present"] is True
    assert submitted["current_value_comparable"] is True
    assert submitted["current_comparison_blocker"] is None


def test_ambiguous_canonical_certificates_report_date_presence_per_field_without_values():
    no_issue_dates = build_reconciliation_plan(
        [_legacy_row()],
        [
            _canonical_case(
                certificates=[
                    {"issue_date": None, "expiry_date": date(2029, 8, 19)},
                    {"issue_date": None, "expiry_date": None},
                ]
            )
        ],
    )
    no_issue_facts = {fact["canonical_fact"]: fact for fact in no_issue_dates["facts"]}
    issue = no_issue_facts["certificate_issue_date"]
    expiry = no_issue_facts["certificate_expiry_date"]
    assert issue["reconciliation_status"] == "BLOCKED_CERTIFICATE_CANONICAL_AMBIGUOUS"
    assert issue["current_value_present"] is False
    assert issue["current_value_comparable"] is False
    assert issue["current_comparison_blocker"] == "BLOCKED_CERTIFICATE_CANONICAL_AMBIGUOUS"
    assert expiry["current_value_present"] is True
    assert expiry["current_value_comparable"] is False

    one_issue_date = build_reconciliation_plan(
        [_legacy_row()],
        [
            _canonical_case(
                certificates=[
                    {"issue_date": date(2026, 8, 21), "expiry_date": None},
                    {"issue_date": None, "expiry_date": None},
                ]
            )
        ],
    )
    one_issue_facts = {fact["canonical_fact"]: fact for fact in one_issue_date["facts"]}
    assert one_issue_facts["certificate_issue_date"]["current_value_present"] is True
    assert one_issue_facts["certificate_expiry_date"]["current_value_present"] is False
    serialized = json.dumps(one_issue_date, default=str)
    assert "2026-08-21" not in serialized

    missing = build_reconciliation_plan(
        [_legacy_row()],
        [_canonical_case(application={"dossier_code": "HS-41", "submitted_on": None})],
    )
    submitted = next(fact for fact in missing["facts"] if fact["canonical_fact"] == "application_submitted_on")
    assert submitted["reconciliation_status"] == "SAFE_INSERT"
    assert submitted["current_value_present"] is False
    assert submitted["current_value_comparable"] is True
    assert submitted["current_comparison_blocker"] is None


def test_report_declares_the_audited_date_comparison_policy():
    report = build_reconciliation_plan([_legacy_row()], [_canonical_case()])
    assert report["date_comparison_policy"] == DATE_COMPARISON_POLICY
    assert report["date_comparison_policy"]["canonical_timezone"] == "UNPROVEN"
    assert report["date_comparison_policy"]["aware_datetime_conversion"] == "BLOCKED_UNPROVEN_BUSINESS_TIMEZONE"
    assert report["date_comparison_policy"]["naive_datetime_conversion"] == "BLOCKED_UNPROVEN_TIMEZONE"


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
    assert not_found["facts"][0]["identity_gap_reason"] == "NO_DIRECT_OR_LINEAGE"
    assert not_found["identity_gap_reason_counts"] == {"NO_DIRECT_OR_LINEAGE": 1}
    conflict = build_reconciliation_plan([_legacy_row()], [_canonical_case(id="a"), _canonical_case(id="b")])
    assert conflict["summary"]["identity_conflicts"] == 1
    assert conflict["facts"][0]["reconciliation_status"] == "CASE_IDENTITY_CONFLICT"


def test_identity_resolver_uses_case_id_then_case_lineage_and_fails_closed_on_disagreement():
    lineage_only = _canonical_case(legacy_inspection_id=None, legacy_lineage=[{"entity_type": "case", "legacy_id": "41", "target_table": "case", "target_entity_id": "case-41"}])
    assert build_reconciliation_plan([_legacy_row()], [lineage_only])["summary"]["matched_cases"] == 1

    direct = _canonical_case(id="direct")
    lineage = _canonical_case(id="lineage", legacy_inspection_id=None, legacy_lineage=[{"entity_type": "case", "legacy_id": "41", "target_table": "case", "target_entity_id": "lineage"}])
    disagreement = build_reconciliation_plan([_legacy_row()], [direct, lineage])
    assert disagreement["facts"][0]["reconciliation_status"] == "CASE_IDENTITY_CONFLICT"

    multiple = build_reconciliation_plan([_legacy_row()], [lineage_only, _canonical_case(id="other", legacy_inspection_id=None, legacy_lineage=[{"entity_type": "case", "legacy_id": "41", "target_table": "case", "target_entity_id": "other"}])])
    assert multiple["facts"][0]["reconciliation_status"] == "CASE_IDENTITY_CONFLICT"


def test_safe_domains_normalize_only_known_values_without_fuzzy_matching():
    assert _domain_candidate_status("tái", "TAI", {"tai": "Tái"})[0] == "ALREADY_MATCHES"
    assert _domain_candidate_status("tai, moi", "Tái + Mới", {"tai, moi": "Tái + Mới", "tai + moi": "Tái + Mới"})[0] == "ALREADY_MATCHES"
    assert _domain_candidate_status("WHO-GMP", "WHO-GLP", {"who-gmp": "WHO-GMP", "who-glp": "WHO-GLP"})[0] == "CONFLICT_EXISTING_CANONICAL"
    assert _domain_candidate_status("unreviewed value", "WHO-GMP", {"who-gmp": "WHO-GMP"})[0] == "BLOCKED_AMBIGUOUS_LEGACY"
    assert _domain_candidate_status("", None, {"who-gmp": "WHO-GMP"})[0] == "LEGACY_SOURCE_MISSING"
    assert _domain_candidate_status("-", None, {"who-gmp": "WHO-GMP"})[0] == "LEGACY_SOURCE_MISSING"


def test_misrouting_provenance_requires_direct_copy_equality():
    matched = build_reconciliation_plan([_legacy_row()], [_canonical_case(application={"dossier_code": "HS-41", "submitted_on": date(2026, 1, 14), "dossier_reference": "540/QD-KT 05/05/2026"})])
    compatibility = next(fact for fact in matched["facts"] if fact["canonical_fact"] == "application_dossier_reference_compatibility")
    assert compatibility["provenance_status"] == "MATCHES_MISROUTED_SOURCE"

    nonmatch = build_reconciliation_plan([_legacy_row()], [_canonical_case(application={"dossier_code": "HS-41", "submitted_on": date(2026, 1, 14), "dossier_reference": "another value"})])
    compatibility = next(fact for fact in nonmatch["facts"] if fact["canonical_fact"] == "application_dossier_reference_compatibility")
    assert compatibility["provenance_status"] == "NOT_MATCHING_MISROUTED_SOURCE"


def test_contract_and_importer_keep_all_four_misrouting_paths_in_sync():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    paths = contract["legacy_misrouting_paths"]
    assert len(paths) == 4
    source = inspect.getsource(phase2_import)
    assert paths[0]["current_target_field"] == "dossier_reference"
    assert paths[1]["current_target_field"] == "decision_reference"
    assert 'dossier_reference=row.get("decision_reference") or None' in source
    assert 'decision_reference=row.get("decision_reference") or None' in source
    assert 'bbkt_reference=row.get("bbkt_reference") or None' in source
    assert "parse_date(row.get(\"bbkt_reference\", \"\")) or parse_date(row.get(\"inspected_at\", \"\"))" in source
    assert source.index("parse_date(row.get(\"bbkt_reference\", \"\"))") < source.index("parse_date(row.get(\"inspected_at\", \"\"))")


def test_read_only_runner_has_no_orm_write_operations_and_uses_read_only_transaction():
    from tools import plan_inspection_case_lifecycle_reconciliation as planner

    source = inspect.getsource(planner.run_read_only_plan_from_snapshot)
    assert "SET TRANSACTION READ ONLY" in source
    assert ".commit(" not in source
    assert ".flush(" not in source
    assert ".add(" not in source
    assert ".delete(" not in source


def test_snapshot_runner_keeps_the_read_only_db_contract():
    source = inspect.getsource(run_read_only_plan_from_snapshot)
    assert "SET TRANSACTION READ ONLY" in source
    assert "current_database" not in source  # verification remains in its dedicated owner.
    assert ".rollback(" in source


class _ScalarResult:
    def __init__(self, value: str):
        self.value = value

    def scalar_one(self) -> str:
        return self.value


class _ReadOnlyConnection:
    def __init__(self, database_name: str = "gxp_legacy_rehearsal", read_only: str = "on"):
        self.database_name = database_name
        self.read_only = read_only
        self.statements: list[str] = []

    def execute(self, statement):
        sql = str(statement)
        self.statements.append(sql)
        if sql.startswith("SELECT current_database"):
            return _ScalarResult(self.database_name)
        if sql.startswith("SHOW transaction_read_only"):
            return _ScalarResult(self.read_only)
        raise AssertionError(f"unexpected or mutating SQL: {sql}")


def test_connected_database_guard_requires_actual_rehearsal_database_and_read_only_transaction():
    connection = _ReadOnlyConnection()
    _verify_read_only_rehearsal_connection(connection)
    assert connection.statements == ["SELECT current_database()", "SHOW transaction_read_only"]
    with pytest.raises(RuntimeError, match="other than the required rehearsal"):
        _verify_read_only_rehearsal_connection(_ReadOnlyConnection(database_name="another_database"))
    with pytest.raises(RuntimeError, match="read-only database transaction"):
        _verify_read_only_rehearsal_connection(_ReadOnlyConnection(read_only="off"))


def test_period_parser_preserves_deterministic_same_and_cross_month_ranges():
    assert _period_start_end("20-21/10/2017") == (date(2017, 10, 20), date(2017, 10, 21))
    assert _period_start_end("31/07 - 01/08/2009") == (date(2009, 7, 31), date(2009, 8, 1))
    assert _period_start_end("01/12-12/12/2017") == (date(2017, 12, 1), date(2017, 12, 12))
