"""Read-only evidence planner for the approved db.ktra semantic split.

Snapshot-only mode profiles parser morphology.  ``--compare-rehearsal`` is an
explicit PostgreSQL-only mode and starts a read-only transaction before SELECTs.
Neither path writes database rows or changes the legacy importer.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from backend.app.domain.legacy_db_ktra_reconciliation import (
    parse_legacy_approval_submission,
    parse_legacy_certificate_id,
    parse_legacy_date,
    parse_legacy_inspection_decision,
    parse_legacy_minutes_recorded,
    parse_legacy_team,
    safe_evidence,
)
from backend.app.domain.phase2_import import normalize_row, parse_int
from tools.profile_legacy_semantics import (
    CANONICAL_SNAPSHOT_ARTIFACT_SHA256,
    snapshot_artifact_sha256,
)
from backend.app.db.models.phase1 import Case, CaseApplication, CaseAssessment, InspectionOutcome, InspectionPlan


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "artifacts" / "phase3c" / "legacy_snapshot.json"
DEFAULT_PROFILE = ROOT / "artifacts" / "legacy_audit" / "db_ktra_parser_profile_v1.json"
DEFAULT_PLAN = ROOT / "artifacts" / "legacy_audit" / "db_ktra_reconciliation_plan_v1.json"
DEFAULT_CONTAMINATION = ROOT / "artifacts" / "legacy_audit" / "db_ktra_contamination_report_v1.json"
REHEARSAL_DATABASE = "gxp_legacy_rehearsal"
REQUIRED_REVISION = "20260912_0012"

PARSERS: dict[str, tuple[str, Callable[[object], dict[str, Any]]]] = {
    "Q. định": ("decision_reference", parse_legacy_inspection_decision),
    "B. bản": ("bbkt_reference", parse_legacy_minutes_recorded),
    "ĐÁNH GIÁ CUỐI": ("ĐÁNH GIÁ CUỐI", lambda value: {"state": "KNOWN", "value": str(value).strip(), "raw": str(value).strip()} if str(value or "").strip() not in {"", "-", "???"} else {"state": "MISSING", "value": None, "raw": str(value or "").strip()}),
    "HẠN KT TUÂN THỦ": ("HẠN KT TUÂN THỦ", parse_legacy_date),
    "T.tra viên": ("T.tra viên", parse_legacy_team),
    "PHIẾU TRÌNH PCT": ("PHIẾU TRÌNH PCT", parse_legacy_approval_submission),
    "PHIẾU TRÌNH CT": ("PHIẾU TRÌNH CT", parse_legacy_approval_submission),
    "ID CC GPs": ("ID CC GPs", parse_legacy_certificate_id),
}


def load_snapshot(path: Path) -> list[dict[str, Any]]:
    actual = snapshot_artifact_sha256(path)
    if actual != CANONICAL_SNAPSHOT_ARTIFACT_SHA256:
        raise RuntimeError("canonical snapshot SHA256 provenance guard failed")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("db.ktra")
    if not isinstance(rows, list):
        raise RuntimeError("canonical snapshot is missing db.ktra rows")
    return [normalize_row(row) for row in rows if isinstance(row, dict)]


def _safe_value(parsed: dict[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {"state": parsed["state"]}
    for key in ("decision_reference", "decision_date", "recorded_on", "recorded_time", "precision", "value", "legacy_certificate_id"):
        raw = parsed.get(key)
        if raw is not None:
            value[key] = raw.isoformat() if hasattr(raw, "isoformat") else raw
    if "members" in parsed:
        value["member_count"] = len(parsed["members"])
        value["role_codes"] = [member["role_code"] for member in parsed["members"]]
    return value


def profile_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in rows if parse_int(row.get("ID", "")) is not None]
    fields: dict[str, Any] = {}
    for header, (source_key, parser) in PARSERS.items():
        states: Counter[str] = Counter()
        examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in valid:
            parsed = parser(row.get(source_key))
            state = str(parsed["state"])
            states[state] += 1
            if len(examples[state]) < 3:
                examples[state].append({**safe_evidence(parsed.get("raw", "")), "parsed": _safe_value(parsed)})
        fields[header] = {"state_counts": dict(sorted(states.items())), "representative_safe_examples": dict(sorted(examples.items()))}
    return {
        "schema_version": "db-ktra-parser-profile/v1",
        "source": {"snapshot_path": "artifacts/phase3c/legacy_snapshot.json", "snapshot_artifact_sha256": CANONICAL_SNAPSHOT_ARTIFACT_SHA256},
        "valid_legacy_rows": len(valid),
        "fields": fields,
        "guardrails": {"database_mutated": False, "workbook_mutated": False, "importer_invoked": False},
    }


def validate_rehearsal_target(database_url: str) -> None:
    parsed = urlsplit(database_url)
    if not parsed.scheme.startswith("postgresql"):
        raise RuntimeError("db.ktra planner requires PostgreSQL rehearsal database")
    if parsed.path.rsplit("/", 1)[-1] != REHEARSAL_DATABASE:
        raise RuntimeError("db.ktra planner refuses database other than gxp_legacy_rehearsal")


def verify_read_only_connection(connection: Any) -> None:
    if connection.execute(text("SELECT current_database()")).scalar_one() != REHEARSAL_DATABASE:
        raise RuntimeError("db.ktra planner connected to an unsafe database")
    if str(connection.execute(text("SHOW transaction_read_only")).scalar_one()).strip().lower() not in {"on", "true", "1"}:
        raise RuntimeError("db.ktra planner requires a read-only transaction")
    revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision != REQUIRED_REVISION:
        raise RuntimeError("db.ktra planner requires Alembic revision 20260912_0012")


def _classification(source: str, current: object) -> str:
    if source == "MISSING":
        return "MISSING_SOURCE"
    if current is None:
        return "SAFE_DIRECT"
    return "ALREADY_MATCHES" if current == source else "BLOCKED_EXISTING_CANONICAL_CONFLICT"


def build_comparison_plan(rows: list[dict[str, Any]], canonical_by_legacy_id: dict[int, dict[str, Any]]) -> dict[str, Any]:
    facts: list[dict[str, Any]] = []
    contamination: Counter[str] = Counter()
    for row in rows:
        legacy_id = parse_int(row.get("ID", ""))
        if legacy_id is None:
            continue
        case = canonical_by_legacy_id.get(legacy_id)
        if case is None:
            facts.append({"legacy_row": legacy_id, "legacy_case_id": legacy_id, "canonical_case_id": None, "fact": "case_identity", "source_state": "KNOWN", "classification": "BLOCKED_IDENTITY", "reason": "no exact canonical case identity", "future_action": "none", "target_owner": "Case"})
            continue
        outcome = case.get("outcome") or {}
        assessment = case.get("assessment") or {}
        result = str(row.get("assessment_result", "")).strip()
        source_state = "MISSING" if result in {"", "-", "???"} else "KNOWN"
        outcome_class = _classification("MISSING" if source_state == "MISSING" else result, outcome.get("outcome_result"))
        assessment_value = assessment.get("assessment_result")
        assessment_class = "NO_ASSESSMENT_ROW" if case.get("assessment") is None else "ASSESSMENT_EMPTY" if assessment_value is None else "CONTAMINATED_EXACT_COPY" if source_state == "KNOWN" and assessment_value == result else "ASSESSMENT_DIFFERENT"
        contamination[assessment_class] += 1
        evidence = safe_evidence(result)
        facts.extend([
            {"legacy_row": legacy_id, "legacy_case_id": legacy_id, "canonical_case_id": case["id"], "fact": "outcome_result", "source_state": source_state, **evidence, "parsed_value": None if source_state == "MISSING" else {"sha256": evidence["source_raw_hash"]}, "current_canonical_value": outcome.get("outcome_result"), "classification": outcome_class, "reason": "db.ktra.Kết quả maps only to InspectionOutcome.outcome_result", "future_action": "write_structured_owner" if outcome_class == "SAFE_DIRECT" else "none", "target_owner": "InspectionOutcome.outcome_result"},
            {"legacy_row": legacy_id, "legacy_case_id": legacy_id, "canonical_case_id": case["id"], "fact": "assessment_result_contamination", "source_state": source_state, **evidence, "parsed_value": None, "current_canonical_value": assessment_value, "classification": assessment_class, "reason": "Kết quả is not a CaseAssessment source", "future_action": "review_only", "target_owner": "CaseAssessment.assessment_result"},
        ])
    return {"schema_version": "db-ktra-reconciliation-plan/v1", "comparison_status": "COMPARED", "facts": facts, "summary": {"legacy_rows": sum(1 for row in rows if parse_int(row.get("ID", "")) is not None), "classification_counts": dict(Counter(fact["classification"] for fact in facts))}, "contamination": {"ket_qua_to_case_assessment": dict(contamination)}, "guardrails": {"database_mutated": False, "write_plan_only": True}}


def run_read_only_comparison(database_url: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Read canonical comparison inputs without creating a candidate write plan."""
    validate_rehearsal_target(database_url)
    engine = create_engine(database_url)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False, expire_on_commit=False)
    try:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        verify_read_only_connection(connection)
        legacy_ids = {parse_int(row.get("ID", "")) for row in rows}
        cases = list(session.scalars(select(Case).where(Case.legacy_inspection_id.in_({value for value in legacy_ids if value is not None}))))
        canonical: dict[int, dict[str, Any]] = {}
        for case in cases:
            application = session.scalar(select(CaseApplication).where(CaseApplication.case_id == case.id))
            assessment = session.scalar(select(CaseAssessment).where(CaseAssessment.case_id == case.id))
            plan = session.scalar(select(InspectionPlan).where(InspectionPlan.case_id == case.id))
            outcome = session.scalar(select(InspectionOutcome).where(InspectionOutcome.case_id == case.id))
            canonical[case.legacy_inspection_id] = {
                "id": case.id,
                "application": None if application is None else {"dossier_reference": application.dossier_reference},
                "assessment": None if assessment is None else {"assessment_result": assessment.assessment_result},
                "plan": None if plan is None else {"decision_reference": plan.decision_reference, "decision_date": plan.decision_date},
                "outcome": None if outcome is None else {
                    "outcome_result": outcome.outcome_result,
                    "final_evaluation": outcome.final_evaluation,
                    "minutes_recorded_on": outcome.minutes_recorded_on,
                    "minutes_recorded_time": outcome.minutes_recorded_time,
                    "compliance_due_on": outcome.compliance_due_on,
                    "decision_reference": outcome.decision_reference,
                    "bbkt_reference": outcome.bbkt_reference,
                },
            }
        report = build_comparison_plan(rows, canonical)
        report["read_only_connection"] = {"database": REHEARSAL_DATABASE, "revision": REQUIRED_REVISION, "transaction_read_only": True}
        return report
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile db.ktra facts and verify a future read-only reconciliation target.")
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--profile-output", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--plan-output", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--contamination-output", type=Path, default=DEFAULT_CONTAMINATION)
    parser.add_argument("--compare-rehearsal", action="store_true")
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    args = parser.parse_args(argv)
    rows = load_snapshot(args.snapshot.resolve())
    profile = profile_rows(rows)
    comparison: dict[str, Any] = {"comparison_status": "NOT_RUN_DATABASE_URL_ABSENT", "guardrails": {"database_mutated": False}}
    if args.compare_rehearsal:
        database_url = os.environ.get(args.database_url_env)
        if not database_url:
            raise RuntimeError(f"--compare-rehearsal requires non-empty environment variable {args.database_url_env}")
        comparison = run_read_only_comparison(database_url, rows)
    for output, payload in ((args.profile_output, profile), (args.plan_output, comparison), (args.contamination_output, {"schema_version": "db-ktra-contamination-report/v1", "comparison": comparison, "guardrails": {"database_mutated": False}})):
        output.resolve().parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
