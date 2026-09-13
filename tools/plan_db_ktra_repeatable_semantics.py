"""Read-only Batch 6 source plan for repeatable db.ktra decisions and minutes."""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from backend.app.domain.legacy_db_ktra_reconciliation import (
    parse_legacy_inspection_decisions,
    parse_legacy_minutes_records,
    scalar_compatibility_projection,
    safe_evidence,
)
from backend.app.domain.phase2_import import parse_int
from tools.plan_db_ktra_reconciliation import SNAPSHOT, load_snapshot
from tools.plan_db_ktra_reconciliation import REHEARSAL_DATABASE, REQUIRED_REVISION, validate_rehearsal_target, verify_read_only_connection
from backend.app.db.models.phase1 import Case, InspectionOutcome, InspectionPlan


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "legacy_audit" / "db_ktra_repeatable_semantics_plan_v1.json"


def _projection(occurrences: list[dict[str, Any]]) -> str:
    return "SINGLETON_MIRROR" if scalar_compatibility_projection(occurrences) else "NULL"


def _source_rows(rows: list[dict[str, Any]], field: str, parser: Any) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    occurrences = 0
    entries = []
    for row in rows:
        legacy_id = parse_int(row.get("ID", ""))
        if legacy_id is None:
            continue
        parsed = parser(row.get(field))
        records = parsed["occurrences"]
        occurrences += len(records)
        bucket = "MISSING" if parsed["state"] == "MISSING" else "RAW_ONLY" if parsed["state"] == "RAW_ONLY" else "UNRESOLVED_OR_PARTIAL" if parsed["state"] != "KNOWN" else "ONE" if len(records) == 1 else "MULTIPLE"
        counts[bucket] += 1
        entries.append({"legacy_inspection_id": legacy_id, "source_state": parsed["state"], "occurrences": [{key: (value.isoformat() if hasattr(value, "isoformat") else value) for key, value in item.items() if key != "legacy_raw"} for item in records], "projection": _projection(records), **safe_evidence(parsed["raw"])})
    return {"source_rows_total": len(entries), "rows_by_cardinality": dict(sorted(counts.items())), "total_occurrences": occurrences, "rows": entries}


def build_plan(rows: list[dict[str, Any]]) -> dict[str, Any]:
    decisions = _source_rows(rows, "decision_reference", parse_legacy_inspection_decisions)
    minutes = _source_rows(rows, "bbkt_reference", parse_legacy_minutes_records)
    decisions["explicit_replaces_relations"] = sum(item["relation_type"] == "REPLACES" for row in decisions["rows"] for item in row["occurrences"])
    durations = [parse_int(row.get("ID", "")) for row in rows if str(row.get("HẠN KT TUÂN THỦ") or "").strip().lower().replace(" ", "") in {"3năm", "03năm"}]
    return {"schema_version": "db-ktra-repeatable-semantics-plan/v1", "decisions": decisions, "minutes": minutes, "compliance": {"NO_MIGRATION_USER_ENTERED": sorted(item for item in durations if item is not None), "write_candidates": 0}, "canonical_gaps": {"classification": "NO_AUTO_CREATE", "requires_rehearsal_read_only_comparison": True}, "write_candidates": "BLOCKED_PENDING_READ_ONLY_REHEARSAL_COMPARISON", "guardrails": {"database_mutated": False, "fuzzy_matching_used": False, "importer_invoked": False, "apply_tool_present": False}}


def build_rehearsal_comparison(rows: list[dict[str, Any]], owners: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Attach exact existing owners; this function cannot create or link a Case."""
    report = build_plan(rows)
    # Invalid legacy identifiers are source diagnostics only, never ownership
    # keys, gaps, or candidates.
    valid_rows = [(legacy_id, row) for row in rows if (legacy_id := parse_int(row.get("ID", ""))) is not None]
    for name, field, parser, owner_key, missing in (
        ("decisions", "decision_reference", parse_legacy_inspection_decisions, "inspection_plan_id", "BLOCKED_NO_INSPECTION_PLAN"),
        ("minutes", "bbkt_reference", parse_legacy_minutes_records, "inspection_outcome_id", "BLOCKED_NO_INSPECTION_OUTCOME"),
    ):
        candidates = []
        classified = []
        counts: Counter[str] = Counter()
        for legacy_id, row in valid_rows:
            parsed = parser(row.get(field))
            if parsed["state"] == "RAW_ONLY": category = "RAW_ONLY"
            elif parsed["state"] != "KNOWN": category = "BLOCKED_SOURCE_UNRESOLVED"
            elif legacy_id not in owners: category = "BLOCKED_NO_CANONICAL_CASE"
            elif owners[legacy_id].get(owner_key) is None: category = missing
            else: category = "WRITE_CANDIDATE"
            counts[category] += 1
            occurrences = parsed["occurrences"] or [{"ordinal": None, "legacy_raw": parsed["raw"]}]
            for occurrence in occurrences:
                record = {
                    "classification": category,
                    "legacy_inspection_id": legacy_id,
                    "canonical_case_id": None if legacy_id not in owners else owners[legacy_id]["case_id"],
                    owner_key: None if legacy_id not in owners else owners[legacy_id].get(owner_key),
                    "source_ordinal": occurrence["ordinal"],
                    **{key: (value.isoformat() if hasattr(value, "isoformat") else value) for key, value in occurrence.items() if key not in {"ordinal", "legacy_raw"}},
                    **safe_evidence(occurrence["legacy_raw"]),
                }
                classified.append(record)
                if category == "WRITE_CANDIDATE":
                    candidates.append(record)
        report[name]["rehearsal_classification_counts"] = dict(sorted(counts.items()))
        report[name]["classification_records"] = classified
        report[name]["candidates"] = candidates
    gaps = sorted(legacy_id for legacy_id, _row in valid_rows if legacy_id not in owners)
    report["canonical_gaps"] = {"classification": "NO_AUTO_CREATE", "legacy_inspection_ids": gaps, "count": len(gaps), "write_candidates": 0}
    report["write_candidates"] = {"decisions": report["decisions"]["candidates"], "minutes": report["minutes"]["candidates"]}
    report["guardrails"]["transaction_read_only"] = True
    return report


def _read_owners(database_url: str, rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    validate_rehearsal_target(database_url)
    engine = create_engine(database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            verify_read_only_connection(connection)
            for table in ("inspection_decision", "inspection_minutes_record"):
                if connection.execute(text("SELECT to_regclass(:table)"), {"table": table}).scalar_one() is not None:
                    raise RuntimeError(f"{table} exists; repeatable planner requires pre-0013 rehearsal state")
            session = Session(bind=connection)
            cases = list(session.scalars(select(Case)))
            plans = {item.case_id: item.id for item in session.scalars(select(InspectionPlan))}
            outcomes = {item.case_id: item.id for item in session.scalars(select(InspectionOutcome))}
            return {case.legacy_inspection_id: {"case_id": case.id, "inspection_plan_id": plans.get(case.id), "inspection_outcome_id": outcomes.get(case.id)} for case in cases if case.legacy_inspection_id is not None}
        finally:
            transaction.rollback()
            engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a source-only Batch 6 repeatable semantics plan.")
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--database-url")
    args = parser.parse_args(argv)
    rows = load_snapshot(args.snapshot.resolve())
    plan = build_plan(rows) if args.database_url is None else build_rehearsal_comparison(rows, _read_owners(args.database_url, rows))
    encoded = (json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    args.output.write_bytes(encoded)
    print(f"SHA256={sha256(encoded).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
