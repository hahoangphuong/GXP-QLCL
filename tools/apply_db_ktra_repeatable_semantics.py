"""Guarded Batch 6 apply for already-audited repeatable source occurrences.

The rehearsal plan deliberately contains safe evidence rather than legacy prose.
This tool replays each candidate against the canonical snapshot before it can
write the exact occurrence raw text into the two structured owner tables.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import Case, InspectionDecision, InspectionMinutesRecord, InspectionOutcome, InspectionPlan
from backend.app.domain.legacy_db_ktra_reconciliation import parse_legacy_inspection_decisions, parse_legacy_minutes_records, safe_evidence
from backend.app.domain.phase2_import import parse_int
from tools.plan_db_ktra_reconciliation import SNAPSHOT, load_snapshot


REHEARSAL_DATABASE = "gxp_legacy_rehearsal"
REQUIRED_REVISION = "20260913_0013"
PLAN_SCHEMA_VERSION = "db-ktra-repeatable-semantics-plan/v1"
REPORT_SCHEMA_VERSION = "batch6-repeatable-apply-report/v1"
CANONICAL_SNAPSHOT_SHA256 = "b3bde05963e4e4d14d5b244e7c62b0f810f1cbbe206750574def6a366bdf7296"
EXPECTED_COUNTS = {"decisions": 1219, "minutes": 1162, "canonical_gaps": 37, "source_replaces": 2, "writable_replaces": 0}
COMPATIBILITY_STATES = (
    "MATCH_SINGLETON",
    "MISSING_SINGLETON",
    "CONFLICT_SINGLETON",
    "NULL_OK_MULTIPLE",
    "SHOULD_BE_NULL_MULTIPLE",
    "NO_STRUCTURED_SOURCE",
)
BBKT_REFERENCE_EVIDENCE_STATES = (
    "CLEARED_OR_ABSENT",
    "MATCHES_SOURCE_RAW",
    "CONFLICTS_SOURCE_RAW",
    "MULTIPLE_STRUCTURED_SOURCE",
    "NO_STRUCTURED_SOURCE",
)


class ApplyFenceError(RuntimeError):
    """Raised when an input, owner, or idempotency fence fails closed."""


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _safe_error_summary(error: Exception) -> str:
    summary = str(error)
    summary = re.sub(r"(?i)(password|pwd)=([^\s&;]+)", r"\1=[REDACTED]", summary)
    return re.sub(r"(://)[^/@\s]+@", r"\1[REDACTED]@", summary)


def _iso(value: object) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value if isinstance(value, str) else None


def _date(value: object) -> Any:
    from datetime import date

    if not isinstance(value, str):
        raise ApplyFenceError("planned date must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ApplyFenceError("planned date is invalid") from exc


def _time(value: object) -> Any:
    from datetime import time

    if value is None:
        return None
    if not isinstance(value, str):
        raise ApplyFenceError("planned time must be an ISO time string")
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise ApplyFenceError("planned time is invalid") from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ApplyFenceError(message)


def _valid_source_rows(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for row in rows:
        legacy_id = parse_int(row.get("ID", ""))
        if legacy_id is None:
            continue
        if legacy_id in indexed:
            raise ApplyFenceError("canonical snapshot has duplicate valid legacy inspection ID")
        indexed[legacy_id] = row
    return indexed


def _candidate_lists(plan: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = plan.get("write_candidates")
    _require(isinstance(candidates, dict), "plan write_candidates must be an object")
    decisions = candidates.get("decisions")
    minutes = candidates.get("minutes")
    _require(isinstance(decisions, list) and isinstance(minutes, list), "plan candidate lists are missing")
    return decisions, minutes


def _source_replaces(plan: dict[str, Any], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source = plan.get("decisions")
    _require(isinstance(source, dict), "plan decision source inventory is missing")
    records = source.get("classification_records")
    _require(isinstance(records, list), "plan decision classification records are missing")
    relations = [item for item in records if isinstance(item, dict) and item.get("relation_type") == "REPLACES"]
    _require(source.get("explicit_replaces_relations") == EXPECTED_COUNTS["source_replaces"], "source replacement count is unexpected")
    _require(len(relations) == EXPECTED_COUNTS["source_replaces"], "source replacement records are incomplete")
    writable_keys = {(item.get("legacy_inspection_id"), item.get("source_ordinal")) for item in decisions}
    classifications = Counter()
    for item in relations:
        _require(item.get("classification") != "WRITE_CANDIDATE", "blocked source replacement entered write candidates")
        _require(item.get("inspection_plan_id") is None, "blocked source replacement has an unexpected InspectionPlan")
        _require((item.get("legacy_inspection_id"), item.get("source_ordinal")) not in writable_keys, "source replacement overlaps a write candidate")
        classifications[str(item.get("classification"))] += 1
    _require(dict(classifications) == {"BLOCKED_NO_INSPECTION_PLAN": EXPECTED_COUNTS["source_replaces"]}, "blocked source replacement classification is unexpected")
    return relations


def validate_plan(plan: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _require(plan.get("schema_version") == PLAN_SCHEMA_VERSION, "unexpected repeatable plan schema version")
    guardrails = plan.get("guardrails")
    _require(isinstance(guardrails, dict), "plan guardrails are missing")
    for key, expected in {
        "database_mutated": False,
        "fuzzy_matching_used": False,
        "importer_invoked": False,
        "apply_tool_present": False,
        "transaction_read_only": True,
    }.items():
        _require(guardrails.get(key) is expected, f"plan guardrail {key} failed")
    gaps = plan.get("canonical_gaps")
    _require(isinstance(gaps, dict), "plan canonical gaps are missing")
    _require(gaps.get("classification") == "NO_AUTO_CREATE", "canonical gap classification is unsafe")
    _require(gaps.get("count") == EXPECTED_COUNTS["canonical_gaps"], "canonical gap count is unexpected")
    _require(gaps.get("write_candidates") == 0, "canonical gaps must never be write candidates")
    compliance = plan.get("compliance")
    _require(isinstance(compliance, dict) and compliance.get("write_candidates") == 0, "compliance writes are forbidden")
    decisions, minutes = _candidate_lists(plan)
    _require(len(decisions) == EXPECTED_COUNTS["decisions"], "decision candidate count is unexpected")
    _require(len(minutes) == EXPECTED_COUNTS["minutes"], "minutes candidate count is unexpected")
    _source_replaces(plan, decisions)
    gap_ids = gaps.get("legacy_inspection_ids")
    _require(isinstance(gap_ids, list) and all(isinstance(item, int) for item in gap_ids), "canonical gap identifiers are invalid")
    for name, items, owner_key in (("decision", decisions, "inspection_plan_id"), ("minutes", minutes, "inspection_outcome_id")):
        keys: set[tuple[str, int]] = set()
        for item in items:
            _require(isinstance(item, dict) and item.get("classification") == "WRITE_CANDIDATE", f"{name} candidate is not write eligible")
            legacy_id = item.get("legacy_inspection_id")
            ordinal = item.get("source_ordinal")
            owner = item.get(owner_key)
            _require(isinstance(item.get("canonical_case_id"), str) and item["canonical_case_id"], f"{name} candidate has no canonical Case")
            _require(isinstance(legacy_id, int) and legacy_id > 0, f"{name} candidate has invalid legacy ID")
            _require(isinstance(ordinal, int) and ordinal > 0, f"{name} candidate has invalid source ordinal")
            _require(isinstance(owner, str) and owner, f"{name} candidate has no owner")
            _require(legacy_id not in gap_ids, f"canonical gap {legacy_id} entered write candidates")
            key = (owner, ordinal)
            _require(key not in keys, f"duplicate {name} business key")
            keys.add(key)
    _require(sum(item.get("relation_type") == "REPLACES" for item in decisions) == EXPECTED_COUNTS["writable_replaces"], "unexpected writable replacement relation count")
    return decisions, minutes


def load_inputs(snapshot: Path, expected_snapshot_sha256: str, plan_path: Path, expected_plan_sha256: str) -> tuple[dict[str, Any], list[dict[str, Any]], str, str]:
    snapshot_sha = _sha256(snapshot)
    _require(snapshot_sha == CANONICAL_SNAPSHOT_SHA256, "canonical snapshot byte SHA256 fence failed")
    _require(snapshot_sha == expected_snapshot_sha256.lower(), "provided snapshot SHA256 fence failed")
    plan_sha = _sha256(plan_path)
    _require(plan_sha == expected_plan_sha256.lower(), "plan SHA256 fence failed")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    validate_plan(plan)
    return plan, load_snapshot(snapshot), snapshot_sha, plan_sha


def _source_occurrence(candidate: dict[str, Any], source_rows: dict[int, dict[str, Any]], *, kind: str) -> dict[str, Any]:
    legacy_id = candidate["legacy_inspection_id"]
    row = source_rows.get(legacy_id)
    _require(row is not None, "candidate legacy identity does not exist in canonical snapshot")
    parsed = parse_legacy_inspection_decisions(row.get("decision_reference")) if kind == "decision" else parse_legacy_minutes_records(row.get("bbkt_reference"))
    _require(parsed["state"] == "KNOWN", "candidate source is no longer deterministically structured")
    occurrences = parsed["occurrences"]
    ordinal = candidate["source_ordinal"]
    _require(ordinal <= len(occurrences), "candidate source ordinal does not exist")
    occurrence = occurrences[ordinal - 1]
    expected = safe_evidence(occurrence["legacy_raw"])
    for key, value in expected.items():
        _require(candidate.get(key) == value, "candidate source evidence does not match canonical snapshot")
    fields = ("reference", "decision_on", "relation_type", "replaces_source_reference") if kind == "decision" else ("recorded_on", "recorded_time", "precision", "source_format")
    for field in fields:
        _require(_iso(candidate.get(field)) == _iso(occurrence.get(field)), f"candidate {kind} semantic field {field} does not match source")
    return occurrence


def prepare_candidates(plan: dict[str, Any], snapshot_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    decisions, minutes = _candidate_lists(plan)
    source_rows = _valid_source_rows(snapshot_rows)
    prepared: list[list[dict[str, Any]]] = [[], []]
    for destination, candidates, kind in zip(prepared, (decisions, minutes), ("decision", "minutes"), strict=True):
        for candidate in candidates:
            occurrence = _source_occurrence(candidate, source_rows, kind=kind)
            destination.append({**candidate, "legacy_raw": occurrence["legacy_raw"]})
    return prepared[0], prepared[1]


def _require_postgres_rehearsal(database_url: str) -> None:
    parsed = urlsplit(database_url)
    _require(parsed.scheme.startswith("postgresql"), "apply requires an explicit PostgreSQL URL")
    _require(parsed.path.rsplit("/", 1)[-1] == REHEARSAL_DATABASE, "apply refuses a database other than gxp_legacy_rehearsal")


def _verify_target(connection: Any) -> None:
    _require(connection.execute(text("SELECT current_database()")).scalar_one() == REHEARSAL_DATABASE, "connected database is unsafe")
    _require(connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REQUIRED_REVISION, "unexpected Alembic revision")
    for table in ("inspection_decision", "inspection_minutes_record"):
        _require(connection.execute(text("SELECT to_regclass(:table)"), {"table": table}).scalar_one() is not None, f"required table {table} is missing")


def _one(session: Session, statement: Any, message: str) -> Any:
    values = list(session.scalars(statement))
    _require(len(values) == 1, message)
    return values[0]


def _match_or_conflict(existing: Any | None, desired: dict[str, Any], fields: tuple[str, ...]) -> str:
    if existing is None:
        return "INSERT"
    for field in fields:
        if getattr(existing, field) != desired[field]:
            raise ApplyFenceError("existing structured row conflicts with audited candidate")
    return "NOOP_IDENTICAL"


def preflight(session: Session, decisions: list[dict[str, Any]], minutes: list[dict[str, Any]], *, snapshot_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Resolve exact owners and classify every key before creating any rows."""
    prepared_decisions: list[dict[str, Any]] = []
    prepared_minutes: list[dict[str, Any]] = []
    actions = {"decisions": Counter(), "minutes": Counter(), "relations": Counter()}
    for candidate in decisions:
        case = _one(session, select(Case).where(Case.legacy_inspection_id == candidate["legacy_inspection_id"]).with_for_update(), "candidate canonical Case ownership mismatch")
        _require(case.id == candidate["canonical_case_id"], "candidate canonical Case ID mismatch")
        plan = _one(session, select(InspectionPlan).where(InspectionPlan.case_id == case.id).with_for_update(), "candidate InspectionPlan ownership mismatch")
        _require(plan.id == candidate["inspection_plan_id"], "candidate InspectionPlan ID mismatch")
        desired = {"inspection_plan_id": plan.id, "ordinal": candidate["source_ordinal"], "reference": candidate["reference"], "decision_on": _date(candidate["decision_on"]), "legacy_raw": candidate["legacy_raw"]}
        existing = session.scalars(select(InspectionDecision).where(InspectionDecision.inspection_plan_id == plan.id, InspectionDecision.ordinal == desired["ordinal"]).with_for_update()).first()
        action = _match_or_conflict(existing, desired, ("inspection_plan_id", "ordinal", "reference", "decision_on", "legacy_raw"))
        actions["decisions"][action] += 1
        prepared_decisions.append({"candidate": candidate, "desired": desired, "existing": existing, "action": action})
    for candidate in minutes:
        case = _one(session, select(Case).where(Case.legacy_inspection_id == candidate["legacy_inspection_id"]).with_for_update(), "candidate canonical Case ownership mismatch")
        _require(case.id == candidate["canonical_case_id"], "candidate canonical Case ID mismatch")
        outcome = _one(session, select(InspectionOutcome).where(InspectionOutcome.case_id == case.id).with_for_update(), "candidate InspectionOutcome ownership mismatch")
        _require(outcome.id == candidate["inspection_outcome_id"], "candidate InspectionOutcome ID mismatch")
        desired = {"inspection_outcome_id": outcome.id, "ordinal": candidate["source_ordinal"], "recorded_on": _date(candidate["recorded_on"]), "recorded_time": _time(candidate.get("recorded_time")), "precision": candidate["precision"], "source_format": candidate["source_format"], "legacy_raw": candidate["legacy_raw"]}
        existing = session.scalars(select(InspectionMinutesRecord).where(InspectionMinutesRecord.inspection_outcome_id == outcome.id, InspectionMinutesRecord.ordinal == desired["ordinal"]).with_for_update()).first()
        action = _match_or_conflict(existing, desired, ("inspection_outcome_id", "ordinal", "recorded_on", "recorded_time", "precision", "source_format", "legacy_raw"))
        actions["minutes"][action] += 1
        prepared_minutes.append({"candidate": candidate, "desired": desired, "existing": existing, "action": action})
    _preflight_replacements(prepared_decisions, actions["relations"])
    compatibility = _compatibility_audit(session, snapshot_rows or [])
    return {"decisions": prepared_decisions, "minutes": prepared_minutes, "actions": actions, "compatibility": compatibility}


def _preflight_replacements(decisions: list[dict[str, Any]], actions: Counter[str]) -> None:
    """Resolve relation evidence before any insert, never from chronology."""
    by_plan_reference: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in decisions:
        by_plan_reference[(item["desired"]["inspection_plan_id"], item["desired"]["reference"])].append(item)
    for item in decisions:
        candidate = item["candidate"]
        relation = candidate.get("relation_type")
        existing = item["existing"]
        if relation is None:
            _require(existing is None or (existing.relation_type is None and existing.related_decision_id is None), "existing decision relation conflicts with source")
            continue
        _require(relation == "REPLACES", "unsupported decision relation")
        target_reference = candidate.get("replaces_source_reference")
        _require(isinstance(target_reference, str) and target_reference, "replacement target evidence is missing")
        targets = by_plan_reference[(item["desired"]["inspection_plan_id"], target_reference)]
        _require(len(targets) == 1 and targets[0] is not item, "replacement target is not exactly one decision in the same plan")
        target = targets[0]
        if item["action"] == "NOOP_IDENTICAL":
            _require(target["existing"] is not None and existing.relation_type == "REPLACES" and existing.related_decision_id == target["existing"].id, "existing decision replacement relation conflicts")
            actions["NOOP_IDENTICAL"] += 1
        else:
            item["replacement_target"] = target
            actions["LINK"] += 1


def _compatibility_state(occurrences: list[dict[str, Any]], current: tuple[Any, ...], expected: tuple[Any, ...]) -> str:
    if not occurrences:
        return "NO_STRUCTURED_SOURCE"
    if len(occurrences) > 1:
        return "NULL_OK_MULTIPLE" if all(value is None for value in current) else "SHOULD_BE_NULL_MULTIPLE"
    if current == expected:
        return "MATCH_SINGLETON"
    return "MISSING_SINGLETON" if all(value is None for value in current) else "CONFLICT_SINGLETON"


def _bbkt_reference_evidence_state(occurrences: list[dict[str, Any]], bbkt_reference: str | None) -> str:
    """Report retained B. ban evidence separately from typed minutes projection."""
    if not occurrences:
        return "NO_STRUCTURED_SOURCE"
    if len(occurrences) > 1:
        return "MULTIPLE_STRUCTURED_SOURCE"
    if bbkt_reference is None:
        return "CLEARED_OR_ABSENT"
    return "MATCHES_SOURCE_RAW" if bbkt_reference == occurrences[0]["legacy_raw"] else "CONFLICTS_SOURCE_RAW"


def _compatibility_summary(states: Counter[str], *, bbkt_reference_evidence: Counter[str] | None = None) -> dict[str, Any]:
    summary: dict[str, Any] = {"total": sum(states.values()), "by_state": {state: states.get(state, 0) for state in COMPATIBILITY_STATES}}
    if bbkt_reference_evidence is not None:
        summary["bbkt_reference_evidence"] = {
            state: bbkt_reference_evidence.get(state, 0)
            for state in BBKT_REFERENCE_EVIDENCE_STATES
        }
    return summary


def _compatibility_audit(session: Session, snapshot_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Audit scalar projections from source facts without mutating any owner."""
    rows = _valid_source_rows(snapshot_rows)
    plans = {item.case_id: item for item in session.scalars(select(InspectionPlan))}
    outcomes = {item.case_id: item for item in session.scalars(select(InspectionOutcome))}
    decision_states: Counter[str] = Counter()
    minutes_states: Counter[str] = Counter()
    bbkt_reference_evidence: Counter[str] = Counter()
    for case in session.scalars(select(Case).where(Case.legacy_inspection_id.is_not(None))):
        row = rows.get(case.legacy_inspection_id)
        if case.id in plans:
            parsed = parse_legacy_inspection_decisions(None if row is None else row.get("decision_reference"))
            occurrences = parsed["occurrences"] if parsed["state"] == "KNOWN" else []
            owner = plans[case.id]
            expected = (None, None, None) if not occurrences else (occurrences[0]["reference"], occurrences[0]["decision_on"], occurrences[0]["legacy_raw"])
            decision_states[_compatibility_state(occurrences, (owner.decision_reference, owner.decision_date, owner.decision_legacy_raw), expected)] += 1
        if case.id in outcomes:
            parsed = parse_legacy_minutes_records(None if row is None else row.get("bbkt_reference"))
            occurrences = parsed["occurrences"] if parsed["state"] == "KNOWN" else []
            owner = outcomes[case.id]
            # bbkt_reference remains raw legacy evidence; it is never promoted
            # into a timing field by this audit or by the structured apply.
            expected = (None, None, None) if not occurrences else (occurrences[0]["recorded_on"], occurrences[0]["recorded_time"], occurrences[0]["legacy_raw"])
            minutes_states[_compatibility_state(occurrences, (owner.minutes_recorded_on, owner.minutes_recorded_time, owner.minutes_legacy_raw), expected)] += 1
            bbkt_reference_evidence[_bbkt_reference_evidence_state(occurrences, owner.bbkt_reference)] += 1
    return {
        "decisions": _compatibility_summary(decision_states),
        "minutes": _compatibility_summary(minutes_states, bbkt_reference_evidence=bbkt_reference_evidence),
    }


def _apply_preflight(session: Session, preflight_result: dict[str, Any]) -> None:
    for item in preflight_result["decisions"]:
        if item["action"] == "INSERT":
            item["existing"] = InspectionDecision(**item["desired"])
            session.add(item["existing"])
    for item in preflight_result["minutes"]:
        if item["action"] == "INSERT":
            item["existing"] = InspectionMinutesRecord(**item["desired"])
            session.add(item["existing"])
    session.flush()
    for item in preflight_result["decisions"]:
        row = item["existing"]
        target = item.get("replacement_target")
        if target is None:
            continue
        row.relation_type = "REPLACES"
        row.related_decision_id = target["existing"].id
    session.flush()


def _count(session: Session, model: Any) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _report(plan: dict[str, Any], plan_sha: str, snapshot_sha: str, mode: str, pre_counts: dict[str, int], preflight_result: dict[str, Any], *, database_mutated: bool) -> dict[str, Any]:
    actions = preflight_result["actions"]
    source_relations = _source_replaces(plan, [item["candidate"] for item in preflight_result["decisions"]])
    action_keys = ("INSERT", "NOOP_IDENTICAL", "CONFLICT")
    relation_actions = {key: actions["relations"].get(key, 0) for key in ("LINK", "NOOP_IDENTICAL", "CONFLICT")}
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "provenance": {"snapshot_sha256": snapshot_sha, "plan_sha256": plan_sha, "database": REHEARSAL_DATABASE, "alembic_revision": REQUIRED_REVISION, "mode": mode},
        "pre_counts": pre_counts,
        "candidate_counts": {"decisions": len(preflight_result["decisions"]), "minutes": len(preflight_result["minutes"]), "source_replaces": len(source_relations), "writable_replaces": sum(item["candidate"].get("relation_type") == "REPLACES" for item in preflight_result["decisions"])},
        "actions": {"decisions": {key: actions["decisions"].get(key, 0) for key in action_keys}, "minutes": {key: actions["minutes"].get(key, 0) for key in action_keys}, "relations": relation_actions},
        "blocked_source_relations": {"count": len(source_relations), "by_classification": dict(sorted(Counter(str(item["classification"]) for item in source_relations).items()))},
        "blocked_source_counts": {"decisions": dict(sorted((plan.get("decisions") or {}).get("rehearsal_classification_counts", {}).items())), "minutes": dict(sorted((plan.get("minutes") or {}).get("rehearsal_classification_counts", {}).items()))},
        "canonical_gap_count": (plan.get("canonical_gaps") or {}).get("count"),
        "compliance_write_candidates": (plan.get("compliance") or {}).get("write_candidates"),
        "owner_validation": {"checked": len(preflight_result["decisions"]) + len(preflight_result["minutes"]), "mismatched": 0},
        "source_evidence_validation": {"checked": len(preflight_result["decisions"]) + len(preflight_result["minutes"]), "mismatched": 0},
        "compatibility_audit": preflight_result["compatibility"],
        "post_expected_counts": {"inspection_decision": pre_counts["inspection_decision"] + actions["decisions"].get("INSERT", 0), "inspection_minutes_record": pre_counts["inspection_minutes_record"] + actions["minutes"].get("INSERT", 0)},
        "database_mutated": database_mutated,
    }


def run(database_url: str, plan: dict[str, Any], snapshot_rows: list[dict[str, Any]], *, plan_sha: str, snapshot_sha: str, apply: bool) -> dict[str, Any]:
    _require_postgres_rehearsal(database_url)
    decisions, minutes = validate_plan(plan)
    prepared_decisions, prepared_minutes = prepare_candidates(plan, snapshot_rows)
    engine = create_engine(database_url, future=True)
    connection = None
    transaction = None
    try:
        connection = engine.connect()
        transaction = connection.begin()
        _verify_target(connection)
        session = Session(bind=connection, autoflush=False, expire_on_commit=False)
        try:
            pre_counts = {"inspection_decision": _count(session, InspectionDecision), "inspection_minutes_record": _count(session, InspectionMinutesRecord)}
            prepared = preflight(session, prepared_decisions, prepared_minutes, snapshot_rows=snapshot_rows)
            if apply:
                _apply_preflight(session, prepared)
            report = _report(plan, plan_sha, snapshot_sha, "apply" if apply else "dry-run", pre_counts, prepared, database_mutated=apply and any(prepared["actions"][name].get("INSERT", 0) or prepared["actions"][name].get("LINK", 0) for name in ("decisions", "minutes", "relations")))
        finally:
            session.close()
        if apply:
            transaction.commit()
        else:
            transaction.rollback()
        return report
    except Exception:
        if transaction is not None and transaction.is_active:
            transaction.rollback()
        raise
    finally:
        if connection is not None:
            connection.close()
        engine.dispose()


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.resolve().parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply audited Batch 6 structured decisions and minutes only.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--expected-snapshot-sha256", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        plan, rows, snapshot_sha, plan_sha = load_inputs(args.snapshot.resolve(), args.expected_snapshot_sha256, args.plan.resolve(), args.expected_plan_sha256)
        report = run(args.database_url, plan, rows, plan_sha=plan_sha, snapshot_sha=snapshot_sha, apply=args.apply)
        _write_report(args.output, report)
        return 0
    except Exception as error:
        _write_report(args.output, {"schema_version": REPORT_SCHEMA_VERSION, "database_mutated": False, "failure_type": type(error).__name__, "error_summary": _safe_error_summary(error)})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
