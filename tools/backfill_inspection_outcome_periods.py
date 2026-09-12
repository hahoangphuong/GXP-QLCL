from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from backend.app.db.enums import LegacyEntityType
from backend.app.db.models.phase1 import Case, InspectionOutcome, LegacyIdMap
from backend.app.domain.phase2_import import normalize_row, parse_int
from backend.app.domain.inspection_periods import InspectionPeriodSourceState, parse_legacy_inspection_periods
from tools.audit_inspection_case_lifecycle_legacy import _date_morphology
from tools.plan_inspection_case_lifecycle_reconciliation import (
    REQUIRED_DATABASE_NAME,
    _resolve_case_identity,
    build_engine,
    build_reconciliation_plan,
    load_legacy_snapshot_json,
    require_rehearsal_database,
)


CANONICAL_WORKBOOK_SHA256 = "c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d"
CANONICAL_SNAPSHOT_SHA256 = "234498b1f74d811ef0fb6f39a71af42919cdd440cad9e53d82c287d526588666"
WRITE_STATUSES = frozenset({"SAFE_INSERT", "SAFE_UPDATE_IF_EMPTY"})


class BackfillInvariantError(RuntimeError):
    pass


def _source_row(raw: dict[str, Any]) -> dict[str, Any]:
    source = raw.get("__source_ktra", raw)
    if not isinstance(source, dict):
        raise BackfillInvariantError("legacy reconciliation row has invalid db.ktra source")
    return normalize_row(source)


def _source_rows_by_id(legacy_rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for raw in legacy_rows:
        legacy_id = parse_int(_source_row(raw).get("ID"))
        if legacy_id is None or legacy_id in result:
            raise BackfillInvariantError("snapshot has invalid or duplicate db.ktra identity")
        result[legacy_id] = raw
    return result


def _case_record(case: Case, mappings: list[LegacyIdMap], outcomes: list[InspectionOutcome]) -> dict[str, Any]:
    outcome_values = [
        {"id": outcome.id, "inspected_on": outcome.inspected_on, "inspected_to_on": outcome.inspected_to_on}
        for outcome in outcomes
    ]
    return {
        "id": case.id,
        "legacy_inspection_id": case.legacy_inspection_id,
        "legacy_lineage": [
            {
                "entity_type": mapping.entity_type.value,
                "legacy_id": mapping.legacy_id,
                "target_table": mapping.target_table,
                "target_entity_id": mapping.target_entity_id,
            }
            for mapping in mappings
            if mapping.entity_type == LegacyEntityType.CASE
        ],
        "outcome": outcome_values[0] if len(outcome_values) == 1 else {},
        "outcomes": outcome_values,
    }


def _case_projection(session: Session) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for case in session.scalars(select(Case)).all():
        mappings = session.scalars(
            select(LegacyIdMap).where(LegacyIdMap.target_table == "case", LegacyIdMap.target_entity_id == case.id)
        ).all()
        outcomes = session.scalars(select(InspectionOutcome).where(InspectionOutcome.case_id == case.id)).all()
        result.append(_case_record(case, mappings, outcomes))
    return result


def _safe_record(
    *,
    legacy_id: int,
    planner_status: str | None,
    case_id: str | None = None,
    outcome_id: str | None = None,
    status: str | None = None,
    source_value: str = "",
    period: tuple[date, date] | None = None,
    current_start: date | None = None,
    current_end: date | None = None,
) -> dict[str, Any]:
    start = None if period is None else period[0]
    end = None if period is None else period[1]
    return {
        "legacy_inspection_id": legacy_id,
        "case_id": case_id,
        "outcome_id": outcome_id,
        "planner_status": planner_status,
        "status": status or planner_status or "BLOCKED_BY_PLANNER_NO_PERIOD_FACT",
        "operation": (
            "FILL_BOTH"
            if (status or planner_status) == "SAFE_INSERT"
            else "FILL_END"
            if (status or planner_status) == "SAFE_UPDATE_IF_EMPTY"
            else None
        ),
        "source_morphology": _date_morphology(source_value),
        "candidate_start": None if start is None else start.isoformat(),
        "candidate_end": None if end is None else end.isoformat(),
        "current_start": None if current_start is None else current_start.isoformat(),
        "current_end": None if current_end is None else current_end.isoformat(),
        "expected_post_start": None if start is None else start.isoformat(),
        "expected_post_end": None if end is None else end.isoformat(),
    }


def _period_facts_by_legacy_id(planner_plan: dict[str, Any]) -> dict[int, dict[str, Any]]:
    facts: dict[int, dict[str, Any]] = {}
    for fact in planner_plan["facts"]:
        if fact.get("canonical_fact") != "actual_inspection_period":
            continue
        legacy_id = fact.get("legacy_inspection_id")
        if not isinstance(legacy_id, int) or legacy_id in facts:
            raise BackfillInvariantError("planner emitted an ambiguous actual inspection period fact")
        facts[legacy_id] = fact
    return facts


def build_backfill_plan(legacy_rows: list[dict[str, Any]], canonical_cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive writes exclusively from the audited v4 planner's period facts."""
    planner_plan = build_reconciliation_plan(legacy_rows, canonical_cases)
    source_rows = _source_rows_by_id(legacy_rows)
    facts = _period_facts_by_legacy_id(planner_plan)
    cases_by_id = {str(case["id"]): case for case in canonical_cases}
    records: list[dict[str, Any]] = []
    structural_counts: Counter[str] = Counter()

    for legacy_id, raw in source_rows.items():
        fact = facts.get(legacy_id)
        planner_status = None if fact is None else str(fact["reconciliation_status"])
        row = _source_row(raw)
        source_value = str(row.get("inspected_at", ""))
        if planner_status not in WRITE_STATUSES:
            records.append(_safe_record(legacy_id=legacy_id, planner_status=planner_status, source_value=source_value))
            continue
        case_id = str(fact["case_id"])
        identity_status, matches = _resolve_case_identity(legacy_id, canonical_cases)
        if identity_status != "MATCHED" or str(matches[0]["id"]) != case_id:
            structural_counts["identity"] += 1
            records.append(_safe_record(legacy_id=legacy_id, planner_status=planner_status, status="BLOCKED_IDENTITY_REVALIDATION", source_value=source_value))
            continue
        case = cases_by_id[case_id]
        outcomes = case.get("outcomes") or []
        if len(outcomes) != 1:
            structural_counts["outcome_cardinality"] += 1
            records.append(_safe_record(legacy_id=legacy_id, planner_status=planner_status, case_id=case_id, status="BLOCKED_OUTCOME_CARDINALITY", source_value=source_value))
            continue
        parsed = parse_legacy_inspection_periods(source_value)
        if parsed.state != InspectionPeriodSourceState.KNOWN or len(parsed.segments) != 1:
            raise BackfillInvariantError(
                "legacy two-column backfill only accepts one deterministic inspection period segment"
            )
        segment = parsed.segments[0]
        period = (segment.started_on, segment.ended_on)
        outcome = outcomes[0]
        records.append(_safe_record(
            legacy_id=legacy_id,
            planner_status=planner_status,
            case_id=case_id,
            outcome_id=str(outcome["id"]),
            source_value=source_value,
            period=period,
            current_start=outcome.get("inspected_on"),
            current_end=outcome.get("inspected_to_on"),
        ))

    return {
        "schema_version": "inspection-outcome-period-backfill-plan/v2",
        "planner_schema_version": planner_plan["schema_version"],
        "database_policy": {"required_database_name": REQUIRED_DATABASE_NAME, "writes_performed": False},
        "planner_period_status_counts": dict(Counter(record["planner_status"] or "NO_PERIOD_FACT" for record in records)),
        "migration_structural_guard_counts": dict(structural_counts),
        "summary": {
            "examined": len(records),
            "writes_planned": sum(record["status"] in WRITE_STATUSES for record in records),
            "safe_insert": sum(record["status"] == "SAFE_INSERT" for record in records),
            "safe_update_if_empty": sum(record["status"] == "SAFE_UPDATE_IF_EMPTY" for record in records),
        },
        "records": records,
    }


def _locked_case_projection(session: Session, legacy_id: int) -> list[dict[str, Any]]:
    mappings = session.scalars(
        select(LegacyIdMap)
        .where(
            LegacyIdMap.entity_type == LegacyEntityType.CASE,
            LegacyIdMap.target_table == "case",
            LegacyIdMap.legacy_id == str(legacy_id),
        )
        .with_for_update()
    ).all()
    target_ids = {mapping.target_entity_id for mapping in mappings}
    cases = session.scalars(
        select(Case)
        .where(or_(Case.legacy_inspection_id == legacy_id, Case.id.in_(target_ids)))
        .with_for_update()
    ).all()
    result: list[dict[str, Any]] = []
    for case in cases:
        case_mappings = session.scalars(
            select(LegacyIdMap)
            .where(LegacyIdMap.target_table == "case", LegacyIdMap.target_entity_id == case.id)
            .with_for_update()
        ).all()
        outcomes = session.scalars(
            select(InspectionOutcome).where(InspectionOutcome.case_id == case.id).with_for_update()
        ).all()
        result.append(_case_record(case, case_mappings, outcomes))
    return result


def _safe_period_fact(raw: dict[str, Any], canonical_cases: list[dict[str, Any]], legacy_id: int) -> dict[str, Any]:
    fact = _period_facts_by_legacy_id(build_reconciliation_plan([raw], canonical_cases)).get(legacy_id)
    if fact is None or fact["reconciliation_status"] not in WRITE_STATUSES:
        raise BackfillInvariantError("planner eligibility changed before write")
    return fact


def _revalidate_locked_write(session: Session, record: dict[str, Any], raw: dict[str, Any]) -> InspectionOutcome:
    legacy_id = int(record["legacy_inspection_id"])
    locked_cases = _locked_case_projection(session, legacy_id)
    identity_status, matches = _resolve_case_identity(legacy_id, locked_cases)
    if identity_status != "MATCHED" or str(matches[0]["id"]) != record["case_id"]:
        raise BackfillInvariantError("case identity changed before write")
    outcomes = matches[0].get("outcomes") or []
    if len(outcomes) != 1 or str(outcomes[0]["id"]) != record["outcome_id"]:
        raise BackfillInvariantError("inspection outcome identity changed before write")
    start = None if outcomes[0].get("inspected_on") is None else outcomes[0]["inspected_on"].isoformat()
    end = None if outcomes[0].get("inspected_to_on") is None else outcomes[0]["inspected_to_on"].isoformat()
    if start != record["current_start"] or end != record["current_end"]:
        raise BackfillInvariantError("canonical inspection period drifted before write")
    locked_fact = _safe_period_fact(raw, locked_cases, legacy_id)
    if locked_fact["reconciliation_status"] != record["planner_status"]:
        raise BackfillInvariantError("planner eligibility changed before write")
    outcome = session.get(InspectionOutcome, record["outcome_id"], with_for_update=True)
    if outcome is None:
        raise BackfillInvariantError("inspection outcome disappeared before write")
    return outcome


def apply_backfill_plan(session: Session, legacy_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply a freshly derived planner v4 write set inside the caller transaction."""
    plan = build_backfill_plan(legacy_rows, _case_projection(session))
    source_rows = _source_rows_by_id(legacy_rows)
    writes = [record for record in plan["records"] if record["status"] in WRITE_STATUSES]
    for record in writes:
        outcome = _revalidate_locked_write(session, record, source_rows[int(record["legacy_inspection_id"])])
        candidate_start = date.fromisoformat(record["candidate_start"])
        candidate_end = date.fromisoformat(record["candidate_end"])
        if record["status"] == "SAFE_INSERT":
            outcome.inspected_on = candidate_start
            outcome.inspected_to_on = candidate_end
        else:
            outcome.inspected_to_on = candidate_end
        session.flush()
        if outcome.inspected_on != candidate_start or outcome.inspected_to_on != candidate_end:
            raise BackfillInvariantError("post-write inspection period verification failed")
    plan["database_policy"]["writes_performed"] = bool(writes)
    plan["summary"]["writes_performed"] = len(writes)
    return plan


def load_audited_snapshot_json(path: Path, *, expected_workbook_sha256: str, expected_snapshot_sha256: str) -> dict[str, Any]:
    """Bind a run to the audited workbook provenance and immutable snapshot bytes."""
    if expected_workbook_sha256 != CANONICAL_WORKBOOK_SHA256:
        raise BackfillInvariantError("expected workbook provenance is not the audited canonical workbook")
    if expected_snapshot_sha256 != CANONICAL_SNAPSHOT_SHA256:
        raise BackfillInvariantError("expected snapshot integrity is not the audited canonical snapshot")
    actual_snapshot_sha256 = sha256(path.read_bytes()).hexdigest()
    if actual_snapshot_sha256 != expected_snapshot_sha256:
        raise BackfillInvariantError("snapshot file integrity does not match the expected SHA256")
    snapshot = load_legacy_snapshot_json(path, expected_workbook_sha256=expected_workbook_sha256)
    if snapshot["provenance"]["source_workbook_sha256"] != expected_workbook_sha256:
        raise BackfillInvariantError("snapshot workbook provenance changed after validation")
    snapshot["file_integrity_sha256"] = actual_snapshot_sha256
    return snapshot


def _verify_rehearsal_connection(connection: Connection, *, require_read_only: bool) -> dict[str, Any]:
    database_name = str(connection.execute(text("SELECT current_database()")).scalar_one())
    if database_name != REQUIRED_DATABASE_NAME:
        raise BackfillInvariantError("backfill connected to a database other than gxp_legacy_rehearsal")
    transaction_read_only: bool | None = None
    if require_read_only:
        value = str(connection.execute(text("SHOW transaction_read_only")).scalar_one()).strip().lower()
        transaction_read_only = value in {"on", "true", "1"}
        if not transaction_read_only:
            raise BackfillInvariantError("backfill dry-run requires a read-only database transaction")
    return {"actual_database_name": database_name, "transaction_read_only": transaction_read_only}


def run_backfill_from_snapshot(database_url: str, snapshot: dict[str, Any], *, apply: bool) -> dict[str, Any]:
    require_rehearsal_database(database_url)
    engine = build_engine(database_url)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False, expire_on_commit=False)
    try:
        if not apply:
            connection.execute(text("SET TRANSACTION READ ONLY"))
        connection_metadata = _verify_rehearsal_connection(connection, require_read_only=not apply)
        report = apply_backfill_plan(session, snapshot["legacy_rows"]) if apply else build_backfill_plan(snapshot["legacy_rows"], _case_projection(session))
        report["database_connection"] = connection_metadata
        report["source_snapshot"] = snapshot["provenance"]
        report["snapshot_file_integrity_sha256"] = snapshot["file_integrity_sha256"]
        if apply:
            transaction.commit()
        return report
    except Exception:
        transaction.rollback()
        raise
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded rehearsal backfill for InspectionOutcome periods.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--expected-workbook-sha256", required=True)
    parser.add_argument("--expected-snapshot-sha256", required=True)
    parser.add_argument("--apply", action="store_true", help="Explicitly apply the bounded rehearsal backfill.")
    args = parser.parse_args()
    snapshot = load_audited_snapshot_json(
        args.snapshot,
        expected_workbook_sha256=args.expected_workbook_sha256,
        expected_snapshot_sha256=args.expected_snapshot_sha256,
    )
    report = run_backfill_from_snapshot(args.database_url, snapshot, apply=args.apply)
    print(json.dumps(report, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
