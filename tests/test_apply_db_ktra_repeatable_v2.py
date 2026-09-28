from __future__ import annotations

from datetime import date
from hashlib import sha256
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, InspectionDecision, InspectionOutcome, InspectionPlan
from backend.app.domain.legacy_snapshot_v2 import SCHEMA_VERSION, snapshot_bytes
from tools import apply_db_ktra_repeatable_v2 as apply
from tools import reconcile_db_ktra_repeatable_v2 as reconciliation


def _snapshot() -> tuple[dict[str, object], str]:
    header = ["ID", "LOẠI KT", "ID CƠ SỞ", "Q. định", "B. bản"]
    cells = lambda values: [{"column_ordinal": index, "raw_value": value} for index, value in enumerate(values, 1)]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "sheets": [{"sheet_name": "db.ktra", "raw_rows": [
            {"source_row_number": 4, "cells": cells(header)},
            {"source_row_number": 5, "cells": cells([1, "GMP", 1, "376/QD-QLD ngày 29/08/2016;", "-"])},
        ]}],
    }
    return payload, sha256(snapshot_bytes(payload)).hexdigest()


def _session() -> tuple[object, Session]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)
    case = Case(
        id="a0000000-0000-0000-0000-000000000001", legacy_inspection_id=1,
        site_id="a0000000-0000-0000-0000-000000000010", gxp_type="GMP", state=CaseState.DRAFT,
    )
    plan = InspectionPlan(
        id="a0000000-0000-0000-0000-000000000011", case_id=case.id, decision_reference="376/QD-QLD",
        decision_date=date(2016, 8, 29), decision_legacy_raw="376/QD-QLD ngày 29/08/2016;",
    )
    session.add_all([case, plan, InspectionOutcome(id="a0000000-0000-0000-0000-000000000012", case_id=case.id)])
    session.commit()
    return engine, session


def _approved(session: Session, snapshot: dict[str, object], digest: str, monkeypatch) -> tuple[dict[str, object], dict[str, object]]:
    monkeypatch.setattr(reconciliation, "CANONICAL_SNAPSHOT_SHA256", digest)
    canonical, decisions, minutes, integrity = reconciliation._read_canonical(session)
    topology = reconciliation.topology_evidence_for_canonical(canonical, owner_integrity=integrity)
    report = reconciliation.build_reconciliation(
        snapshot, canonical, decisions, minutes, expected_snapshot_sha256=digest,
        topology_evidence=topology, owner_integrity=integrity,
    )
    return report["dry_run_apply_plan"], topology


def test_exact_one_action_is_fingerprinted_and_apply_is_explicit(monkeypatch):
    engine, session = _session()
    try:
        snapshot, digest = _snapshot()
        approved, _topology = _approved(session, snapshot, digest, monkeypatch)
        assert approved["write_authorized"] is False
        assert approved["writer_invoked"] is False
        assert len(approved["actions"]) == 1
        assert approved["actions"][0]["kind"] == "decisions"
        assert apply.action_fingerprint(approved) == apply.action_fingerprint(approved)
    finally:
        session.close()
        engine.dispose()


def test_guarded_apply_inserts_one_decision_without_rewriting_plan_and_second_run_rejects_stale_plan(monkeypatch):
    engine, session = _session()
    try:
        snapshot, digest = _snapshot()
        approved, topology = _approved(session, snapshot, digest, monkeypatch)
        session.rollback()
        with session.begin():
            result = apply.guarded_apply(session, snapshot, topology_evidence=topology, approved_plan=approved)
        persisted = list(session.scalars(select(InspectionDecision)))
        assert len(persisted) == 1
        assert result["inserted"]["reference"] == "376/QD-QLD"
        plan = session.get(InspectionPlan, "a0000000-0000-0000-0000-000000000011")
        assert (plan.decision_reference, plan.decision_date, plan.decision_legacy_raw) == (
            "376/QD-QLD", date(2016, 8, 29), "376/QD-QLD ngày 29/08/2016;"
        )
        with pytest.raises(apply.ApplyFenceError, match="action set differs"):
            apply.guarded_apply(session, snapshot, topology_evidence=topology, approved_plan=approved)
        assert len(list(session.scalars(select(InspectionDecision)))) == 1
    finally:
        session.close()
        engine.dispose()


def test_existing_conflict_and_owner_drift_fail_before_insert(monkeypatch):
    engine, session = _session()
    try:
        snapshot, digest = _snapshot()
        approved, topology = _approved(session, snapshot, digest, monkeypatch)
        session.rollback()
        session.add(InspectionDecision(
            inspection_plan_id="a0000000-0000-0000-0000-000000000011", ordinal=1, reference="conflict",
            decision_on=date(2016, 8, 29), legacy_raw="conflict",
        ))
        session.commit()
        with pytest.raises(apply.ApplyFenceError, match="hard semantic conflicts"):
            apply.guarded_apply(session, snapshot, topology_evidence=topology, approved_plan=approved)
        assert len(list(session.scalars(select(InspectionDecision)))) == 1
        session.rollback()
        session.delete(session.get(InspectionDecision, session.scalar(select(InspectionDecision.id))))
        session.commit()
        changed = {**approved, "actions": [{**approved["actions"][0], "inspection_plan_id": "wrong"}]}
        with pytest.raises(apply.ApplyFenceError, match="InspectionPlan owner"):
            apply.guarded_apply(session, snapshot, topology_evidence=topology, approved_plan=changed)
    finally:
        session.close()
        engine.dispose()


def test_guarded_apply_rolls_back_on_injected_failure(monkeypatch):
    engine, session = _session()
    try:
        snapshot, digest = _snapshot()
        approved, topology = _approved(session, snapshot, digest, monkeypatch)
        session.rollback()
        try:
            with session.begin():
                apply.guarded_apply(session, snapshot, topology_evidence=topology, approved_plan=approved)
                raise RuntimeError("injected failure")
        except RuntimeError:
            pass
        assert session.scalar(select(InspectionDecision.id).limit(1)) is None
    finally:
        session.close()
        engine.dispose()


def test_changed_topology_or_approved_action_set_aborts_before_any_write(monkeypatch):
    engine, session = _session()
    try:
        snapshot, digest = _snapshot()
        approved, topology = _approved(session, snapshot, digest, monkeypatch)
        session.rollback()
        changed_topology = {**topology, "case_count": 2}
        with pytest.raises(reconciliation.ReconciliationFenceError, match="topology"):
            apply.guarded_apply(session, snapshot, topology_evidence=changed_topology, approved_plan=approved)
        assert session.scalar(select(InspectionDecision.id).limit(1)) is None
        session.rollback()
        changed_plan = {**approved, "actions": [{**approved["actions"][0], "source_ordinal": 2}]}
        with pytest.raises(apply.ApplyFenceError, match="action set differs"):
            apply.guarded_apply(session, snapshot, topology_evidence=topology, approved_plan=changed_plan)
        assert session.scalar(select(InspectionDecision.id).limit(1)) is None
    finally:
        session.close()
        engine.dispose()


def test_target_owners_are_locked_before_fresh_semantic_authorization(monkeypatch):
    engine, session = _session()
    try:
        snapshot, digest = _snapshot()
        approved, topology = _approved(session, snapshot, digest, monkeypatch)
        session.rollback()
        locked = {"value": False}
        original = apply._lock_approved_owners

        def lock_then_mark(*args, **kwargs):
            result = original(*args, **kwargs)
            locked["value"] = True
            return result

        original_fresh = apply.fresh_preflight

        def fresh_after_lock(*args, **kwargs):
            assert locked["value"] is True
            return original_fresh(*args, **kwargs)

        monkeypatch.setattr(apply, "_lock_approved_owners", lock_then_mark)
        monkeypatch.setattr(apply, "fresh_preflight", fresh_after_lock)
        with session.begin():
            apply.guarded_apply(session, snapshot, topology_evidence=topology, approved_plan=approved)
        assert session.scalar(select(InspectionDecision.id).limit(1)) is not None
    finally:
        session.close()
        engine.dispose()


def _post_apply_report(*, data_apply_count=0, hard_conflicts=0, minutes_excel=1149) -> dict[str, object]:
    zero = {
        "MISSING_IN_DB": 0, "EXTRA_IN_DB": 0, "FIELD_MISMATCH": 0,
        "OWNER_MISMATCH": 0, "RELATION_MISMATCH": 0,
        "CANONICAL_CASE_MISSING": 0, "UNEXPECTED_OWNER_MISSING": 0,
    }
    return {
        "owners": {"case_universe": {"case_universe_status": "PASS"}, "owner_integrity": {"status": "PASS"}},
        "reconciliation_outcome": {
            "status": "INCOMPLETE_EVIDENCE",
            "data_apply_required": {"count": data_apply_count},
            "hard_semantic_conflicts": {"count": hard_conflicts},
        },
        "dry_run_apply_plan": {"actions": []},
        "decisions": {"expected_structured_count": 1220, "existing_structured_count": 1220, "classification_counts": dict(zero)},
        "minutes": {
            "expected_structured_count": 1162, "existing_structured_count": 1162,
            "classification_counts": {**zero, "EXCEL_SERIAL_DATE_REPRESENTATION_EQUIVALENT": minutes_excel},
        },
    }


def test_post_apply_validator_accepts_only_incomplete_evidence_without_actions():
    apply.validate_post_apply_reconciliation(_post_apply_report())


def test_production_post_apply_validator_retains_the_exact_rehearsal_terminal_status():
    report = _post_apply_report()
    report["reconciliation_outcome"]["status"] = "PASS_EXACT"
    with pytest.raises(apply.ApplyFenceError, match="outcome status"):
        apply.validate_post_apply_reconciliation(report)
    apply.validate_post_apply_reconciliation_contract(
        report,
        decision_counts=apply.POST_APPLY_DECISION_COUNTS,
        minutes_counts=apply.POST_APPLY_MINUTES_COUNTS,
        expected_outcome_status="PASS_EXACT",
    )


@pytest.mark.parametrize(
    "changed",
    [
        lambda report: report["reconciliation_outcome"]["data_apply_required"].__setitem__("count", 1),
        lambda report: report["reconciliation_outcome"]["hard_semantic_conflicts"].__setitem__("count", 1),
        lambda report: report["decisions"].__setitem__("existing_structured_count", 1219),
        lambda report: report["minutes"]["classification_counts"].__setitem__("FIELD_MISMATCH", 1),
        lambda report: report["minutes"]["classification_counts"].__setitem__("EXCEL_SERIAL_DATE_REPRESENTATION_EQUIVALENT", 0),
    ],
)
def test_post_apply_validator_rejects_remaining_apply_conflicts_or_minutes_regression(changed):
    report = _post_apply_report()
    changed(report)
    with pytest.raises(apply.ApplyFenceError, match="post-apply"):
        apply.validate_post_apply_reconciliation(report)


class _Scalar:
    def __init__(self, value): self.value = value
    def scalar_one(self): return self.value


class _Connection:
    def __init__(self, database, revision): self.database, self.revision = database, revision
    def execute(self, statement):
        sql = str(statement)
        if "current_database" in sql: return _Scalar(self.database)
        if "version_num" in sql: return _Scalar(self.revision)
        raise AssertionError(sql)


def test_postgres_rehearsal_and_exact_revision_fences_remain_fail_closed():
    apply.verify_write_target(_Connection(reconciliation.REHEARSAL_DATABASE, reconciliation.REQUIRED_REVISION))
    with pytest.raises(apply.ApplyFenceError):
        apply.verify_write_target(_Connection("gxp_qlcl", reconciliation.REQUIRED_REVISION))
    with pytest.raises(apply.ApplyFenceError):
        apply.verify_write_target(_Connection(reconciliation.REHEARSAL_DATABASE, "wrong"))
    with pytest.raises(reconciliation.ReconciliationFenceError):
        reconciliation.validate_target_url("sqlite:///unsafe.db")


class _LifecycleEngine:
    def dispose(self):
        pass


class _LifecycleSession:
    def __init__(self, *, commit_error: Exception | None = None):
        self.commit_error = commit_error
        self.rollback_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def connection(self):
        return object()

    def commit(self):
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self):
        self.rollback_count += 1


def _run_main_lifecycle(
    monkeypatch,
    tmp_path,
    *,
    apply_requested: bool,
    guarded_error: Exception | None = None,
    commit_error: Exception | None = None,
    post_error: Exception | None = None,
    verification_error: Exception | None = None,
):
    approved = {"actions": [{"kind": "decisions"}]}
    session = _LifecycleSession(commit_error=commit_error)
    calls = {"run": 0}

    def run(*args, **kwargs):
        calls["run"] += 1
        if calls["run"] == 2 and post_error is not None:
            raise post_error
        return {"pre": calls["run"]}

    def guarded(*args, **kwargs):
        if guarded_error is not None:
            raise guarded_error
        return {"action_fingerprint": "fresh", "inserted": {"id": "decision-1"}}

    monkeypatch.setattr(reconciliation, "validate_target_url", lambda value: None)
    monkeypatch.setattr(reconciliation, "load_verified_snapshot_file", lambda value: {})
    monkeypatch.setattr(reconciliation, "load_verified_topology_file", lambda value, **kwargs: {})
    monkeypatch.setattr(reconciliation, "run", run)
    monkeypatch.setattr(apply, "load_approved_plan", lambda value, **kwargs: approved)
    monkeypatch.setattr(apply, "_validate_fresh_plan", lambda fresh, approved: [])
    monkeypatch.setattr(apply, "verify_write_target", lambda connection: None)
    monkeypatch.setattr(apply, "guarded_apply", guarded)
    monkeypatch.setattr(apply, "create_engine", lambda value, **kwargs: _LifecycleEngine())
    monkeypatch.setattr(apply, "Session", lambda engine: session)
    if verification_error is not None:
        monkeypatch.setattr(apply, "validate_post_apply_reconciliation", lambda report: (_ for _ in ()).throw(verification_error))
    else:
        monkeypatch.setattr(apply, "validate_post_apply_reconciliation", lambda report: None)
    arguments = [
        "--database-url", "postgresql+psycopg://operator:secret@example.invalid/gxp_legacy_rehearsal",
        "--topology-evidence", str(tmp_path / "topology.json"),
        "--expected-topology-sha256", "topology",
        "--approved-action-plan", str(tmp_path / "plan.json"),
        "--expected-approved-action-sha256", "plan",
        "--output-dir", str(tmp_path),
    ]
    if apply_requested:
        arguments.append("--apply")
    exit_code = apply.main(arguments)
    payload = json.loads((tmp_path / "b6b_v2_apply_result.json").read_text(encoding="utf-8"))
    return exit_code, payload, session


def test_main_writes_dry_run_lifecycle_artifact(monkeypatch, tmp_path):
    exit_code, payload, _session = _run_main_lifecycle(monkeypatch, tmp_path, apply_requested=False)
    assert exit_code == 0
    assert payload["status"] == "DRY_RUN_ONLY"
    assert payload["writer_invoked"] is False
    assert payload["transaction_committed"] is False
    assert payload["database_mutated"] is False


def test_main_writes_rollback_lifecycle_artifact_before_commit(monkeypatch, tmp_path):
    exit_code, payload, session = _run_main_lifecycle(
        monkeypatch, tmp_path, apply_requested=True, guarded_error=RuntimeError("before commit")
    )
    assert exit_code == 3
    assert session.rollback_count == 1
    assert payload["status"] == "WRITE_TRANSACTION_ROLLED_BACK"
    assert payload["writer_invoked"] is True
    assert payload["transaction_committed"] is False
    assert payload["database_mutated"] is False


def test_main_commit_error_marks_both_commit_and_mutation_outcomes_unknown(monkeypatch, tmp_path):
    exit_code, payload, _session = _run_main_lifecycle(
        monkeypatch, tmp_path, apply_requested=True, commit_error=RuntimeError("commit transport failure")
    )
    assert exit_code == 3
    assert payload["status"] == "WRITE_TRANSACTION_COMMIT_ERROR_OUTCOME_UNCONFIRMED"
    assert payload["writer_invoked"] is True
    assert payload["transaction_committed"] is None
    assert payload["database_mutated"] is None


def test_main_writes_post_apply_reconciliation_error_artifact(monkeypatch, tmp_path):
    exit_code, payload, _session = _run_main_lifecycle(
        monkeypatch, tmp_path, apply_requested=True, post_error=RuntimeError("post reconciliation unavailable")
    )
    assert exit_code == 4
    assert payload["status"] == "POST_APPLY_RECONCILIATION_ERROR"
    assert payload["transaction_committed"] is True
    assert payload["database_mutated"] is True


def test_main_writes_post_apply_verification_failure_artifact(monkeypatch, tmp_path):
    exit_code, payload, _session = _run_main_lifecycle(
        monkeypatch, tmp_path, apply_requested=True, verification_error=apply.ApplyFenceError("semantic mismatch")
    )
    assert exit_code == 4
    assert payload["status"] == "POST_APPLY_VERIFICATION_FAILED"
    assert payload["transaction_committed"] is True
    assert payload["database_mutated"] is True


def test_main_writes_verified_success_lifecycle_artifact(monkeypatch, tmp_path):
    exit_code, payload, _session = _run_main_lifecycle(monkeypatch, tmp_path, apply_requested=True)
    assert exit_code == 0
    assert payload["status"] == "APPLY_VERIFIED_SUCCESS"
    assert payload["transaction_committed"] is True
    assert payload["database_mutated"] is True
