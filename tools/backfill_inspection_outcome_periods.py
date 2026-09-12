from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.enums import LegacyEntityType
from backend.app.db.models.phase1 import Case, InspectionOutcome, LegacyIdMap
from backend.app.domain.phase2_import import normalize_row, parse_int, parse_legacy_inspection_period
from tools.audit_inspection_case_lifecycle_legacy import _date_morphology
from tools.plan_inspection_case_lifecycle_reconciliation import (
    _resolve_case_identity,
    load_legacy_snapshot_json,
    require_rehearsal_database,
)


class BackfillInvariantError(RuntimeError):
    pass


WRITE_STATUSES = frozenset({"SAFE_INSERT", "SAFE_UPDATE_IF_EMPTY"})


def _case_projection(session: Session) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for case in session.scalars(select(Case)).all():
        lineage = session.scalars(
            select(LegacyIdMap).where(
                LegacyIdMap.target_table == "case",
                LegacyIdMap.target_entity_id == case.id,
            )
        ).all()
        outcomes = session.scalars(
            select(InspectionOutcome).where(InspectionOutcome.case_id == case.id)
        ).all()
        cases.append(
            {
                "id": case.id,
                "legacy_inspection_id": case.legacy_inspection_id,
                "legacy_lineage": [
                    {
                        "entity_type": mapping.entity_type.value,
                        "legacy_id": mapping.legacy_id,
                        "target_table": mapping.target_table,
                        "target_entity_id": mapping.target_entity_id,
                    }
                    for mapping in lineage
                    if mapping.entity_type == LegacyEntityType.CASE
                ],
                "outcomes": [
                    {
                        "id": outcome.id,
                        "inspected_on": outcome.inspected_on,
                        "inspected_to_on": outcome.inspected_to_on,
                    }
                    for outcome in outcomes
                ],
            }
        )
    return cases


def _source_row(raw: dict[str, Any]) -> dict[str, Any]:
    source = raw.get("__source_ktra", raw)
    if not isinstance(source, dict):
        raise BackfillInvariantError("legacy reconciliation row has invalid db.ktra source")
    return normalize_row(source)


def _safe_record(
    *,
    legacy_id: int | None,
    case_id: str | None,
    outcome_id: str | None,
    status: str,
    operation: str | None = None,
    source_value: str = "",
    source_period: tuple[date, date] | None = None,
    current_start: date | None = None,
    current_end: date | None = None,
) -> dict[str, Any]:
    start = None if source_period is None else source_period[0]
    end = None if source_period is None else source_period[1]
    return {
        "legacy_inspection_id": legacy_id,
        "case_id": case_id,
        "outcome_id": outcome_id,
        "status": status,
        "operation": operation,
        "source_morphology": _date_morphology(source_value),
        "source_resolution": "DETERMINISTIC" if source_period is not None else "UNRESOLVED",
        "candidate_start": None if start is None else start.isoformat(),
        "candidate_end": None if end is None else end.isoformat(),
        "current_start": None if current_start is None else current_start.isoformat(),
        "current_end": None if current_end is None else current_end.isoformat(),
        "expected_post_start": None if operation is None else start.isoformat(),
        "expected_post_end": None if operation is None else end.isoformat(),
    }


def build_backfill_plan(
    legacy_rows: list[dict[str, Any]], canonical_cases: list[dict[str, Any]]
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter(
        {
            "examined": 0,
            "eligible_safe_insert": 0,
            "eligible_safe_update_if_empty": 0,
            "already_matches": 0,
            "blocked_missing_outcome": 0,
            "blocked_multiple_outcomes": 0,
            "blocked_identity": 0,
            "blocked_source_changed": 0,
            "blocked_canonical_drift": 0,
            "blocked_provenance": 0,
            "blocked_source_ambiguous": 0,
            "writes_planned": 0,
        }
    )
    for raw in legacy_rows:
        row = _source_row(raw)
        legacy_id = parse_int(row.get("ID"))
        counts["examined"] += 1
        if legacy_id is None:
            counts["blocked_identity"] += 1
            records.append(_safe_record(legacy_id=None, case_id=None, outcome_id=None, status="BLOCKED_IDENTITY"))
            continue
        identity_status, matches = _resolve_case_identity(legacy_id, canonical_cases)
        if identity_status != "MATCHED":
            counts["blocked_identity"] += 1
            records.append(_safe_record(legacy_id=legacy_id, case_id=None, outcome_id=None, status="BLOCKED_IDENTITY"))
            continue
        case = matches[0]
        outcomes = case.get("outcomes") or []
        if len(outcomes) == 0:
            counts["blocked_missing_outcome"] += 1
            records.append(_safe_record(legacy_id=legacy_id, case_id=case["id"], outcome_id=None, status="NO_EXISTING_INSPECTION_OUTCOME"))
            continue
        if len(outcomes) != 1:
            counts["blocked_multiple_outcomes"] += 1
            records.append(_safe_record(legacy_id=legacy_id, case_id=case["id"], outcome_id=None, status="MULTIPLE_INSPECTION_OUTCOME_ROWS"))
            continue

        outcome = outcomes[0]
        source_value = str(row.get("inspected_at", ""))
        period = parse_legacy_inspection_period(source_value)
        if period is None:
            counts["blocked_source_ambiguous"] += 1
            records.append(_safe_record(legacy_id=legacy_id, case_id=case["id"], outcome_id=outcome["id"], status="BLOCKED_SOURCE_AMBIGUOUS", source_value=source_value))
            continue
        start, end = period
        current_start = outcome.get("inspected_on")
        current_end = outcome.get("inspected_to_on")
        bbkt_period = parse_legacy_inspection_period(str(row.get("bbkt_reference", "")))
        bbkt_start = None if bbkt_period is None else bbkt_period[0]
        if current_start is None and current_end is None:
            counts["eligible_safe_insert"] += 1
            counts["writes_planned"] += 1
            records.append(_safe_record(legacy_id=legacy_id, case_id=case["id"], outcome_id=outcome["id"], status="SAFE_INSERT", operation="FILL_BOTH", source_value=source_value, source_period=period, current_start=current_start, current_end=current_end))
        elif current_start == start and current_end is None and bbkt_start != current_start:
            counts["eligible_safe_update_if_empty"] += 1
            counts["writes_planned"] += 1
            records.append(_safe_record(legacy_id=legacy_id, case_id=case["id"], outcome_id=outcome["id"], status="SAFE_UPDATE_IF_EMPTY", operation="FILL_END", source_value=source_value, source_period=period, current_start=current_start, current_end=current_end))
        elif current_start == start and current_end == end:
            counts["already_matches"] += 1
            records.append(_safe_record(legacy_id=legacy_id, case_id=case["id"], outcome_id=outcome["id"], status="ALREADY_MATCHES", source_value=source_value, source_period=period, current_start=current_start, current_end=current_end))
        elif bbkt_start is not None and current_start == bbkt_start:
            counts["blocked_provenance"] += 1
            records.append(_safe_record(legacy_id=legacy_id, case_id=case["id"], outcome_id=outcome["id"], status="BLOCKED_PROVENANCE", source_value=source_value, source_period=period, current_start=current_start, current_end=current_end))
        else:
            counts["blocked_canonical_drift"] += 1
            records.append(_safe_record(legacy_id=legacy_id, case_id=case["id"], outcome_id=outcome["id"], status="BLOCKED_CANONICAL_DRIFT", source_value=source_value, source_period=period, current_start=current_start, current_end=current_end))
    return {
        "schema_version": "inspection-outcome-period-backfill-plan/v1",
        "database_policy": {"required_database_name": "gxp_legacy_rehearsal", "writes_performed": False},
        "summary": dict(counts),
        "records": records,
    }


def apply_backfill_plan(session: Session, legacy_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply only a freshly recomputed, fully guarded rehearsal plan."""
    plan = build_backfill_plan(legacy_rows, _case_projection(session))
    writes = [record for record in plan["records"] if record["status"] in WRITE_STATUSES]
    for record in writes:
        outcomes = session.scalars(
            select(InspectionOutcome)
            .where(InspectionOutcome.case_id == record["case_id"])
            .with_for_update()
        ).all()
        if len(outcomes) != 1 or outcomes[0].id != record["outcome_id"]:
            raise BackfillInvariantError("inspection outcome changed during backfill")
        outcome = outcomes[0]
        expected_start = None if record["current_start"] is None else date.fromisoformat(record["current_start"])
        expected_end = None if record["current_end"] is None else date.fromisoformat(record["current_end"])
        if outcome.inspected_on != expected_start or outcome.inspected_to_on != expected_end:
            raise BackfillInvariantError("canonical inspection period drifted before write")
        candidate_start = date.fromisoformat(record["candidate_start"])
        candidate_end = date.fromisoformat(record["candidate_end"])
        if record["operation"] == "FILL_BOTH":
            outcome.inspected_on = candidate_start
            outcome.inspected_to_on = candidate_end
        elif record["operation"] == "FILL_END":
            outcome.inspected_to_on = candidate_end
        else:
            raise BackfillInvariantError("unknown backfill operation")
        session.flush()
        if outcome.inspected_on != candidate_start or outcome.inspected_to_on != candidate_end:
            raise BackfillInvariantError("post-write inspection period verification failed")
    plan["database_policy"]["writes_performed"] = bool(writes)
    plan["summary"]["writes_performed"] = len(writes)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded rehearsal backfill for InspectionOutcome periods.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Explicitly apply the bounded rehearsal backfill.")
    args = parser.parse_args()
    require_rehearsal_database(args.database_url)
    legacy_rows = load_legacy_snapshot_json(args.snapshot)["legacy_rows"]
    engine = create_engine(args.database_url)
    with Session(engine) as session:
        if args.apply:
            try:
                report = apply_backfill_plan(session, legacy_rows)
                session.commit()
            except Exception:
                session.rollback()
                raise
        else:
            report = build_backfill_plan(legacy_rows, _case_projection(session))
        print(json.dumps(report, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
