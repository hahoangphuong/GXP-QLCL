from __future__ import annotations

from datetime import date
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, InspectionDecision, InspectionMinutesRecord, InspectionOutcome, InspectionPlan
from backend.app.domain.legacy_db_ktra_reconciliation import parse_legacy_inspection_decisions, parse_legacy_minutes_records, safe_evidence
from tools import apply_db_ktra_repeatable_semantics as apply


def _candidate(occurrence, *, legacy_id: int, case_id: str, owner_key: str, owner_id: str):
    return {
        "classification": "WRITE_CANDIDATE",
        "legacy_inspection_id": legacy_id,
        "canonical_case_id": case_id,
        owner_key: owner_id,
        "source_ordinal": occurrence["ordinal"],
        **{key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in occurrence.items() if key not in {"ordinal", "legacy_raw"}},
        **safe_evidence(occurrence["legacy_raw"]),
    }


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)
    case = Case(id="a0000000-0000-0000-0000-000000000001", legacy_inspection_id=1, site_id="a0000000-0000-0000-0000-000000000010", gxp_type="GMP", state=CaseState.DRAFT)
    plan = InspectionPlan(id="a0000000-0000-0000-0000-000000000011", case_id=case.id)
    outcome = InspectionOutcome(id="a0000000-0000-0000-0000-000000000012", case_id=case.id)
    session.add_all([case, plan, outcome])
    session.commit()
    return engine, session


def _prepared_source():
    decision_raw = "565/QD-QLD ngay 21/8/2018; thay the QD so 190/QD-QLD ngay 30/03/2018"
    minutes_raw = "01/02/2018 & 02/02/2018"
    decision = parse_legacy_inspection_decisions(decision_raw)["occurrences"]
    minutes = parse_legacy_minutes_records(minutes_raw)["occurrences"]
    case_id = "a0000000-0000-0000-0000-000000000001"
    decisions = [_candidate(item, legacy_id=1, case_id=case_id, owner_key="inspection_plan_id", owner_id="a0000000-0000-0000-0000-000000000011") for item in decision]
    minute_candidates = [_candidate(item, legacy_id=1, case_id=case_id, owner_key="inspection_outcome_id", owner_id="a0000000-0000-0000-0000-000000000012") for item in minutes]
    rows = [{"ID": "1", "decision_reference": decision_raw, "bbkt_reference": minutes_raw}]
    return decisions, minute_candidates, rows


def _valid_plan():
    decisions = [
        {
            "classification": "WRITE_CANDIDATE", "legacy_inspection_id": index,
            "canonical_case_id": f"case-{index}", "inspection_plan_id": f"plan-{index}",
            "source_ordinal": 1, "relation_type": None,
        }
        for index in range(1, 1220)
    ]
    # The audited source replacements are blocked IDs 601 and 745, not
    # members of the current write envelope.
    decisions[600]["legacy_inspection_id"] = 1300
    decisions[744]["legacy_inspection_id"] = 1301
    minutes = [
        {
            "classification": "WRITE_CANDIDATE", "legacy_inspection_id": index,
            "canonical_case_id": f"case-{index}", "inspection_outcome_id": f"outcome-{index}",
            "source_ordinal": 1,
        }
        for index in range(1, 1163)
    ]
    return {
        "schema_version": apply.PLAN_SCHEMA_VERSION,
        "guardrails": {"database_mutated": False, "fuzzy_matching_used": False, "importer_invoked": False, "apply_tool_present": False, "transaction_read_only": True},
        "canonical_gaps": {"classification": "NO_AUTO_CREATE", "count": 37, "write_candidates": 0, "legacy_inspection_ids": list(range(1220, 1257))},
        "compliance": {"write_candidates": 0},
        "decisions": {
            "explicit_replaces_relations": 2,
            "classification_records": [
                {"legacy_inspection_id": 601, "source_ordinal": 1, "classification": "BLOCKED_NO_INSPECTION_PLAN", "inspection_plan_id": None, "relation_type": "REPLACES", "replaces_source_reference": "190/QD-QLD"},
                {"legacy_inspection_id": 745, "source_ordinal": 1, "classification": "BLOCKED_NO_INSPECTION_PLAN", "inspection_plan_id": None, "relation_type": "REPLACES", "replaces_source_reference": "563/QD-QLD"},
            ],
        },
        "write_candidates": {"decisions": decisions, "minutes": minutes},
    }


def test_source_replay_recovers_exact_raw_and_rejects_safe_evidence_drift():
    decisions, minutes, rows = _prepared_source()
    prepared_decisions, prepared_minutes = apply.prepare_candidates({"write_candidates": {"decisions": decisions, "minutes": minutes}}, rows)
    assert prepared_decisions[0]["legacy_raw"] == "565/QD-QLD ngay 21/8/2018"
    assert prepared_minutes[1]["legacy_raw"] == "02/02/2018"
    decisions[0]["source_raw_hash"] = "0" * 64
    with pytest.raises(apply.ApplyFenceError, match="evidence"):
        apply.prepare_candidates({"write_candidates": {"decisions": decisions, "minutes": minutes}}, rows)


def test_preflight_apply_is_atomic_idempotent_and_links_only_explicit_replacement():
    engine, session = _session()
    try:
        decisions, minutes, rows = _prepared_source()
        prepared_decisions, prepared_minutes = apply.prepare_candidates({"write_candidates": {"decisions": decisions, "minutes": minutes}}, rows)
        first = apply.preflight(session, prepared_decisions, prepared_minutes, snapshot_rows=rows)
        assert first["actions"]["decisions"] == {"INSERT": 2}
        assert first["actions"]["minutes"] == {"INSERT": 2}
        assert first["actions"]["relations"] == {"LINK": 1}
        apply._apply_preflight(session, first)
        session.commit()

        persisted = list(session.scalars(select(InspectionDecision).order_by(InspectionDecision.ordinal)))
        assert len(persisted) == 2
        replacing = next(item for item in persisted if item.relation_type == "REPLACES")
        assert replacing.related_decision_id == next(item.id for item in persisted if item.id != replacing.id)
        assert session.scalar(select(InspectionPlan.decision_reference).where(InspectionPlan.id == "a0000000-0000-0000-0000-000000000011")) is None
        assert session.scalar(select(InspectionOutcome.minutes_recorded_on).where(InspectionOutcome.id == "a0000000-0000-0000-0000-000000000012")) is None

        replay = apply.preflight(session, prepared_decisions, prepared_minutes, snapshot_rows=rows)
        assert replay["actions"]["decisions"] == {"NOOP_IDENTICAL": 2}
        assert replay["actions"]["minutes"] == {"NOOP_IDENTICAL": 2}
        assert replay["actions"]["relations"] == {"NOOP_IDENTICAL": 1}
        apply._apply_preflight(session, replay)
    finally:
        session.close()
        engine.dispose()


def test_preflight_rejects_owner_mismatch_before_any_insert():
    engine, session = _session()
    try:
        decisions, minutes, rows = _prepared_source()
        decisions[0]["inspection_plan_id"] = "other-plan"
        prepared_decisions, prepared_minutes = apply.prepare_candidates({"write_candidates": {"decisions": decisions, "minutes": minutes}}, rows)
        with pytest.raises(apply.ApplyFenceError, match="InspectionPlan ID mismatch"):
            apply.preflight(session, prepared_decisions, prepared_minutes)
        assert session.scalar(select(InspectionDecision.id).limit(1)) is None
    finally:
        session.close()
        engine.dispose()


def test_plan_contract_rejects_wrong_counts_gaps_and_invalid_ids():
    plan = _valid_plan()
    assert [len(items) for items in apply.validate_plan(plan)] == [1219, 1162]
    plan["write_candidates"]["decisions"].pop()
    with pytest.raises(apply.ApplyFenceError, match="decision candidate count"):
        apply.validate_plan(plan)
    plan = _valid_plan()
    plan["write_candidates"]["decisions"][0]["legacy_inspection_id"] = 1220
    with pytest.raises(apply.ApplyFenceError, match="canonical gap"):
        apply.validate_plan(plan)
    plan = _valid_plan()
    plan["write_candidates"]["minutes"][0]["legacy_inspection_id"] = None
    with pytest.raises(apply.ApplyFenceError):
        apply.validate_plan(plan)
    plan = _valid_plan()
    plan["write_candidates"]["decisions"][1]["inspection_plan_id"] = "plan-1"
    with pytest.raises(apply.ApplyFenceError, match="duplicate"):
        apply.validate_plan(plan)
    plan = _valid_plan()
    plan["decisions"]["explicit_replaces_relations"] = 1
    with pytest.raises(apply.ApplyFenceError, match="source replacement count"):
        apply.validate_plan(plan)
    plan = _valid_plan()
    plan["write_candidates"]["decisions"][0]["relation_type"] = "REPLACES"
    with pytest.raises(apply.ApplyFenceError, match="writable replacement"):
        apply.validate_plan(plan)


def test_cli_requires_explicit_mode_and_postgres_rehearsal_target(tmp_path):
    with pytest.raises(SystemExit):
        apply.main(["--snapshot", str(tmp_path / "snapshot.json"), "--expected-snapshot-sha256", "0" * 64, "--plan", str(tmp_path / "plan.json"), "--expected-plan-sha256", "0" * 64, "--database-url", "sqlite:///unsafe.db", "--output", str(tmp_path / "report.json")])
    with pytest.raises(apply.ApplyFenceError, match="PostgreSQL"):
        apply._require_postgres_rehearsal("sqlite:///unsafe.db")
    with pytest.raises(apply.ApplyFenceError, match="other than"):
        apply._require_postgres_rehearsal("postgresql://user:password@host/other")


def test_report_is_deterministic_and_never_contains_connection_url():
    empty_audit = {"total": 0, "by_state": {state: 0 for state in apply.COMPATIBILITY_STATES}}
    prepared = {
        "decisions": [{"candidate": {"relation_type": None}}],
        "minutes": [{"candidate": {}}],
        "actions": {"decisions": {"INSERT": 1}, "minutes": {"INSERT": 1}, "relations": {}},
        "compatibility": {"decisions": empty_audit, "minutes": empty_audit},
    }
    plan = _valid_plan()
    first = apply._report(plan, "plan-sha", "snapshot-sha", "dry-run", {"inspection_decision": 0, "inspection_minutes_record": 0}, prepared, database_mutated=False)
    second = apply._report(plan, "plan-sha", "snapshot-sha", "dry-run", {"inspection_decision": 0, "inspection_minutes_record": 0}, prepared, database_mutated=False)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert "password" not in json.dumps(first).lower()
    assert first["database_mutated"] is False
    assert first["candidate_counts"] == {"decisions": 1, "minutes": 1, "source_replaces": 2, "writable_replaces": 0}
    assert first["actions"]["relations"] == {"LINK": 0, "NOOP_IDENTICAL": 0, "CONFLICT": 0}
    assert first["blocked_source_relations"] == {"count": 2, "by_classification": {"BLOCKED_NO_INSPECTION_PLAN": 2}}
    assert first["compatibility_audit"] == {"decisions": empty_audit, "minutes": empty_audit}
    assert first["actions"]["decisions"] == {"INSERT": 1, "NOOP_IDENTICAL": 0, "CONFLICT": 0}
    assert first["actions"]["minutes"] == {"INSERT": 1, "NOOP_IDENTICAL": 0, "CONFLICT": 0}


def test_existing_conflict_and_replacement_target_fail_closed():
    engine, session = _session()
    try:
        decisions, minutes, rows = _prepared_source()
        prepared_decisions, prepared_minutes = apply.prepare_candidates({"write_candidates": {"decisions": decisions, "minutes": minutes}}, rows)
        session.add(InspectionDecision(inspection_plan_id="a0000000-0000-0000-0000-000000000011", ordinal=1, reference="different", decision_on=date(2018, 8, 21), legacy_raw="different"))
        session.commit()
        with pytest.raises(apply.ApplyFenceError, match="conflicts"):
            apply.preflight(session, prepared_decisions, prepared_minutes)
    finally:
        session.close()
        engine.dispose()


def test_zero_writable_relations_insert_and_replay_without_relation_actions():
    engine, session = _session()
    try:
        decision_raw = "1/QD ngay 01/02/2018; 2/QD ngay 02/02/2018"
        minutes_raw = "01/02/2018 & 02/02/2018"
        decisions = [_candidate(item, legacy_id=1, case_id="a0000000-0000-0000-0000-000000000001", owner_key="inspection_plan_id", owner_id="a0000000-0000-0000-0000-000000000011") for item in parse_legacy_inspection_decisions(decision_raw)["occurrences"]]
        minutes = [_candidate(item, legacy_id=1, case_id="a0000000-0000-0000-0000-000000000001", owner_key="inspection_outcome_id", owner_id="a0000000-0000-0000-0000-000000000012") for item in parse_legacy_minutes_records(minutes_raw)["occurrences"]]
        rows = [{"ID": "1", "decision_reference": decision_raw, "bbkt_reference": minutes_raw}]
        prepared_decisions, prepared_minutes = apply.prepare_candidates({"write_candidates": {"decisions": decisions, "minutes": minutes}}, rows)
        first = apply.preflight(session, prepared_decisions, prepared_minutes)
        assert first["actions"]["relations"] == {}
        apply._apply_preflight(session, first)
        session.commit()
        assert all(item.relation_type is None for item in session.scalars(select(InspectionDecision)))
        replay = apply.preflight(session, prepared_decisions, prepared_minutes)
        assert replay["actions"]["decisions"] == {"NOOP_IDENTICAL": 2}
        assert replay["actions"]["relations"] == {}
    finally:
        session.close()
        engine.dispose()


def test_rollback_after_insert_candidate_leaves_no_partial_structured_rows():
    engine, session = _session()
    try:
        decisions, minutes, rows = _prepared_source()
        prepared_decisions, prepared_minutes = apply.prepare_candidates({"write_candidates": {"decisions": decisions, "minutes": minutes}}, rows)
        first = apply.preflight(session, prepared_decisions, prepared_minutes)
        try:
            apply._apply_preflight(session, first)
            raise RuntimeError("injected failure after flush")
        except RuntimeError:
            session.rollback()
        assert session.scalar(select(InspectionDecision.id).limit(1)) is None
        assert session.scalar(select(InspectionMinutesRecord.id).limit(1)) is None
    finally:
        session.close()
        engine.dispose()


def test_replacement_preflight_rejects_zero_multiple_cross_plan_and_self_targets():
    source = {"relation_type": "REPLACES", "replaces_source_reference": "target"}
    replacing = {"candidate": source, "desired": {"inspection_plan_id": "plan-1", "reference": "source"}, "existing": None, "action": "INSERT"}
    with pytest.raises(apply.ApplyFenceError, match="exactly one"):
        apply._preflight_replacements([replacing], {})
    target = {"candidate": {"relation_type": None}, "desired": {"inspection_plan_id": "plan-2", "reference": "target"}, "existing": None, "action": "INSERT"}
    with pytest.raises(apply.ApplyFenceError, match="exactly one"):
        apply._preflight_replacements([replacing, target], {})
    duplicate = {"candidate": {"relation_type": None}, "desired": {"inspection_plan_id": "plan-1", "reference": "target"}, "existing": None, "action": "INSERT"}
    with pytest.raises(apply.ApplyFenceError, match="exactly one"):
        apply._preflight_replacements([replacing, duplicate, {**duplicate}], {})
    self_reference = {"candidate": {"relation_type": "REPLACES", "replaces_source_reference": "source"}, "desired": {"inspection_plan_id": "plan-1", "reference": "source"}, "existing": None, "action": "INSERT"}
    with pytest.raises(apply.ApplyFenceError, match="exactly one"):
        apply._preflight_replacements([self_reference], {})


def test_failure_summary_redacts_database_credentials():
    assert "secret" not in apply._safe_error_summary(RuntimeError("postgresql://operator:secret@host/gxp"))
    assert "[REDACTED]" in apply._safe_error_summary(RuntimeError("postgresql://operator:secret@host/gxp"))


def test_compatibility_audit_covers_all_states_without_mutating_scalars():
    engine, session = _session()
    try:
        decision_raw = "1/QD ngay 01/02/2018"
        minutes_raw = "01/02/2018"
        rows = [{"ID": "1", "decision_reference": decision_raw, "bbkt_reference": minutes_raw}]
        initial = apply._compatibility_audit(session, rows)
        assert initial["decisions"]["by_state"]["MISSING_SINGLETON"] == 1
        assert initial["minutes"]["by_state"]["MISSING_SINGLETON"] == 1

        plan = session.get(InspectionPlan, "a0000000-0000-0000-0000-000000000011")
        outcome = session.get(InspectionOutcome, "a0000000-0000-0000-0000-000000000012")
        plan.decision_reference, plan.decision_date, plan.decision_legacy_raw = "1/QD", date(2018, 2, 1), decision_raw
        outcome.minutes_recorded_on, outcome.minutes_recorded_time, outcome.minutes_legacy_raw, outcome.bbkt_reference = date(2018, 2, 1), None, minutes_raw, None
        assert apply._compatibility_audit(session, rows)["decisions"]["by_state"]["MATCH_SINGLETON"] == 1
        minutes_audit = apply._compatibility_audit(session, rows)["minutes"]
        # Cleared B. bản evidence cannot invalidate a matching typed projection.
        assert minutes_audit["by_state"]["MATCH_SINGLETON"] == 1
        assert minutes_audit["bbkt_reference_evidence"]["CLEARED_OR_ABSENT"] == 1

        plan.decision_reference = "wrong"
        outcome.bbkt_reference = "wrong"
        conflict = apply._compatibility_audit(session, rows)
        assert conflict["decisions"]["by_state"]["CONFLICT_SINGLETON"] == 1
        assert conflict["minutes"]["by_state"]["MATCH_SINGLETON"] == 1
        assert conflict["minutes"]["bbkt_reference_evidence"]["CONFLICTS_SOURCE_RAW"] == 1

        plan.decision_reference = plan.decision_date = plan.decision_legacy_raw = None
        outcome.minutes_recorded_on = outcome.minutes_recorded_time = outcome.minutes_legacy_raw = outcome.bbkt_reference = None
        multiple = [{"ID": "1", "decision_reference": "1/QD ngay 01/02/2018; 2/QD ngay 02/02/2018", "bbkt_reference": "01/02/2018 & 02/02/2018"}]
        null_ok = apply._compatibility_audit(session, multiple)
        assert null_ok["decisions"]["by_state"]["NULL_OK_MULTIPLE"] == 1
        assert null_ok["minutes"]["by_state"]["NULL_OK_MULTIPLE"] == 1
        plan.decision_reference = "1/QD"
        outcome.minutes_recorded_on = date(2018, 2, 1)
        should_null = apply._compatibility_audit(session, multiple)
        assert should_null["decisions"]["by_state"]["SHOULD_BE_NULL_MULTIPLE"] == 1
        assert should_null["minutes"]["by_state"]["SHOULD_BE_NULL_MULTIPLE"] == 1

        no_source = [{"ID": "1", "decision_reference": "unstructured prose", "bbkt_reference": "unstructured prose"}]
        none = apply._compatibility_audit(session, no_source)
        assert none["decisions"]["by_state"]["NO_STRUCTURED_SOURCE"] == 1
        assert none["minutes"]["by_state"]["NO_STRUCTURED_SOURCE"] == 1
        assert set(none["decisions"]["by_state"]) == set(apply.COMPATIBILITY_STATES)
        assert set(none["minutes"]["by_state"]) == set(apply.COMPATIBILITY_STATES)
    finally:
        session.rollback()
        session.close()
        engine.dispose()
