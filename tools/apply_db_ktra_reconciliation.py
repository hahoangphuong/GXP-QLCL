"""Fail-closed Batch 4 rehearsal apply tool for the approved db.ktra subset.

This tool is intentionally inert without ``--apply-rehearsal``.  It never
parses the workbook and replays every approved source fact from the committed
snapshot before it opens its one write transaction.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import (
    CapaCycle, Case, CaseApplication, CaseAssessment, Certificate,
    CertificateScope, CertificateVersion, InspectionApprovalSubmission,
    InspectionOutcome, InspectionPeriodSegment, InspectionPlan, InspectionTeam,
    InspectionTeamMember,
)
from backend.app.domain.legacy_db_ktra_reconciliation import (
    parse_legacy_date,
    parse_legacy_inspection_decision,
    parse_legacy_minutes_recorded,
    safe_evidence,
)
from backend.app.domain.phase2_import import parse_int
from tools.plan_db_ktra_reconciliation import (
    REHEARSAL_DATABASE,
    REQUIRED_REVISION,
    SNAPSHOT,
    load_snapshot,
    validate_rehearsal_target,
)
from tools.profile_legacy_semantics import CANONICAL_SNAPSHOT_ARTIFACT_SHA256, snapshot_artifact_sha256


PLAN_SCHEMA_VERSION = "db-ktra-reconciliation-plan/v1"
TOOL_VERSION = "db-ktra-reconciliation-apply/v1"
EXPECTED_FACT_COUNTS = {
    "decision_reference": 1220, "decision_date": 1220, "decision_legacy_raw": 1220,
    "minutes_recorded_on": 1150, "minutes_recorded_time": 1150,
    "final_evaluation": 1294, "compliance_due_on": 405,
    "assessment_result_contamination": 764,
    "application_dossier_reference_contamination": 1220,
    "outcome_decision_reference_contamination": 1220,
    "outcome_bbkt_reference_contamination": 1150,
}
SAFE_FACTS = {"decision_reference", "decision_date", "decision_legacy_raw", "minutes_recorded_on", "minutes_recorded_time", "final_evaluation", "compliance_due_on"}
CLEANUP_FACTS = {"assessment_result_contamination", "application_dossier_reference_contamination", "outcome_decision_reference_contamination", "outcome_bbkt_reference_contamination"}


class ApplyFenceError(RuntimeError):
    """A plan, provenance, or live-state fence failed before commit."""


class ApplyExecutionError(ApplyFenceError):
    def __init__(self, message: str, report: dict[str, Any]):
        super().__init__(message)
        self.report = report


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def load_and_validate_plan(path: Path, expected_plan_sha256: str) -> dict[str, Any]:
    actual = _sha(path)
    if actual != expected_plan_sha256.lower():
        raise ApplyFenceError("plan SHA256 fence failed")
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION or plan.get("comparison_status") != "COMPARED":
        raise ApplyFenceError("plan is not a compared db.ktra reconciliation plan")
    connection = plan.get("read_only_connection") or {}
    if connection.get("database") != REHEARSAL_DATABASE or connection.get("revision") != REQUIRED_REVISION or connection.get("transaction_read_only") is not True:
        raise ApplyFenceError("plan rehearsal read-only provenance fence failed")
    return plan


def validate_snapshot_provenance(snapshot: Path) -> list[dict[str, Any]]:
    if snapshot_artifact_sha256(snapshot) != CANONICAL_SNAPSHOT_ARTIFACT_SHA256:
        raise ApplyFenceError("canonical snapshot provenance fence failed")
    return load_snapshot(snapshot)


def _eligible_facts(plan: dict[str, Any]) -> list[dict[str, Any]]:
    eligible = [fact for fact in plan.get("facts", []) if (fact.get("fact") in SAFE_FACTS and fact.get("classification") == "SAFE_DIRECT") or (fact.get("fact") in CLEANUP_FACTS and fact.get("classification") == "CONTAMINATED_EXACT_COPY")]
    counts = Counter(str(fact["fact"]) for fact in eligible)
    if dict(counts) != EXPECTED_FACT_COUNTS:
        raise ApplyFenceError(f"approved write envelope mismatch: {dict(counts)}")
    return eligible


def _source_for_fact(row: dict[str, Any], fact: str) -> dict[str, Any]:
    if fact.startswith("decision") or fact.startswith("application_dossier") or fact.startswith("outcome_decision"):
        return parse_legacy_inspection_decision(row.get("decision_reference"))
    if fact.startswith("minutes") or fact == "outcome_bbkt_reference_contamination":
        return parse_legacy_minutes_recorded(row.get("bbkt_reference"))
    if fact == "final_evaluation":
        raw = str(row.get("ĐÁNH GIÁ CUỐI") or "").strip()
        return {"state": "MISSING" if raw in {"", "-", "???"} else "KNOWN", "value": raw or None, "raw": raw}
    if fact == "compliance_due_on":
        return parse_legacy_date(row.get("HẠN KT TUÂN THỦ"))
    if fact == "assessment_result_contamination":
        raw = str(row.get("assessment_result") or "").strip()
        return {"state": "MISSING" if raw in {"", "-", "???"} else "KNOWN", "value": raw or None, "raw": raw}
    raise ApplyFenceError(f"unsupported candidate fact {fact}")


def _safe_parsed(parsed: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"state": parsed["state"]}
    for key in ("decision_reference", "decision_date", "recorded_on", "recorded_time", "value", "precision", "source_format"):
        value = parsed.get(key)
        if value is not None:
            result[key] = value.isoformat() if hasattr(value, "isoformat") else value
    return result


def validate_source_replay(eligible: list[dict[str, Any]], snapshot_rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    rows = {parse_int(row.get("ID", "")): row for row in snapshot_rows if parse_int(row.get("ID", "")) is not None}
    for fact in eligible:
        legacy_id = fact.get("legacy_case_id")
        row = rows.get(legacy_id)
        if row is None or fact.get("legacy_row") != legacy_id:
            raise ApplyFenceError("plan legacy identity does not exist in canonical snapshot")
        parsed = _source_for_fact(row, str(fact["fact"]))
        if parsed["state"] != fact.get("source_state") or safe_evidence(parsed.get("raw", ""))["source_raw_hash"] != fact.get("source_raw_hash"):
            raise ApplyFenceError(f"source replay mismatch for legacy row {legacy_id}, fact {fact['fact']}")
        planned = fact.get("parsed_value") or {}
        if planned and _safe_parsed(parsed) != planned:
            raise ApplyFenceError(f"parser result mismatch for legacy row {legacy_id}, fact {fact['fact']}")
    return rows


def _require_same_or_empty(current: object, desired: object, label: str) -> bool:
    if current == desired:
        return False
    if current is None:
        return True
    raise ApplyFenceError(f"live canonical conflict at {label}")


def _bump_changed_entities(changed_entities: dict[int, Any], new_entities: set[int]) -> None:
    """Advance optimistic versions only for persisted objects changed by this run."""
    for entity_identity, entity in changed_entities.items():
        if entity_identity not in new_entities and getattr(entity, "row_version", None) is not None:
            entity.row_version += 1


def _safe_error_summary(error: Exception) -> str:
    """Keep operational failure evidence useful without serializing credentials."""
    summary = str(error)
    summary = re.sub(r"(?i)(password|pwd)=([^\s&;]+)", r"\1=[REDACTED]", summary)
    return re.sub(r"(://)[^/@\s]+@", r"\1[REDACTED]@", summary)


def _lock_one(session: Session, model: Any, case_id: str) -> Any | None:
    return session.scalars(select(model).where(model.case_id == case_id).with_for_update()).first()


def _operation_groups(eligible: list[dict[str, Any]]) -> dict[int, dict[str, dict[str, Any]]]:
    grouped: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    for fact in eligible:
        grouped[int(fact["legacy_case_id"])][str(fact["fact"])] = fact
    return grouped


def _protected_counts(session: Session) -> dict[str, int]:
    """Capture excluded-table cardinalities without retaining business prose."""
    if hasattr(session, "protected_counts"):
        return dict(session.protected_counts())
    return {
        "inspection_period_segments": session.scalar(select(func.count()).select_from(InspectionPeriodSegment)),
        "inspection_teams": session.scalar(select(func.count()).select_from(InspectionTeam)),
        "inspection_team_members": session.scalar(select(func.count()).select_from(InspectionTeamMember)),
        "approval_submissions": session.scalar(select(func.count()).select_from(InspectionApprovalSubmission)),
        "certificates": session.scalar(select(func.count()).select_from(Certificate)),
        "certificate_versions": session.scalar(select(func.count()).select_from(CertificateVersion)),
        "certificate_scopes": session.scalar(select(func.count()).select_from(CertificateScope)),
        "capa_cycles": session.scalar(select(func.count()).select_from(CapaCycle)),
    }


def _protected_evidence(cases: list[Any], outcomes: list[Any], counts: dict[str, int]) -> dict[str, Any]:
    return {
        "case_states": {case.id: str(case.state) for case in cases},
        "outcome_period_fields": {outcome.id: (outcome.inspected_on, outcome.inspected_to_on, outcome.inspection_period_state) for outcome in outcomes if outcome is not None},
        "counts": counts,
    }


def _verify_protected_state(before: dict[str, Any], cases: list[Any], outcomes: list[Any], after_counts: dict[str, int]) -> dict[str, Any]:
    after = _protected_evidence(cases, outcomes, after_counts)
    if before != after:
        raise ApplyFenceError("protected Batch 4 state changed unexpectedly")
    return {
        "inspection_period_segments_before": before["counts"]["inspection_period_segments"],
        "inspection_period_segments_after": after_counts["inspection_period_segments"],
        "protected_outcome_fields_verified": len(before["outcome_period_fields"]),
        "case_state_verified": len(before["case_states"]),
        **{f"{key}_before": value for key, value in before["counts"].items() if key != "inspection_period_segments"},
        **{f"{key}_after": value for key, value in after_counts.items() if key != "inspection_period_segments"},
    }


def preflight_and_apply(session: Session, plan: dict[str, Any], snapshot_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Preflight every candidate, then mutate only after all fences pass.

    Caller owns the transaction. Any exception rolls the complete operation back.
    """
    eligible = _eligible_facts(plan)
    rows = validate_source_replay(eligible, snapshot_rows)
    groups = _operation_groups(eligible)
    operations: list[tuple[Any, str, object]] = []
    changed_entities: dict[int, Any] = {}
    new_entities: set[int] = set()
    locked_cases: list[Any] = []
    locked_outcomes: list[Any] = []
    already = Counter()
    for legacy_id, facts in groups.items():
        case = session.scalars(select(Case).where(Case.legacy_inspection_id == legacy_id).with_for_update()).first()
        if case is None:
            raise ApplyFenceError(f"missing canonical case for legacy ID {legacy_id}")
        locked_cases.append(case)
        row = rows[legacy_id]
        decision = parse_legacy_inspection_decision(row.get("decision_reference"))
        minutes = parse_legacy_minutes_recorded(row.get("bbkt_reference"))
        outcome = _lock_one(session, InspectionOutcome, case.id)
        if outcome is not None:
            locked_outcomes.append(outcome)
        application = _lock_one(session, CaseApplication, case.id)
        assessment = _lock_one(session, CaseAssessment, case.id)
        plan_row = _lock_one(session, InspectionPlan, case.id)
        if any(name.startswith("decision_") for name in facts):
            if plan_row is None:
                plan_row = InspectionPlan(case_id=case.id)
                session.add(plan_row)
                new_entities.add(id(plan_row))
            for field, desired in (("decision_reference", decision["decision_reference"]), ("decision_date", decision["decision_date"]), ("decision_legacy_raw", decision["raw"])):
                if field not in facts:
                    raise ApplyFenceError("incomplete decision owner-move plan")
                if _require_same_or_empty(getattr(plan_row, field), desired, f"InspectionPlan.{field}"):
                    operations.append((plan_row, field, desired))
                else:
                    already[field] += 1
            for model, field, fact_name in ((application, "dossier_reference", "application_dossier_reference_contamination"), (outcome, "decision_reference", "outcome_decision_reference_contamination")):
                if fact_name not in facts or model is None:
                    raise ApplyFenceError("incomplete decision cleanup plan")
                if getattr(model, field) == decision["raw"]:
                    operations.append((model, field, None))
                elif getattr(model, field) is None:
                    already[fact_name] += 1
                else:
                    raise ApplyFenceError(f"live canonical conflict at {fact_name}")
        if any(name.startswith("minutes_") or name == "outcome_bbkt_reference_contamination" for name in facts):
            if outcome is None or not {"minutes_recorded_on", "minutes_recorded_time", "outcome_bbkt_reference_contamination"} <= set(facts):
                raise ApplyFenceError("incomplete minutes owner-move plan")
            for field, desired in (("minutes_recorded_on", minutes["recorded_on"]), ("minutes_recorded_time", minutes["recorded_time"]), ("minutes_legacy_raw", minutes["raw"])):
                if _require_same_or_empty(getattr(outcome, field), desired, f"InspectionOutcome.{field}"):
                    operations.append((outcome, field, desired))
                else:
                    already[field] += 1
            if outcome.bbkt_reference == minutes["raw"]:
                operations.append((outcome, "bbkt_reference", None))
            elif outcome.bbkt_reference is None:
                already["outcome_bbkt_reference_contamination"] += 1
            else:
                raise ApplyFenceError("live canonical conflict at outcome_bbkt_reference_contamination")
        if "final_evaluation" in facts:
            if outcome is None:
                raise ApplyFenceError("missing InspectionOutcome for final evaluation")
            parsed = _source_for_fact(row, "final_evaluation")
            if _require_same_or_empty(outcome.final_evaluation, parsed["value"], "InspectionOutcome.final_evaluation"):
                operations.append((outcome, "final_evaluation", parsed["value"]))
            else:
                already["final_evaluation"] += 1
        if "compliance_due_on" in facts:
            if outcome is None:
                raise ApplyFenceError("missing InspectionOutcome for compliance due date")
            parsed = _source_for_fact(row, "compliance_due_on")
            if _require_same_or_empty(outcome.compliance_due_on, parsed["value"], "InspectionOutcome.compliance_due_on"):
                operations.append((outcome, "compliance_due_on", parsed["value"]))
            else:
                already["compliance_due_on"] += 1
        if "assessment_result_contamination" in facts:
            if outcome is None or assessment is None:
                raise ApplyFenceError("missing outcome or assessment for Kết quả cleanup")
            parsed = _source_for_fact(row, "assessment_result_contamination")
            if outcome.outcome_result != parsed["value"]:
                raise ApplyFenceError("outcome result drift blocks assessment cleanup")
            if assessment.assessment_result == parsed["value"]:
                operations.append((assessment, "assessment_result", None))
            elif assessment.assessment_result is None:
                already["assessment_result_contamination"] += 1
            else:
                raise ApplyFenceError("assessment result drift blocks cleanup")
    protected_before = _protected_evidence(locked_cases, locked_outcomes, _protected_counts(session))
    for entity, field, value in operations:
        setattr(entity, field, value)
        changed_entities[id(entity)] = entity
    _bump_changed_entities(changed_entities, new_entities)
    session.flush()
    protected_state = _verify_protected_state(protected_before, locked_cases, locked_outcomes, _protected_counts(session))
    operation_counts = dict(Counter(field for _entity, field, _value in operations))
    return {"operation_counts": operation_counts, "rows_already_applied": dict(already), "entities_changed": len(changed_entities), "precondition_conflicts": [], "before_after_aggregate_counts": {"planned_field_changes": len(operations), "applied_field_changes": len(operations), "already_applied_fields": sum(already.values())}, "protected_state": protected_state}


def _verify_live_target(connection: Any) -> None:
    if connection.execute(text("SELECT current_database()")).scalar_one() != REHEARSAL_DATABASE:
        raise ApplyFenceError("unsafe live database")
    if connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != REQUIRED_REVISION:
        raise ApplyFenceError("unexpected Alembic revision")


def run_apply(database_url: str, plan: dict[str, Any], snapshot_rows: list[dict[str, Any]], *, dry_run: bool) -> dict[str, Any]:
    validate_rehearsal_target(database_url)
    engine = create_engine(database_url)
    started = datetime.now(timezone.utc)
    connection = None
    transaction = None
    try:
        connection = engine.connect()
        transaction = connection.begin()
        _verify_live_target(connection)
        session = Session(bind=connection, autoflush=False, expire_on_commit=False)
        try:
            report = preflight_and_apply(session, plan, snapshot_rows)
        finally:
            session.close()
        if dry_run:
            transaction.rollback()
            committed = False
        else:
            transaction.commit()
            committed = True
        return {**report, "database": REHEARSAL_DATABASE, "revision": REQUIRED_REVISION, "dry_run": dry_run, "transaction_committed": committed, "transaction_rolled_back": dry_run, "started_at": started.isoformat(), "completed_at": datetime.now(timezone.utc).isoformat()}
    except Exception as error:
        if transaction is not None and transaction.is_active:
            transaction.rollback()
        raise ApplyExecutionError(
            _safe_error_summary(error),
            {
                "database": REHEARSAL_DATABASE,
                "revision": REQUIRED_REVISION,
                "transaction_committed": False,
                "transaction_rolled_back": transaction is not None,
                "failure_stage": "live_transaction",
            },
        ) from error
    finally:
        if connection is not None:
            connection.close()
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply the audited db.ktra rehearsal subset only after explicit approval.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply-rehearsal", action="store_true")
    mode.add_argument("--dry-run-rehearsal", action="store_true")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args(argv)
    started = datetime.now(timezone.utc)
    base_report: dict[str, Any] = {
        "tool_version": TOOL_VERSION,
        "source_git_sha": _git_sha(),
        "snapshot_provenance_sha256": CANONICAL_SNAPSHOT_ARTIFACT_SHA256,
        "plan_validated": False,
        "dry_run": args.dry_run_rehearsal,
        "transaction_committed": False,
        "transaction_rolled_back": False,
        "started_at": started.isoformat(),
    }
    try:
        if not args.apply_rehearsal and not args.dry_run_rehearsal:
            raise ApplyFenceError("refusing to run without --apply-rehearsal or --dry-run-rehearsal")
        plan_path = args.plan.resolve()
        base_report["plan_sha256"] = _sha(plan_path)
        plan = load_and_validate_plan(plan_path, args.expected_plan_sha256)
        base_report["plan_validated"] = True
        snapshot_rows = validate_snapshot_provenance(args.snapshot.resolve())
        database_url = os.environ.get(args.database_url_env)
        if not database_url:
            raise ApplyFenceError(f"missing database URL environment variable {args.database_url_env}")
        eligible = _eligible_facts(plan)
        excluded = Counter(str(fact.get("classification")) for fact in plan.get("facts", []) if fact not in eligible)
        report = {**base_report, "excluded_domains": ["InspectionTeam", "InspectionTeamMember", "InspectionApprovalSubmission", "Certificate", "CapaCycle", "InspectionPeriodSegment"], "excluded_classification_counts": dict(excluded), **run_apply(database_url, plan, snapshot_rows, dry_run=args.dry_run_rehearsal)}
        _write_report(args.report_output, report)
        return 0
    except Exception as error:
        execution_report = getattr(error, "report", {})
        report = {**base_report, **execution_report, "completed_at": datetime.now(timezone.utc).isoformat(), "failure_stage": execution_report.get("failure_stage", "validation"), "failure_type": type(error).__name__, "error_summary": _safe_error_summary(error), "precondition_conflicts": execution_report.get("precondition_conflicts", []), "operation_counts": execution_report.get("operation_counts", {}), "transaction_committed": False}
        _write_report(args.report_output, report)
        raise


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.resolve().parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
