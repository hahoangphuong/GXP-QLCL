"""Read-only Batch 5 evidence audit for residual ``db.ktra`` semantics.

The tool deliberately has no snapshot-only approximation of canonical state.
It emits residual artifacts only after a guarded PostgreSQL rehearsal read.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import (
    Case, CaseApplication, CaseAssessment, Certificate, InspectorProfile,
    InspectionApprovalSubmission, InspectionOutcome, InspectionPlan, Person, Site,
)
from backend.app.domain.legacy_db_ktra_reconciliation import (
    parse_legacy_approval_submission, parse_legacy_certificate_id,
    parse_legacy_date, parse_legacy_inspection_decision, parse_legacy_minutes_recorded,
    parse_legacy_team, safe_evidence,
)
from backend.app.domain.phase2_import import normalize_inspection_gxp_type, parse_int
from tools.plan_db_ktra_reconciliation import (
    REHEARSAL_DATABASE, REQUIRED_REVISION, SNAPSHOT, load_snapshot,
    validate_rehearsal_target, verify_read_only_connection,
)
from tools.profile_legacy_semantics import CANONICAL_SNAPSHOT_ARTIFACT_SHA256


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESIDUAL = ROOT / "artifacts" / "legacy_audit" / "db_ktra_residual_audit_v1.json"
DEFAULT_IDENTITY = ROOT / "artifacts" / "legacy_audit" / "db_ktra_blocked_identity_v1.json"
DEFAULT_PARSER = ROOT / "artifacts" / "legacy_audit" / "db_ktra_blocked_parser_v1.json"
TOOL_VERSION = "db-ktra-residual-audit/v1"

RESIDUAL_SPECS = {
    "assessment_result": ("assessment_result", "outcome_result", "CaseAssessment.assessment_result"),
    "application_dossier_reference": ("decision_reference", "plan_decision_legacy_raw", "CaseApplication.dossier_reference"),
    "outcome_decision_reference": ("decision_reference", "plan_decision_legacy_raw", "InspectionOutcome.decision_reference"),
    "outcome_bbkt_reference": ("bbkt_reference", "minutes_legacy_raw", "InspectionOutcome.bbkt_reference"),
}


def _shape(value: object) -> str:
    text_value = "" if value is None else str(value)
    return "".join("9" if char.isdigit() else "A" if char.isalpha() else char for char in text_value)


def _safe_value(value: object) -> dict[str, Any] | None:
    if value is None:
        return None
    return {**safe_evidence(value.isoformat() if hasattr(value, "isoformat") else value), "shape": _shape(value)}


def _source_parser(domain: str, row: dict[str, Any]) -> dict[str, Any]:
    if domain == "assessment_result":
        raw = str(row.get("assessment_result") or "").strip()
        return {"state": "MISSING" if raw in {"", "-", "???"} else "KNOWN", "raw": raw, "value": raw or None}
    if domain in {"application_dossier_reference", "outcome_decision_reference"}:
        return parse_legacy_inspection_decision(row.get("decision_reference"))
    return parse_legacy_minutes_recorded(row.get("bbkt_reference"))


def _source_raw(parsed: dict[str, Any]) -> object:
    return parsed.get("raw")


def classify_residual(*, parsed: dict[str, Any], current: object, canonical: object) -> str:
    """Classify without fuzzy or normalization-based contamination inference."""
    if current is None:
        return "CANONICAL_LEGITIMATE"
    if parsed["state"] == "MISSING":
        return "SOURCE_MISSING"
    if parsed["state"] != "KNOWN":
        return "SOURCE_PARSE_BLOCKED"
    if current == _source_raw(parsed):
        # The Phase 2 importer wrote this exact raw source into compatibility fields.
        return "TRANSFORMED_CONTAMINATION_PROVEN"
    if canonical is not None and current == canonical:
        return "OWNER_DUPLICATE"
    return "CURRENT_VALUE_UNEXPLAINED"


def parser_morphology(parser_name: str, parsed: dict[str, Any]) -> str:
    raw = str(parsed.get("raw") or "")
    if parsed["state"] == "MISSING":
        return "MISSING"
    if parsed["state"] == "KNOWN":
        return "KNOWN"
    if parsed["state"] == "UNRESOLVED":
        if ";" in raw or "\n" in raw:
            return "MULTIPLE_REFERENCES_OR_DATES"
        return "UNRESOLVED_AMBIGUITY"
    if parser_name == "decision" and not any(char.isdigit() for char in raw):
        return "TEXTUAL_ANNOTATION_OR_REFERENCE_ONLY"
    if any(char.isdigit() for char in raw):
        return "PARTIAL_OR_MALFORMED_DATE"
    return "TEXTUAL_ANNOTATION_OR_REFERENCE_ONLY"


def _identity_row(row: dict[str, Any], cases_by_legacy_id: dict[int, dict[str, Any]], cases_by_site_and_type: dict[tuple[int | None, str], list[dict[str, Any]]]) -> dict[str, Any] | None:
    legacy_id = parse_int(row.get("ID", ""))
    if legacy_id is None or legacy_id in cases_by_legacy_id:
        return None
    site_legacy_id = parse_int(row.get("site_legacy_id_ref", ""))
    gxp_type = normalize_inspection_gxp_type(row.get("inspection_gxp_type"))
    candidates = cases_by_site_and_type.get((site_legacy_id, gxp_type or ""), [])
    if not candidates:
        classification = "NO_CANONICAL_CASE"
    elif len(candidates) == 1:
        # Site/type is supporting evidence, not an alternate stable inspection ID.
        classification = "MANUAL_REVIEW"
    else:
        classification = "MULTIPLE_CANDIDATES"
    return {
        "legacy_inspection_id": legacy_id,
        "source_site_legacy_id": site_legacy_id,
        "source_gxp_type": gxp_type,
        "source_date_shapes": {"inspection": _shape(row.get("inspected_at")), "submission": _shape(row.get("submitted_at"))},
        "classification": classification,
        "exact_candidate_count": len(candidates),
    }


def _residual_rows(rows: list[dict[str, Any]], live: dict[int, dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    report: dict[str, list[dict[str, Any]]] = {key: [] for key in RESIDUAL_SPECS}
    for row in rows:
        legacy_id = parse_int(row.get("ID", ""))
        case = live.get(legacy_id) if legacy_id is not None else None
        if case is None:
            continue
        for domain, (_source, canonical_key, _owner) in RESIDUAL_SPECS.items():
            current = case.get(domain)
            if current is None:
                continue
            parsed = _source_parser(domain, row)
            category = classify_residual(parsed=parsed, current=current, canonical=case.get(canonical_key))
            report[domain].append({
                "legacy_inspection_id": legacy_id,
                "canonical_case_id": case["id"],
                "classification": category,
                "current": _safe_value(current),
                "source": _safe_value(_source_raw(parsed)),
                "canonical_owner": _safe_value(case.get(canonical_key)),
                "normalization_proof": "NONE_EXACT_COMPARISON_ONLY",
                "historical_transformation_owner": "phase2_import.import_db_ktra exact raw compatibility copy" if category == "TRANSFORMED_CONTAMINATION_PROVEN" else None,
            })
    return ({name: {"count": len(items), "classification_counts": dict(sorted(Counter(item["classification"] for item in items).items())), "rows": items} for name, items in report.items()}, [])


def _parser_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected = {
        "decision": ("Q. định", lambda row: parse_legacy_inspection_decision(row.get("decision_reference"))),
        "minutes": ("B. bản", lambda row: parse_legacy_minutes_recorded(row.get("bbkt_reference"))),
        "deadline": ("HẠN KT TUÂN THỦ", lambda row: parse_legacy_date(row.get("HẠN KT TUÂN THỦ"))),
    }
    result: dict[str, Any] = {}
    for key, (label, parser) in selected.items():
        blocked: list[dict[str, Any]] = []
        counts: Counter[str] = Counter()
        for row in rows:
            legacy_id = parse_int(row.get("ID", ""))
            if legacy_id is None:
                continue
            parsed = parser(row)
            morphology = parser_morphology(key, parsed)
            counts[morphology] += 1
            if parsed["state"] not in {"KNOWN", "MISSING"}:
                blocked.append({"legacy_inspection_id": legacy_id, "state": parsed["state"], "morphology": morphology, **_safe_value(parsed.get("raw"))})
        result[label] = {"morphology_counts": dict(sorted(counts.items())), "blocked_rows": blocked}
    return result


def _team_matrix(rows: list[dict[str, Any]], live: dict[int, dict[str, Any]], person_count: int, profile_count: int) -> dict[str, Any]:
    members = 0
    states: Counter[str] = Counter()
    for row in rows:
        legacy_id = parse_int(row.get("ID", ""))
        parsed = parse_legacy_team(row.get("T.tra viên"))
        if legacy_id is None or parsed["state"] != "KNOWN":
            continue
        for member in parsed["members"]:
            members += 1
            states[live.get(legacy_id, {}).get("team_member_states", {}).get(member["display_name"], "UNRESOLVED")] += 1
    return {
        "identity_sources": {"person_rows": person_count, "inspector_profile_rows": profile_count, "matching_policy": "EXACT_SOURCE_DISPLAY_TEXT_ONLY"},
        "legacy_candidate_members": members,
        "resolution_counts": dict(sorted(states.items())),
        "conclusion": "PERSONNEL_MIGRATION_REQUIRED" if states.get("UNRESOLVED", 0) else "EXACT_IDENTITY_AVAILABLE",
    }


def _integrity(rows: list[dict[str, Any]], live: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Verify post-apply fields against the same source parsers used by Batch 4."""
    mismatches: list[dict[str, Any]] = []

    def mismatch(legacy_id: int, check: str) -> None:
        mismatches.append({"legacy_inspection_id": legacy_id, "check": check})

    for row in rows:
        legacy_id = parse_int(row.get("ID", ""))
        case = live.get(legacy_id) if legacy_id is not None else None
        if case is None:
            continue
        decision = parse_legacy_inspection_decision(row.get("decision_reference"))
        if decision["state"] == "KNOWN":
            if (case.get("plan_decision_reference"), case.get("plan_decision_date"), case.get("plan_decision_legacy_raw")) != (decision.get("decision_reference"), decision.get("decision_date"), decision.get("raw")):
                mismatch(legacy_id, "decision_typed_owner")
            if case.get("application_dossier_reference") == decision.get("raw") or case.get("outcome_decision_reference") == decision.get("raw"):
                mismatch(legacy_id, "decision_exact_copy_compatibility_not_cleared")
        minutes = parse_legacy_minutes_recorded(row.get("bbkt_reference"))
        if minutes["state"] == "KNOWN":
            if (case.get("minutes_recorded_on"), case.get("minutes_recorded_time"), case.get("minutes_legacy_raw")) != (minutes.get("recorded_on"), minutes.get("recorded_time"), minutes.get("raw")):
                mismatch(legacy_id, "minutes_typed_owner")
            if case.get("outcome_bbkt_reference") == minutes.get("raw"):
                mismatch(legacy_id, "minutes_exact_copy_compatibility_not_cleared")
        result = str(row.get("assessment_result") or "").strip()
        if result not in {"", "-", "???"}:
            if case.get("outcome_result") != result:
                mismatch(legacy_id, "outcome_result_source_value")
            if case.get("assessment_result") == result:
                mismatch(legacy_id, "assessment_exact_copy_not_cleared")
        final = str(row.get("final_evaluation") or "").strip()
        if final not in {"", "-", "???"} and case.get("final_evaluation") != final:
            mismatch(legacy_id, "final_evaluation_source_value")
        deadline = parse_legacy_date(row.get("compliance_due_on"))
        if deadline["state"] == "KNOWN" and case.get("compliance_due_on") != deadline.get("value"):
            mismatch(legacy_id, "compliance_due_on_source_value")
    return {
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "inspection_period_fields": "POST_STATE_ONLY_REQUIRES_PRE_APPLY_EVIDENCE_FOR_NON_MUTATION_PROOF",
        "workflow_side_effects": "NOT_INFERRED_FROM_READ_ONLY_ROW_COMPARISON",
    }


def build_audit(rows: list[dict[str, Any]], live: dict[int, dict[str, Any]], *, cases_by_site_and_type: dict[tuple[int | None, str], list[dict[str, Any]]], person_count: int, profile_count: int) -> dict[str, Any]:
    residual, _ = _residual_rows(rows, live)
    identities = [item for row in rows if (item := _identity_row(row, live, cases_by_site_and_type)) is not None]
    parser = _parser_profile(rows)
    approvals: dict[str, Counter[str]] = {"PCT": Counter(), "CT": Counter()}
    certificate_anomalies: list[dict[str, Any]] = []
    for row in rows:
        legacy_id = parse_int(row.get("ID", ""))
        if legacy_id is None:
            continue
        pct, ct = parse_legacy_approval_submission(row.get("pct_submission")), parse_legacy_approval_submission(row.get("ct_submission"))
        if pct["state"] == "KNOWN":
            approvals["PCT"]["SINGLE_UNORDERED_SUBMISSION"] += 1
            approvals["PCT"]["COMPLETION_EVIDENCE_ABSENT"] += 1
        if ct["state"] == "KNOWN":
            approvals["CT"]["EXACTLY_ONE_PCT_SOURCE_CANDIDATE" if pct["state"] == "KNOWN" else "LACKS_PCT_SOURCE"] += 1
            approvals["CT"]["EXPLICIT_PARENT_REFERENCE_ABSENT"] += 1
        certificate = live.get(legacy_id, {}).get("certificate_anomaly")
        if certificate:
            certificate_anomalies.append({"legacy_inspection_id": legacy_id, **certificate})
    return {
        "schema_version": "db-ktra-residual-audit/v1",
        "tool_version": TOOL_VERSION,
        "snapshot_provenance_sha256": CANONICAL_SNAPSHOT_ARTIFACT_SHA256,
        "residual_compatibility": residual,
        "blocked_identity": {"count": len(identities), "rows": identities},
        "blocked_parser": parser,
        "team_identity_source_matrix": _team_matrix(rows, live, person_count, profile_count),
        "approval_source_semantics": {stage: dict(sorted(counts.items())) for stage, counts in approvals.items()},
        "certificate_anomalies": certificate_anomalies,
        "batch4_post_state_integrity": _integrity(rows, live),
        "guardrails": {"database_mutated": False, "fuzzy_matching_used": False, "importer_invoked": False},
    }


def _read_live(database_url: str, rows: list[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], dict[tuple[int | None, str], list[dict[str, Any]]], int, int]:
    validate_rehearsal_target(database_url)
    engine = create_engine(database_url)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False, expire_on_commit=False)
    try:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        verify_read_only_connection(connection)
        legacy_ids = {value for row in rows if (value := parse_int(row.get("ID", ""))) is not None}
        cases = list(session.scalars(select(Case)))
        sites = {item.id: item for item in session.scalars(select(Site))}
        case_ids = {case.id for case in cases}
        applications = {item.case_id: item for item in session.scalars(select(CaseApplication).where(CaseApplication.case_id.in_(case_ids)))}
        assessments = {item.case_id: item for item in session.scalars(select(CaseAssessment).where(CaseAssessment.case_id.in_(case_ids)))}
        outcomes = {item.case_id: item for item in session.scalars(select(InspectionOutcome).where(InspectionOutcome.case_id.in_(case_ids)))}
        plans = {item.case_id: item for item in session.scalars(select(InspectionPlan).where(InspectionPlan.case_id.in_(case_ids)))}
        certificates: dict[int, list[Certificate]] = defaultdict(list)
        requested_certificates = {parse_legacy_certificate_id(row.get("ID CC GPs")).get("legacy_certificate_id") for row in rows}
        for certificate in session.scalars(select(Certificate).where(Certificate.legacy_certificate_id.in_({value for value in requested_certificates if value is not None}))):
            if certificate.legacy_certificate_id is not None:
                certificates[certificate.legacy_certificate_id].append(certificate)
        people = list(session.scalars(select(Person)))
        profiles = list(session.scalars(select(InspectorProfile)))
        identity_index: dict[str, set[str]] = defaultdict(set)
        for person in people:
            identity_index[person.full_name].add(f"person:{person.id}")
            if person.display_name:
                identity_index[person.display_name].add(f"person:{person.id}")
        for profile in profiles:
            if profile.legacy_display_text:
                identity_index[profile.legacy_display_text].add(f"profile:{profile.id}")
        live: dict[int, dict[str, Any]] = {}
        by_site_type: dict[tuple[int | None, str], list[dict[str, Any]]] = defaultdict(list)
        for case in cases:
            site = sites.get(case.site_id)
            candidate = {"id": case.id, "legacy_inspection_id": case.legacy_inspection_id, "site_legacy_id": None if site is None else site.legacy_site_id, "gxp_type": case.gxp_type}
            by_site_type[(candidate["site_legacy_id"], case.gxp_type)].append(candidate)
            if case.legacy_inspection_id not in legacy_ids:
                continue
            application, assessment, outcome, plan = applications.get(case.id), assessments.get(case.id), outcomes.get(case.id), plans.get(case.id)
            live[case.legacy_inspection_id] = {
                **candidate,
                "state": case.state,
                "assessment_result": None if assessment is None else assessment.assessment_result,
                "outcome_result": None if outcome is None else outcome.outcome_result,
                "application_dossier_reference": None if application is None else application.dossier_reference,
                "outcome_decision_reference": None if outcome is None else outcome.decision_reference,
                "plan_decision_legacy_raw": None if plan is None else plan.decision_legacy_raw,
                "plan_decision_reference": None if plan is None else plan.decision_reference,
                "plan_decision_date": None if plan is None else plan.decision_date,
                "outcome_bbkt_reference": None if outcome is None else outcome.bbkt_reference,
                "minutes_legacy_raw": None if outcome is None else outcome.minutes_legacy_raw,
                "minutes_recorded_on": None if outcome is None else outcome.minutes_recorded_on,
                "minutes_recorded_time": None if outcome is None else outcome.minutes_recorded_time,
                "final_evaluation": None if outcome is None else outcome.final_evaluation,
                "compliance_due_on": None if outcome is None else outcome.compliance_due_on,
                "team_member_states": {},
                "certificate_anomaly": None,
            }
        for row in rows:
            legacy_id = parse_int(row.get("ID", ""))
            case = live.get(legacy_id) if legacy_id is not None else None
            if case is None:
                continue
            for member in parse_legacy_team(row.get("T.tra viên")).get("members", []):
                matches = identity_index.get(member["display_name"], set())
                case["team_member_states"][member["display_name"]] = "UNRESOLVED" if not matches else "AMBIGUOUS" if len(matches) > 1 else "EXACT_RESOLVED"
            certificate_id = parse_legacy_certificate_id(row.get("ID CC GPs")).get("legacy_certificate_id")
            candidates = certificates.get(certificate_id, [])
            if certificate_id is not None and (len(candidates) != 1 or (candidates and candidates[0].case_id not in {None, case["id"]}) or (candidates and candidates[0].site_id != case["site_id"])):
                case["certificate_anomaly"] = {"legacy_certificate_id": certificate_id, "canonical_certificate_identity_count": len(candidates), "source_case_id": case["id"], "canonical_case_id": None if len(candidates) != 1 else candidates[0].case_id, "site_relation": "MATCH" if len(candidates) == 1 and candidates[0].site_id == case["site_id"] else "MISMATCH_OR_UNRESOLVED", "source_gxp_type": case["gxp_type"], "canonical_gxp_type": None if len(candidates) != 1 else candidates[0].certificate_type}
        return live, by_site_type, len(people), len(profiles)
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a read-only db.ktra residual semantic audit.")
    parser.add_argument("--compare-rehearsal", action="store_true", required=True)
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--residual-output", type=Path, default=DEFAULT_RESIDUAL)
    parser.add_argument("--identity-output", type=Path, default=DEFAULT_IDENTITY)
    parser.add_argument("--parser-output", type=Path, default=DEFAULT_PARSER)
    args = parser.parse_args(argv)
    database_url = os.environ.get(args.database_url_env)
    if not database_url:
        raise RuntimeError(f"--compare-rehearsal requires non-empty environment variable {args.database_url_env}")
    rows = load_snapshot(args.snapshot.resolve())
    live, by_site_type, person_count, profile_count = _read_live(database_url, rows)
    report = build_audit(rows, live, cases_by_site_and_type=by_site_type, person_count=person_count, profile_count=profile_count)
    report["read_only_connection"] = {"database": REHEARSAL_DATABASE, "revision": REQUIRED_REVISION, "transaction_read_only": True}
    outputs = ((args.residual_output, report), (args.identity_output, report["blocked_identity"]), (args.parser_output, report["blocked_parser"]))
    for output, payload in outputs:
        output.resolve().parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
