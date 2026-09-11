from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import (
    Case,
    CaseApplication,
    CaseAssessment,
    CapaCycle,
    Certificate,
    CertificateVersion,
    InspectionOutcome,
    InspectionPlan,
    InspectionTeam,
    InspectionTeamMember,
    LegacyIdMap,
)
from backend.app.db.session import build_engine
from backend.app.domain.legacy_snapshot import read_core_sheet_rows
from backend.app.domain.phase2_import import normalize_row, parse_date
from tools.audit_inspection_case_lifecycle_legacy import (
    _classify_decision_composite,
    _date_morphology,
    _fold,
    _shape,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "legacy_audit" / "inspection_case_lifecycle_reconciliation_plan.json"
REQUIRED_DATABASE_NAME = "gxp_legacy_rehearsal"
PLAN_STATUS = {
    "SAFE_NOOP",
    "SAFE_INSERT",
    "SAFE_UPDATE_IF_EMPTY",
    "ALREADY_MATCHES",
    "CONFLICT_EXISTING_CANONICAL",
    "BLOCKED_AMBIGUOUS_LEGACY",
    "BLOCKED_OWNER_MISSING",
    "BLOCKED_OWNER_MISMATCH",
    "BLOCKED_PROVENANCE_CONTAMINATION",
    "MANUAL_RECONCILIATION_REQUIRED",
}


def require_rehearsal_database(database_url: str) -> None:
    parsed = urlsplit(database_url)
    database_name = parsed.path.rsplit("/", 1)[-1]
    if parsed.scheme not in {"postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
        raise RuntimeError("reconciliation planner requires a PostgreSQL rehearsal database URL")
    if database_name != REQUIRED_DATABASE_NAME:
        raise RuntimeError(f"reconciliation planner refuses database {database_name!r}; expected rehearsal database")


def _hash(value: str | None) -> str | None:
    text_value = str(value or "").strip()
    return sha256(text_value.encode("utf-8")).hexdigest() if text_value else None


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() not in {"", "-", "???"}


def _candidate_status(candidate: Any, current: Any) -> str:
    if not _present(candidate):
        return "BLOCKED_AMBIGUOUS_LEGACY"
    if not _present(current):
        return "SAFE_INSERT"
    return "ALREADY_MATCHES" if candidate == current else "CONFLICT_EXISTING_CANONICAL"


def _split_decision(value: str) -> tuple[str | None, str | None, str]:
    status = _classify_decision_composite(value)
    if status != "reference_plus_trailing_date":
        return None, None, status
    match = re.search(r"(?P<date>\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s*$", value.strip())
    if not match:
        return None, None, "malformed_or_ambiguous"
    reference = value[: match.start()].strip(" \t\r\n,;:-")
    parsed = parse_date(match.group("date"))
    return reference, None if parsed is None else parsed.isoformat(), "deterministic_reference_date_split" if parsed else "malformed_or_ambiguous"


def _period_start_end(value: str) -> tuple[date | None, date | None]:
    direct = parse_date(value)
    if direct is not None:
        return direct, direct
    text_value = str(value or "").strip()
    match = re.fullmatch(r"(\d{1,2})\s*/\s*(\d{1,2})\s*-\s*(\d{1,2})\s*/\s*(\d{1,2})[./-](\d{2,4})", text_value)
    if match:
        first_day, first_month, last_day, last_month, year = (int(part) for part in match.groups())
        if year < 100:
            year += 2000
        try:
            return date(year, first_month, first_day), date(year, last_month, last_day)
        except ValueError:
            return None, None
    match = re.fullmatch(r"(\d{1,2})\s*-\s*(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", text_value)
    if match:
        first, last, month, year = (int(part) for part in match.groups())
        if year < 100:
            year += 2000
        try:
            return date(year, month, first), date(year, month, last)
        except ValueError:
            return None, None
    return None, None


def _date_reconciliation(legacy_value: str, current_start: date | None, current_end: date | None) -> tuple[str, str, str | None]:
    morphology = _date_morphology(legacy_value)
    start, end = _period_start_end(legacy_value)
    if start is None:
        return morphology, "BLOCKED_AMBIGUOUS_LEGACY", None
    if current_start == start and (current_end in {None, end}):
        return morphology, "ALREADY_MATCHES", start.isoformat()
    if current_start is None:
        return morphology, "SAFE_INSERT", start.isoformat()
    return morphology, "CONFLICT_EXISTING_CANONICAL", start.isoformat()


def _misrouting_status(legacy_value: str, current_value: Any, source_key: str) -> str:
    if not _present(current_value):
        return "NOT_MATCHING_MISROUTED_SOURCE"
    if source_key in {"decision_reference", "bbkt_reference"}:
        return "POSSIBLE_LEGACY_MISROUTED"
    return "NOT_MATCHING_MISROUTED_SOURCE"


def _fact(case_id: str | None, legacy_id: int, key: str, source: str, status: str, *, candidate: Any = None, current: Any = None, provenance_status: str = "NOT_ASSESSED", blocker: str | None = None) -> dict[str, Any]:
    return {
        "legacy_inspection_id": legacy_id,
        "case_id": case_id,
        "canonical_fact": key,
        "legacy_source": source,
        "legacy_morphology": _date_morphology(str(candidate)) if key.endswith("_on") and candidate is not None else _shape(str(candidate or "")),
        "current_value_present": _present(current),
        "candidate_available": _present(candidate),
        "candidate_sha256": _hash(str(candidate)) if candidate is not None and not isinstance(candidate, (date, int, float, bool)) else None,
        "candidate_value": candidate if isinstance(candidate, (date, type(None))) else None,
        "reconciliation_status": status,
        "provenance_status": provenance_status,
        "blocker": blocker,
        "recommended_future_action": "manual_review" if status in {"MANUAL_RECONCILIATION_REQUIRED", "BLOCKED_PROVENANCE_CONTAMINATION", "CONFLICT_EXISTING_CANONICAL"} else ("write_structured_owner" if status in {"SAFE_INSERT", "SAFE_UPDATE_IF_EMPTY"} else "no_write"),
    }


def _row_id(row: dict[str, str]) -> int | None:
    try:
        return int(float(str(row.get("ID", "")).strip()))
    except (TypeError, ValueError):
        return None


def build_reconciliation_plan(legacy_rows: list[dict[str, str]], canonical_cases: list[dict[str, Any]]) -> dict[str, Any]:
    case_by_legacy: dict[int, list[dict[str, Any]]] = {}
    for case in canonical_cases:
        legacy_id = case.get("legacy_inspection_id")
        if legacy_id is not None:
            case_by_legacy.setdefault(int(legacy_id), []).append(case)

    facts: list[dict[str, Any]] = []
    identity_counts = Counter()
    for raw in legacy_rows:
        row = normalize_row(raw)
        legacy_id = _row_id(row)
        if legacy_id is None:
            continue
        matches = case_by_legacy.get(legacy_id, [])
        if not matches:
            identity_counts["unmatched"] += 1
            facts.append(_fact(None, legacy_id, "case_identity", "db.ktra.ID", "CASE_NOT_FOUND", blocker="no unique Case.legacy_inspection_id match"))
            continue
        if len(matches) != 1:
            identity_counts["conflict"] += 1
            facts.append(_fact(None, legacy_id, "case_identity", "db.ktra.ID", "CASE_IDENTITY_CONFLICT", blocker="more than one canonical Case matched stable legacy identity"))
            continue
        identity_counts["matched"] += 1
        case = matches[0]
        case_id = str(case["id"])
        application = case.get("application") or {}
        assessment = case.get("assessment") or {}
        outcome = case.get("outcome") or {}
        plan = case.get("plan") or {}
        cert = case.get("certificate") or {}

        decision_ref, decision_date, decision_status = _split_decision(row.get("decision_reference", ""))
        facts.append(_fact(case_id, legacy_id, "inspection_decision_reference", "db.ktra Q. định", "BLOCKED_OWNER_MISSING", candidate=decision_ref, current=plan.get("decision_reference"), blocker="canonical InspectionPlan.decision_reference does not exist"))
        facts.append(_fact(case_id, legacy_id, "inspection_decision_date", "db.ktra Q. định", "BLOCKED_OWNER_MISSING", candidate=decision_date, current=plan.get("decision_date"), blocker="canonical InspectionPlan.decision_date does not exist"))
        facts[-2]["legacy_morphology"] = decision_status
        facts[-1]["legacy_morphology"] = decision_status

        b_value = row.get("bbkt_reference", "")
        actual_value = row.get("inspected_at", "")
        b_date, _ = _period_start_end(b_value)
        actual_start, actual_end = _period_start_end(actual_value)
        current_start = outcome.get("inspected_on")
        current_end = outcome.get("inspected_to_on")
        if b_date is not None and current_start == b_date and (actual_start is None or actual_start != current_start):
            inspection_status = "BLOCKED_PROVENANCE_CONTAMINATION"
            provenance = "MATCHES_BBKT_SOURCE_ONLY"
        elif current_start == actual_start and current_start is not None:
            inspection_status = "ALREADY_MATCHES"
            provenance = "MATCHES_ACTUAL_SOURCE" if b_date != current_start else "MATCHES_BOTH_SOURCES"
        elif current_start is None:
            inspection_status = "BLOCKED_AMBIGUOUS_LEGACY"
            provenance = "CURRENT_EMPTY"
        else:
            inspection_status = "BLOCKED_PROVENANCE_CONTAMINATION" if b_date == current_start else "CONFLICT_EXISTING_CANONICAL"
            provenance = "MATCHES_NEITHER" if b_date != current_start and actual_start != current_start else "LEGACY_ACTUAL_AMBIGUOUS"
        facts.append(_fact(case_id, legacy_id, "actual_inspection_period", "db.ktra Ngày K.tra", inspection_status, candidate=actual_start, current=current_start, provenance_status=provenance, blocker="current importer tries B. bản before Ngày K.tra" if inspection_status == "BLOCKED_PROVENANCE_CONTAMINATION" else None))
        facts.append(_fact(case_id, legacy_id, "bbkt_reference", "db.ktra B. bản", "BLOCKED_OWNER_MISMATCH", candidate=b_value, current=outcome.get("bbkt_reference"), provenance_status=_misrouting_status(b_value, outcome.get("bbkt_reference"), "bbkt_reference"), blocker="B. bản semantics are not proven and importer maps it to bbkt_reference"))

        for key, source, candidate, current in [
            ("dossier_code", "db.ktra Mã hồ sơ", row.get("dossier_code"), application.get("dossier_code")),
            ("application_submitted_on", "db.ktra Ngày nộp hồ sơ", row.get("submitted_at"), application.get("submitted_on")),
            ("applicable_standard", "db.ktra TIÊU CHUẨN ÁP DỤNG", row.get("applicable_standard"), case.get("applicable_standard")),
            ("inspection_type", "db.ktra LOẠI KIỂM TRA", row.get("inspection_type"), case.get("inspection_type")),
            ("certificate_issue_date", "db.cc Ngày cấp CC", row.get("certificate_issue_date"), cert.get("issue_date")),
        ]:
            status = _candidate_status(candidate, current)
            if key == "application_submitted_on":
                status = _date_reconciliation(str(candidate or ""), current, None)[1]
            facts.append(_fact(case_id, legacy_id, key, source, status, candidate=candidate, current=current))
        for key in ("report_written_on", "final_evaluation", "compliance_due_on", "capa_incoming_reference", "approval_submission"):
            facts.append(_fact(case_id, legacy_id, key, "legacy source/profile", "BLOCKED_OWNER_MISSING", blocker="canonical semantic owner is not present"))

        expiry = row.get("certificate_expiry_date", "")
        expiry_morphology = _date_morphology(expiry)
        expiry_status = "MANUAL_RECONCILIATION_REQUIRED" if expiry_morphology in {"PARTIAL_DATE", "ANNOTATED_DATE", "MULTI_DATE"} else _candidate_status(expiry, cert.get("expiry_date"))
        facts.append(_fact(case_id, legacy_id, "certificate_expiry_date", "db.cc Hết hạn CC", expiry_status, candidate=expiry, current=cert.get("expiry_date"), blocker="partial/annotated legacy expiry requires manual reconciliation" if expiry_status == "MANUAL_RECONCILIATION_REQUIRED" else None))

    status_counts = Counter(fact["reconciliation_status"] for fact in facts)
    per_fact: dict[str, Counter[str]] = {}
    for fact in facts:
        per_fact.setdefault(fact["canonical_fact"], Counter())[fact["reconciliation_status"]] += 1
    return {
        "schema_version": "inspection-case-lifecycle-reconciliation-plan/v1",
        "status": "READ_ONLY_DRY_RUN_PLAN",
        "database_policy": {"required_database_name": REQUIRED_DATABASE_NAME, "writes_performed": False},
        "source_policy": {"legacy_values_raw_persisted": False, "candidate_values_hashed": True},
        "identity": dict(identity_counts),
        "summary": {"legacy_cases": len(legacy_rows), "matched_cases": identity_counts["matched"], "unmatched": identity_counts["unmatched"], "identity_conflicts": identity_counts["conflict"], "reconciliation_status_counts": dict(status_counts), "per_fact_status_counts": {key: dict(value) for key, value in sorted(per_fact.items())}},
        "facts": facts,
        "legacy_misrouting_evidence": {"decision_reference_to_application_dossier_reference": "PRESENT", "decision_reference_to_inspection_outcome": "PRESENT", "bbkt_to_outcome_reference": "PRESENT", "bbkt_parse_before_inspected_at_fallback": "PRESENT"},
        "guardrails": {"database_mutated": False, "workbook_mutated": False, "backfill_performed": False, "candidate_database_allowed": False},
    }


def _canonical_snapshot(session: Session, legacy_ids: list[int]) -> list[dict[str, Any]]:
    cases = list(session.scalars(select(Case).where(Case.legacy_inspection_id.in_(legacy_ids)))) if legacy_ids else []
    result: list[dict[str, Any]] = []
    for case in cases:
        application = session.scalar(select(CaseApplication).where(CaseApplication.case_id == case.id))
        assessment = session.scalar(select(CaseAssessment).where(CaseAssessment.case_id == case.id))
        plan = session.scalar(select(InspectionPlan).where(InspectionPlan.case_id == case.id))
        outcome = session.scalar(select(InspectionOutcome).where(InspectionOutcome.case_id == case.id))
        team = session.scalar(select(InspectionTeam).where(InspectionTeam.case_id == case.id))
        members = list(session.scalars(select(InspectionTeamMember).where(InspectionTeamMember.team_id == team.id).order_by(InspectionTeamMember.sort_order, InspectionTeamMember.id))) if team else []
        capa_cycles = list(session.scalars(select(CapaCycle).where(CapaCycle.case_id == case.id).order_by(CapaCycle.round_no)))
        lineage = list(session.scalars(select(LegacyIdMap).where(LegacyIdMap.target_entity_id == case.id).order_by(LegacyIdMap.entity_type, LegacyIdMap.legacy_id)))
        certificate = session.scalar(select(Certificate).where(Certificate.case_id == case.id))
        version = session.scalar(select(CertificateVersion).where(CertificateVersion.certificate_id == certificate.id).order_by(CertificateVersion.version_no.desc())) if certificate else None
        result.append({"id": case.id, "legacy_inspection_id": case.legacy_inspection_id, "gxp_type": case.gxp_type, "applicable_standard": case.applicable_standard, "inspection_type": case.inspection_type, "application": None if application is None else {"dossier_code": application.dossier_code, "dossier_reference": application.dossier_reference, "submitted_on": application.submitted_on}, "assessment": None if assessment is None else {"assessed_on": assessment.assessed_on, "assessor_name": assessment.assessor_name, "assessment_result": assessment.assessment_result}, "plan": None if plan is None else {"decision_document_hint": plan.decision_document_hint, "plan_start_on": plan.plan_start_on, "plan_end_on": plan.plan_end_on}, "team": None if team is None else {"display_text": team.display_text, "members": [{"inspector_profile_id": member.inspector_profile_id, "person_id": member.person_id, "role_label": member.role_label, "sort_order": member.sort_order} for member in members]}, "outcome": None if outcome is None else {"inspected_on": outcome.inspected_on, "inspected_to_on": outcome.inspected_to_on, "decision_reference": outcome.decision_reference, "bbkt_reference": outcome.bbkt_reference, "outcome_result": outcome.outcome_result}, "capa_cycles": [{"round_no": cycle.round_no, "requested_on": cycle.requested_on, "submitted_on": cycle.submitted_on, "assessed_on": cycle.assessed_on, "assessor_name": cycle.assessor_name, "result": cycle.result, "status": cycle.status} for cycle in capa_cycles], "certificate": None if version is None else {"certificate_number": version.certificate_number, "issue_date": version.issue_date, "expiry_date": version.expiry_date}, "legacy_lineage": [{"entity_type": str(mapping.entity_type), "legacy_id": mapping.legacy_id, "target_table": mapping.target_table} for mapping in lineage]})
    return result


def run_read_only_plan(database_url: str, workbook: Path) -> dict[str, Any]:
    require_rehearsal_database(database_url)
    snapshot = read_core_sheet_rows(workbook)
    legacy_rows = snapshot.get("db.ktra", [])
    engine = build_engine(database_url)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False, expire_on_commit=False)
    try:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        ids = [legacy_id for legacy_id in (_row_id(normalize_row(row)) for row in legacy_rows) if legacy_id is not None]
        canonical = _canonical_snapshot(session, ids)
        return build_reconciliation_plan(legacy_rows, canonical)
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a read-only inspection lifecycle reconciliation plan.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--workbook", type=Path, default=ROOT / "legacy" / "Danh sách Kiểm tra GPs.xlsb")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run_read_only_plan(args.database_url, args.workbook.resolve())
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.resolve().write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print("STATUS=READ_ONLY_DRY_RUN_PLAN")
    print(f"MATCHED_CASES={report['summary']['matched_cases']}")
    print(f"OUTPUT={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
