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
from backend.app.db.models.phase1 import (
    Case,
    CaseApplication,
    CaseAssessment,
    Certificate,
    InspectorProfile,
    InspectionApprovalSubmission,
    InspectionOutcome,
    InspectionPlan,
    InspectionTeam,
    InspectionTeamMember,
    Person,
)


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
    for key in ("decision_reference", "decision_date", "recorded_on", "recorded_time", "precision", "source_format", "value", "legacy_certificate_id", "reference", "submitted_on", "submitted_time"):
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
    team_morphology: Counter[str] = Counter()
    team_member_counts: Counter[int] = Counter()
    for row in valid:
        raw = str(row.get("T.tra viên") or "").strip()
        if raw in {"", "-", "???"}:
            continue
        markers = "+".join(name for name, marker in (("comma", ","), ("newline", "\n"), ("semicolon", ";"), ("slash", "/")) if marker in raw) or "none"
        team_morphology[markers] += 1
        parsed = parse_legacy_team(raw)
        if parsed["state"] == "KNOWN":
            team_member_counts[len(parsed["members"])] += 1
    return {
        "schema_version": "db-ktra-parser-profile/v1",
        "source": {"snapshot_path": "artifacts/phase3c/legacy_snapshot.json", "snapshot_artifact_sha256": CANONICAL_SNAPSHOT_ARTIFACT_SHA256},
        "valid_legacy_rows": len(valid),
        "fields": fields,
        "team_segmentation": {"delimiter_counts": dict(sorted(team_morphology.items())), "candidate_member_count_distribution": dict(sorted(team_member_counts.items()))},
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


def _safe_current(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    return safe_evidence(value.isoformat() if hasattr(value, "isoformat") else value)


def _classification(source_state: str, source: object, current: object) -> str:
    if source_state != "KNOWN":
        return "MISSING_SOURCE" if source_state == "MISSING" else "BLOCKED_PARSE"
    if current is None:
        return "SAFE_DIRECT"
    return "ALREADY_MATCHES" if current == source else "BLOCKED_EXISTING_CANONICAL_CONFLICT"


def _fact(legacy_id: int, case: dict[str, Any], name: str, parsed: dict[str, Any], value: object, current: object, owner: str, reason: str) -> dict[str, Any]:
    raw = str(parsed.get("raw") or "")
    evidence = safe_evidence(raw)
    classification = _classification(str(parsed["state"]), value, current)
    return {
        "legacy_row": legacy_id, "legacy_case_id": legacy_id, "canonical_case_id": case["id"],
        "fact": name, "source_state": parsed["state"], **evidence,
        "parsed_value": _safe_value(parsed), "current_canonical_value": _safe_current(current),
        "classification": classification, "reason": reason,
        "future_action": "write_structured_owner" if classification == "SAFE_DIRECT" else "none", "target_owner": owner,
    }


def _contamination_fact(legacy_id: int, case: dict[str, Any], name: str, parsed: dict[str, Any], source: object, current: object, owner: str, reason: str) -> dict[str, Any]:
    if current is None:
        classification = "TARGET_NULL"
    elif parsed["state"] == "KNOWN" and current == source:
        classification = "CONTAMINATED_EXACT_COPY"
    else:
        classification = "TARGET_DIFFERENT"
    return {
        **_fact(legacy_id, case, name, parsed, source, current, owner, reason),
        "classification": classification, "future_action": "review_only",
    }


def _approval_fact(legacy_id: int, case: dict[str, Any], stage: str, parsed: dict[str, Any]) -> dict[str, Any]:
    current = (case.get("submissions") or {}).get(stage)
    if parsed["state"] != "KNOWN":
        classification = "MISSING_SOURCE" if parsed["state"] == "MISSING" else "BLOCKED_PARSE"
    elif current is None:
        classification = "SAFE_SUBMISSION_FACT"
    elif all(current.get(key) == parsed.get(key) for key in ("reference", "submitted_on", "submitted_time")):
        classification = "ALREADY_MATCHES"
    else:
        classification = "BLOCKED_EXISTING_CANONICAL_CONFLICT"
    blocker = "completion and parent linkage are not inferred from legacy source"
    if stage == "CT" and parsed["state"] == "KNOWN":
        classification = "BLOCKED_PARENT_RELATION" if current is None else classification
        blocker = "CT parent relation is not inferred from legacy source"
    return {
        **_fact(legacy_id, case, f"{stage.lower()}_submission", parsed, parsed.get("reference"), None if current is None else current.get("reference"), "InspectionApprovalSubmission", blocker),
        "classification": classification, "future_action": "review_only" if classification.startswith("BLOCKED") else "write_structured_owner",
    }


def _team_fact(legacy_id: int, case: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    resolution = case.get("team_resolution") or {}
    if parsed["state"] != "KNOWN":
        classification = "MISSING_SOURCE" if parsed["state"] == "MISSING" else "BLOCKED_PARSE"
    elif resolution.get("ambiguous"):
        classification = "BLOCKED_IDENTITY"
    elif resolution.get("unresolved"):
        classification = "SAFE_DISPLAY_ONLY"
    else:
        classification = "SAFE_ORDERED_EXPANSION"
    return {
        **_fact(legacy_id, case, "inspection_team", parsed, len(parsed.get("members", [])), resolution.get("current_member_count"), "InspectionTeam/InspectionTeamMember", "ordered source names require exact Person or InspectorProfile identity"),
        "classification": classification, "future_action": "review_only" if classification != "SAFE_ORDERED_EXPANSION" else "write_structured_owner",
        "identity_resolution": {key: resolution.get(key, 0) for key in ("resolved", "unresolved", "ambiguous", "current_member_count")},
    }


def _certificate_fact(legacy_id: int, case: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    candidate = case.get("certificate_by_legacy_id")
    certificates = candidate if isinstance(candidate, list) else ([] if candidate is None else [candidate])
    certificate = certificates[0] if len(certificates) == 1 else None
    if parsed["state"] != "KNOWN":
        classification = "MISSING_SOURCE" if parsed["state"] == "MISSING" else "BLOCKED_PARSE"
    elif len(certificates) != 1:
        classification = "BLOCKED_IDENTITY"
    elif certificate.get("case_id") not in {None, case["id"]}:
        classification = "BLOCKED_CASE_MISMATCH"
    elif certificate.get("site_id") != case.get("site_id"):
        classification = "BLOCKED_SITE_MISMATCH"
    elif certificate.get("certificate_type") != case.get("gxp_type"):
        classification = "BLOCKED_TYPE_MISMATCH"
    else:
        classification = "ALREADY_LINKED" if certificate.get("case_id") == case["id"] else "SAFE_LINK"
    return {
        **_fact(legacy_id, case, "certificate_link", parsed, parsed.get("legacy_certificate_id"), None if certificate is None else certificate.get("legacy_certificate_id"), "Certificate", "exact legacy certificate identity with case/site/type checks"),
        "classification": classification, "future_action": "review_only" if classification.startswith("BLOCKED") else "write_structured_owner",
    }


def _team_resolution(parsed: dict[str, Any], identity_index: dict[str, set[str]], current_member_count: int) -> dict[str, int]:
    resolved = unresolved = ambiguous = 0
    for member in parsed.get("members", []):
        matches = identity_index.get(member["display_name"], set())
        if len(matches) == 1:
            resolved += 1
        elif not matches:
            unresolved += 1
        else:
            ambiguous += 1
    return {"resolved": resolved, "unresolved": unresolved, "ambiguous": ambiguous, "current_member_count": current_member_count}


def _contamination_summary(facts: list[dict[str, Any]], fact_name: str) -> dict[str, int]:
    selected = [fact for fact in facts if fact["fact"] == fact_name]
    return {
        "matched_source_rows": len(selected), "target_rows_present": sum(fact["current_canonical_value"] is not None for fact in selected),
        "exact_equality_count": sum(fact["classification"] == "CONTAMINATED_EXACT_COPY" for fact in selected),
        "target_null_count": sum(fact["classification"] == "TARGET_NULL" for fact in selected),
        "differing_count": sum(fact["classification"] == "TARGET_DIFFERENT" for fact in selected),
        "safe_to_clean_later_count": sum(fact["classification"] == "CONTAMINATED_EXACT_COPY" for fact in selected),
        "review_required_count": sum(fact["classification"] != "CONTAMINATED_EXACT_COPY" for fact in selected),
    }


def build_comparison_plan(rows: list[dict[str, Any]], canonical_by_legacy_id: dict[int, dict[str, Any]]) -> dict[str, Any]:
    facts: list[dict[str, Any]] = []
    for row in rows:
        legacy_id = parse_int(row.get("ID", ""))
        if legacy_id is None:
            continue
        case = canonical_by_legacy_id.get(legacy_id)
        if case is None:
            facts.append({"legacy_row": legacy_id, "legacy_case_id": legacy_id, "canonical_case_id": None, "fact": "case_identity", "source_state": "KNOWN", "classification": "BLOCKED_IDENTITY", "reason": "no exact canonical case identity", "future_action": "none", "target_owner": "Case"})
            continue
        outcome, assessment, application, plan = (case.get("outcome") or {}), (case.get("assessment") or {}), (case.get("application") or {}), (case.get("plan") or {})
        result_raw = str(row.get("assessment_result") or "").strip()
        result = {"state": "MISSING" if result_raw in {"", "-", "???"} else "KNOWN", "value": result_raw or None, "raw": result_raw}
        decision = parse_legacy_inspection_decision(row.get("decision_reference"))
        minutes = parse_legacy_minutes_recorded(row.get("bbkt_reference"))
        final = {"state": "MISSING" if str(row.get("ĐÁNH GIÁ CUỐI") or "").strip() in {"", "-", "???"} else "KNOWN", "value": str(row.get("ĐÁNH GIÁ CUỐI") or "").strip() or None, "raw": str(row.get("ĐÁNH GIÁ CUỐI") or "").strip()}
        deadline, team = parse_legacy_date(row.get("HẠN KT TUÂN THỦ")), parse_legacy_team(row.get("T.tra viên"))
        facts.extend([
            _fact(legacy_id, case, "outcome_result", result, result["value"], outcome.get("outcome_result"), "InspectionOutcome.outcome_result", "Kết quả maps only to InspectionOutcome.outcome_result"),
            _contamination_fact(legacy_id, case, "assessment_result_contamination", result, result["value"], assessment.get("assessment_result"), "CaseAssessment.assessment_result", "Kết quả is not a CaseAssessment source"),
            _fact(legacy_id, case, "decision_reference", decision, decision.get("decision_reference"), plan.get("decision_reference"), "InspectionPlan.decision_reference", "Q. định split reference"),
            _fact(legacy_id, case, "decision_date", decision, decision.get("decision_date"), plan.get("decision_date"), "InspectionPlan.decision_date", "Q. định split date"),
            _fact(legacy_id, case, "decision_legacy_raw", decision, decision.get("raw"), plan.get("decision_legacy_raw"), "InspectionPlan.decision_legacy_raw", "raw provenance only"),
            _contamination_fact(legacy_id, case, "application_dossier_reference_contamination", decision, decision.get("decision_reference"), application.get("dossier_reference"), "CaseApplication.dossier_reference", "Q. định is not an application source"),
            _contamination_fact(legacy_id, case, "outcome_decision_reference_contamination", decision, decision.get("decision_reference"), outcome.get("decision_reference"), "InspectionOutcome.decision_reference", "Q. định belongs to InspectionPlan"),
            _fact(legacy_id, case, "minutes_recorded_on", minutes, minutes.get("recorded_on"), outcome.get("minutes_recorded_on"), "InspectionOutcome.minutes_recorded_on", "B. bản minutes date only"),
            _fact(legacy_id, case, "minutes_recorded_time", minutes, minutes.get("recorded_time"), outcome.get("minutes_recorded_time"), "InspectionOutcome.minutes_recorded_time", "B. bản local clock time only"),
            _contamination_fact(legacy_id, case, "outcome_bbkt_reference_contamination", minutes, minutes.get("raw"), outcome.get("bbkt_reference"), "InspectionOutcome.bbkt_reference", "B. bản raw compatibility field is report-only"),
            _fact(legacy_id, case, "final_evaluation", final, final["value"], outcome.get("final_evaluation"), "InspectionOutcome.final_evaluation", "ĐÁNH GIÁ CUỐI remains distinct from Kết quả"),
            _fact(legacy_id, case, "compliance_due_on", deadline, deadline.get("value"), outcome.get("compliance_due_on"), "InspectionOutcome.compliance_due_on", "HẠN KT TUÂN THỦ date only"),
            _team_fact(legacy_id, case, team),
            _approval_fact(legacy_id, case, "PCT", parse_legacy_approval_submission(row.get("PHIẾU TRÌNH PCT"))),
            _approval_fact(legacy_id, case, "CT", parse_legacy_approval_submission(row.get("PHIẾU TRÌNH CT"))),
            _certificate_fact(legacy_id, case, parse_legacy_certificate_id(row.get("ID CC GPs"))),
        ])
    return {"schema_version": "db-ktra-reconciliation-plan/v1", "comparison_status": "COMPARED", "facts": facts, "summary": {"legacy_rows": sum(1 for row in rows if parse_int(row.get("ID", "")) is not None), "classification_counts": dict(Counter(fact["classification"] for fact in facts))}, "contamination": {name: _contamination_summary(facts, name) for name in ("assessment_result_contamination", "application_dossier_reference_contamination", "outcome_decision_reference_contamination", "outcome_bbkt_reference_contamination")}, "guardrails": {"database_mutated": False, "write_plan_only": True}}


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
        usable_ids = {value for value in legacy_ids if value is not None}
        cases = list(session.scalars(select(Case).where(Case.legacy_inspection_id.in_(usable_ids))))
        case_ids = {case.id for case in cases}
        applications = {item.case_id: item for item in session.scalars(select(CaseApplication).where(CaseApplication.case_id.in_(case_ids)))}
        assessments = {item.case_id: item for item in session.scalars(select(CaseAssessment).where(CaseAssessment.case_id.in_(case_ids)))}
        plans = {item.case_id: item for item in session.scalars(select(InspectionPlan).where(InspectionPlan.case_id.in_(case_ids)))}
        outcomes = {item.case_id: item for item in session.scalars(select(InspectionOutcome).where(InspectionOutcome.case_id.in_(case_ids)))}
        teams = {item.case_id: item for item in session.scalars(select(InspectionTeam).where(InspectionTeam.case_id.in_(case_ids)))}
        team_ids = {team.id for team in teams.values()}
        team_members: dict[str, list[InspectionTeamMember]] = defaultdict(list)
        for item in session.scalars(select(InspectionTeamMember).where(InspectionTeamMember.team_id.in_(team_ids))):
            team_members[item.team_id].append(item)
        submissions: dict[str, dict[str, InspectionApprovalSubmission]] = defaultdict(dict)
        for item in session.scalars(select(InspectionApprovalSubmission).where(InspectionApprovalSubmission.case_id.in_(case_ids))):
            if item.round_no == 1:
                submissions[item.case_id][item.stage] = item
        certificate_ids = {parse_legacy_certificate_id(row.get("ID CC GPs")).get("legacy_certificate_id") for row in rows}
        certificates: dict[int, list[Certificate]] = defaultdict(list)
        for item in session.scalars(select(Certificate).where(Certificate.legacy_certificate_id.in_({value for value in certificate_ids if value is not None}))):
            if item.legacy_certificate_id is not None:
                certificates[item.legacy_certificate_id].append(item)
        identity_index: dict[str, set[str]] = defaultdict(set)
        for person in session.scalars(select(Person)):
            identity_index[person.full_name].add(person.id)
            if person.display_name:
                identity_index[person.display_name].add(person.id)
        for profile in session.scalars(select(InspectorProfile)):
            if profile.legacy_display_text:
                identity_index[profile.legacy_display_text].add(profile.person_id)
        canonical: dict[int, dict[str, Any]] = {}
        for case in cases:
            application, assessment, plan, outcome = applications.get(case.id), assessments.get(case.id), plans.get(case.id), outcomes.get(case.id)
            team = teams.get(case.id)
            canonical[case.legacy_inspection_id] = {
                "id": case.id, "site_id": case.site_id, "gxp_type": case.gxp_type,
                "application": None if application is None else {"dossier_reference": application.dossier_reference},
                "assessment": None if assessment is None else {"assessment_result": assessment.assessment_result},
                "plan": None if plan is None else {"decision_reference": plan.decision_reference, "decision_date": plan.decision_date, "decision_legacy_raw": plan.decision_legacy_raw},
                "submissions": {stage: {"reference": item.reference, "submitted_on": item.submitted_on, "submitted_time": item.submitted_time} for stage, item in submissions.get(case.id, {}).items()},
                "team_resolution": {"resolved": 0, "unresolved": 0, "ambiguous": 0, "current_member_count": len(team_members.get(team.id, [])) if team else 0},
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
        for row in rows:
            legacy_id = parse_int(row.get("ID", ""))
            case = canonical.get(legacy_id) if legacy_id is not None else None
            if case is None:
                continue
            case["team_resolution"] = _team_resolution(parse_legacy_team(row.get("T.tra viên")), identity_index, case["team_resolution"]["current_member_count"])
            parsed_certificate = parse_legacy_certificate_id(row.get("ID CC GPs"))
            certificate_rows = certificates.get(parsed_certificate.get("legacy_certificate_id"), [])
            case["certificate_by_legacy_id"] = [{"legacy_certificate_id": item.legacy_certificate_id, "case_id": item.case_id, "site_id": item.site_id, "certificate_type": item.certificate_type} for item in certificate_rows]
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
