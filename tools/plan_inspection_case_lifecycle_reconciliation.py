from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime
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
    InspectionPeriodSegment,
    InspectionPlan,
    InspectionTeam,
    InspectionTeamMember,
    LegacyIdMap,
)
from backend.app.db.enums import LegacyEntityType
from backend.app.db.session import build_engine
from backend.app.domain.phase2_import import normalize_row, parse_date
from backend.app.domain.inspection_periods import InspectionPeriodSourceState, parse_legacy_inspection_periods
from tools.audit_inspection_case_lifecycle_legacy import (
    _classify_decision_composite,
    _date_morphology,
    _fold,
    _shape,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "legacy_audit" / "inspection_case_lifecycle_reconciliation_plan.json"
REQUIRED_DATABASE_NAME = "gxp_legacy_rehearsal"
SNAPSHOT_SCHEMA_VERSION = "inspection-case-lifecycle-legacy-snapshot/v3"
SNAPSHOT_EXTRACTION_OWNER = "backend.app.domain.legacy_snapshot.read_core_sheet_rows"
SNAPSHOT_EXTRACTION_STATUS = "EXTRACTED_READ_ONLY"
SNAPSHOT_REQUIRED_SECTIONS = ("db.ktra", "db.cc")
SNAPSHOT_KTRA_FIELDS = (
    "ID",
    "__excel_row_number",
    "decision_reference",
    "bbkt_reference",
    "inspected_at",
    "submitted_at",
    "dossier_code",
    "applicable_standard",
    "inspection_type",
    "inspection_gxp_type",
)
SNAPSHOT_CC_FIELDS = (
    "ID",
    "__excel_row_number",
    "inspection_case_legacy_id_ref",
    "certificate_issue_date",
    "certificate_expiry_date",
    "certificate_valid_until",
    "certificate_type",
    "scope_code",
    "certificate_scope_text",
    "certificate_scope_short_text",
    "certificate_standard",
    "certificate_number",
    "certificate_issuer",
    "latest_flag",
    "latest_legacy_id",
)
SNAPSHOT_CC_IDENTITY_PROVENANCE_FIELDS = frozenset(
    {
        "ID",
        "__excel_row_number",
        "inspection_case_legacy_id_ref",
    }
)
# Every selected certificate field that is not identity, provenance, or the
# optional case link is business payload. Deriving this avoids silently
# dropping an otherwise meaningful certificate-only row when fields evolve.
SNAPSHOT_CC_LIFECYCLE_PAYLOAD_FIELDS = tuple(
    field for field in SNAPSHOT_CC_FIELDS if field not in SNAPSHOT_CC_IDENTITY_PROVENANCE_FIELDS
)
# Phase 2 maps this field to CertificateVersion.issuing_authority, while a
# Certificate itself requires a resolved site. Issuer-only, identityless rows
# therefore cannot establish a certificate entity or be linked to a neighbor.
CERTIFICATE_NONIDENTIFYING_RESIDUAL_FIELDS = frozenset({"certificate_issuer"})
CERTIFICATE_IDENTITY_BEARING_FIELDS = frozenset(
    field
    for field in SNAPSHOT_CC_LIFECYCLE_PAYLOAD_FIELDS
    if field not in CERTIFICATE_NONIDENTIFYING_RESIDUAL_FIELDS
)
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
    "BLOCKED_PROVENANCE_AMBIGUOUS",
    "MANUAL_RECONCILIATION_REQUIRED",
    "BLOCKED_TIMEZONE_POLICY_UNPROVEN",
    "LEGACY_SOURCE_MISSING",
    "CERTIFICATE_SOURCE_MISSING",
    "BLOCKED_CERTIFICATE_SOURCE_AMBIGUOUS",
    "BLOCKED_CERTIFICATE_CANONICAL_AMBIGUOUS",
}

# The database/session, API, and legacy importer do not currently establish a
# business-calendar timezone for CaseApplication.submitted_on. UTC timestamps
# elsewhere are operational/audit timestamps, not evidence for a local-date
# rule. Do not project any datetime to a date until an owner closes that gap.
DATE_COMPARISON_POLICY = {
    "canonical_timezone": "UNPROVEN",
    "aware_datetime_conversion": "BLOCKED_UNPROVEN_BUSINESS_TIMEZONE",
    "naive_datetime_conversion": "BLOCKED_UNPROVEN_TIMEZONE",
    "date_value_comparison": "DIRECT_DATE_COMPARISON",
    "evidence": [
        "CaseApplication.submitted_on is DateTime(timezone=True)",
        "database session factory does not set a PostgreSQL timezone",
        "CaseApplicationUpsertRequest accepts datetime without timezone validation",
        "phase2_import.parse_dt constructs naive datetime values from legacy text",
    ],
}

# These closed domains are the scalar, source-audited values that can be
# compared without guessing. Composite or unlisted values remain blocked.
APPLICABLE_STANDARD_DOMAIN = {
    "3p": "3P",
    "eu-gmp": "EU-GMP",
    "gmp": "GMP",
    "gmp bao bi": "GMP Bao bì",
    "japan gmp": "Japan-GMP",
    "japan-gmp": "Japan-GMP",
    "oecd-glp": "OECD-GLP",
    "who-glp": "WHO-GLP",
    "who-gmp": "WHO-GMP",
}
INSPECTION_TYPE_DOMAIN = {
    "bo sung day chuyen": "Bổ sung dây chuyền",
    "bo sung kho": "Bổ sung kho",
    "bo sung nha may nang mem 2": "Bổ sung nhà máy nang mềm 2",
    "cap lai": "Cấp lại",
    "d.gia nra": "Đánh giá NRA",
    "danh gia xac nhan": "Đánh giá xác nhận",
    "danh gia xac nhan japan": "Đánh giá xác nhận Japan",
    "doi pham vi & dia chi": "Đổi phạm vi & địa chỉ",
    "doi pham vi chung nhan": "Đổi phạm vi chứng nhận",
    "doi ten": "Đổi tên",
    "doi ten va gia han cc": "Đổi tên và gia hạn CC",
    "dot xuat": "Đột xuất",
    "gia han cc": "Gia hạn CC",
    "giam sat": "Giám sát",
    "kiem soat thay doi": "Kiểm soát thay đổi",
    "moi": "Mới",
    "moi + tai": "Tái + Mới",
    "sua pham vi chung nhan": "Sửa phạm vi chứng nhận",
    "tai": "Tái",
    "tai + moi": "Tái + Mới",
    "tai, moi": "Tái + Mới",
    "thay doi pham vi": "Thay đổi phạm vi",
    "theo y/c": "Theo yêu cầu",
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
        return "LEGACY_SOURCE_MISSING"
    if not _present(current):
        return "SAFE_INSERT"
    return "ALREADY_MATCHES" if candidate == current else "CONFLICT_EXISTING_CANONICAL"


def _normalize_canonical_date(value: Any) -> tuple[date | None, str | None]:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return None, "BLOCKED_UNPROVEN_TIMEZONE"
        return None, "BLOCKED_UNPROVEN_BUSINESS_TIMEZONE"
    if isinstance(value, date):
        return value, None
    return None, None


def _date_candidate(value: str) -> date | None:
    return parse_date(value)


def _date_source_resolution(value: str) -> tuple[str, str, date | None]:
    """Classify legacy date text without persisting the raw source value."""
    morphology = _date_morphology(value)
    if not _present(value):
        return "MISSING", morphology, None
    candidate = _date_candidate(value)
    if candidate is not None:
        return "DETERMINISTIC", morphology, candidate
    if morphology in {"DATE_RANGE", "MULTI_DATE", "PARTIAL_DATE", "ANNOTATED_DATE"}:
        return "REQUIRES_BUSINESS_SELECTION", morphology, None
    return "UNRESOLVED", morphology, None


def _date_candidate_status(legacy_value: str, current: Any) -> tuple[str, date | None]:
    source_resolution, _, candidate = _date_source_resolution(legacy_value)
    if source_resolution == "MISSING":
        return "LEGACY_SOURCE_MISSING", None
    if source_resolution == "REQUIRES_BUSINESS_SELECTION":
        return "MANUAL_RECONCILIATION_REQUIRED", None
    if source_resolution != "DETERMINISTIC":
        return "BLOCKED_AMBIGUOUS_LEGACY", None
    canonical, timezone_blocker = _normalize_canonical_date(current)
    if timezone_blocker is not None:
        return "BLOCKED_TIMEZONE_POLICY_UNPROVEN", candidate
    if canonical is None:
        return "SAFE_INSERT", candidate
    return ("ALREADY_MATCHES" if candidate == canonical else "CONFLICT_EXISTING_CANONICAL"), candidate


def _normalize_domain(value: Any, domain: dict[str, str]) -> str | None:
    folded = _fold(str(value or ""))
    return domain.get(folded)


def _domain_candidate_status(legacy_value: str, current: Any, domain: dict[str, str]) -> tuple[str, str | None]:
    if not _present(legacy_value):
        return "LEGACY_SOURCE_MISSING", None
    candidate = _normalize_domain(legacy_value, domain)
    canonical = _normalize_domain(current, domain)
    if candidate is None:
        return "BLOCKED_AMBIGUOUS_LEGACY", candidate
    if not _present(current):
        return "SAFE_INSERT", candidate
    if canonical is None:
        return "BLOCKED_AMBIGUOUS_LEGACY", candidate
    return ("ALREADY_MATCHES" if candidate == canonical else "CONFLICT_EXISTING_CANONICAL"), candidate


def _domain_source_resolution(value: str, domain: dict[str, str]) -> tuple[str, str | None]:
    if not _present(value):
        return "MISSING", None
    candidate = _normalize_domain(value, domain)
    return ("RECOGNIZED_DOMAIN_VALUE" if candidate is not None else "UNRECOGNIZED_DOMAIN_VALUE"), candidate


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
    result = parse_legacy_inspection_periods(value)
    if result.state != InspectionPeriodSourceState.KNOWN or len(result.segments) != 1:
        return None, None
    segment = result.segments[0]
    return segment.started_on, segment.ended_on


def _period_pairs(value: str) -> tuple[tuple[date, date], ...]:
    parsed = parse_legacy_inspection_periods(value)
    if parsed.state != InspectionPeriodSourceState.KNOWN:
        return ()
    return tuple((segment.started_on, segment.ended_on) for segment in parsed.segments)


def _canonical_period_pairs(outcome: dict[str, Any]) -> tuple[tuple[date, date], ...]:
    stored = outcome.get("inspection_period_segments") or []
    if stored:
        return tuple((segment["started_on"], segment["ended_on"]) for segment in stored)
    start, end = outcome.get("inspected_on"), outcome.get("inspected_to_on")
    return () if start is None or end is None else ((start, end),)


def _date_reconciliation(legacy_value: str, current_start: date | None, current_end: date | None) -> tuple[str, str, str | None]:
    parsed = parse_legacy_inspection_periods(legacy_value)
    morphology = _date_morphology(legacy_value)
    if parsed.state == InspectionPeriodSourceState.MISSING:
        return morphology, "LEGACY_SOURCE_MISSING", None
    if parsed.state == InspectionPeriodSourceState.PENDING_INPUT:
        return morphology, "PENDING_LEGACY_INPUT", None
    if parsed.state == InspectionPeriodSourceState.NOT_APPLICABLE:
        return morphology, "LEGACY_SOURCE_NOT_APPLICABLE", None
    if parsed.state == InspectionPeriodSourceState.NON_DATE_EXPRESSION:
        return morphology, "MANUAL_RECONCILIATION_REQUIRED", None
    if parsed.state != InspectionPeriodSourceState.KNOWN:
        return morphology, "BLOCKED_AMBIGUOUS_LEGACY", None
    if len(parsed.segments) != 1:
        return morphology, "SEGMENT_MODEL_MIGRATION_REQUIRED", None
    start, end = parsed.segments[0].started_on, parsed.segments[0].ended_on
    current_start, start_timezone_blocker = _normalize_canonical_date(current_start)
    current_end, end_timezone_blocker = _normalize_canonical_date(current_end)
    if start_timezone_blocker is not None or end_timezone_blocker is not None:
        return morphology, "BLOCKED_TIMEZONE_POLICY_UNPROVEN", None
    if current_start == start and current_end == end:
        return morphology, "ALREADY_MATCHES", start.isoformat()
    if current_start is None and current_end is None:
        return morphology, "SAFE_INSERT", start.isoformat()
    if current_start == start and current_end is None:
        return morphology, "SAFE_UPDATE_IF_EMPTY", start.isoformat()
    return morphology, "CONFLICT_EXISTING_CANONICAL", start.isoformat()


def _classify_period_reconciliation(
    *,
    actual_status: str,
    actual_start: date | None,
    actual_end: date | None,
    current_start: Any,
    current_end: Any,
) -> tuple[str, str]:
    """Compare the canonical compatibility view only with `Ngay K.tra`."""
    normalized_start, start_blocker = _normalize_canonical_date(current_start)
    normalized_end, end_blocker = _normalize_canonical_date(current_end)
    if start_blocker is not None or end_blocker is not None:
        return actual_status, "NOT_PROVEN_TIMEZONE_UNCOMPARABLE"

    if actual_start is None:
        if normalized_start is None and normalized_end is None:
            return actual_status, "CURRENT_EMPTY"
        return actual_status, "MATCHES_NEITHER"

    if normalized_start == actual_start and normalized_end == actual_end:
        return actual_status, "MATCHES_ACTUAL_SOURCE"
    if normalized_start == actual_start and normalized_end is None:
        return actual_status, "MATCHES_ACTUAL_START_ONLY"
    if normalized_start is None and normalized_end is None:
        return actual_status, "CURRENT_EMPTY"
    return actual_status, "MATCHES_NEITHER"


def _misrouting_status(legacy_value: str, current_value: Any) -> str:
    if not _present(current_value):
        return "CURRENT_EMPTY"
    if _fold(str(legacy_value)) == _fold(str(current_value)):
        return "MATCHES_MISROUTED_SOURCE"
    return "NOT_MATCHING_MISROUTED_SOURCE"


def _case_lineage_matches(case: dict[str, Any], legacy_id: int) -> bool:
    for mapping in case.get("legacy_lineage") or []:
        entity_type = str(mapping.get("entity_type") or "").lower()
        if mapping.get("target_table") != "case" or entity_type not in {"case", "legacyentitytype.case"}:
            continue
        if str(mapping.get("legacy_id") or "").strip() == str(legacy_id):
            return True
    return False


def _resolve_case_identity(legacy_id: int, canonical_cases: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    direct = [case for case in canonical_cases if case.get("legacy_inspection_id") == legacy_id]
    lineage = [case for case in canonical_cases if _case_lineage_matches(case, legacy_id)]
    direct_ids = {str(case["id"]) for case in direct}
    lineage_ids = {str(case["id"]) for case in lineage}
    if direct_ids and lineage_ids and direct_ids != lineage_ids:
        return "CASE_IDENTITY_CONFLICT", []
    matches = direct if direct else lineage
    if len({str(case["id"]) for case in matches}) != 1:
        return ("CASE_NOT_FOUND" if not matches else "CASE_IDENTITY_CONFLICT"), []
    return "MATCHED", matches


def _fact(case_id: str | None, legacy_id: int, key: str, source: str, status: str, *, candidate: Any = None, current: Any = None, current_value_comparable: bool | None = None, current_comparison_blocker: str | None = None, provenance_status: str = "NOT_ASSESSED", blocker: str | None = None, legacy_morphology: str | None = None, source_resolution_status: str | None = None) -> dict[str, Any]:
    fact = {
        "legacy_inspection_id": legacy_id,
        "case_id": case_id,
        "canonical_fact": key,
        "legacy_source": source,
        "legacy_morphology": legacy_morphology if legacy_morphology is not None else (_date_morphology(str(candidate)) if key.endswith("_on") and candidate is not None else _shape(str(candidate or ""))),
        "current_value_present": _present(current),
        "current_value_comparable": current_value_comparable,
        "current_comparison_blocker": current_comparison_blocker,
        "candidate_available": _present(candidate),
        "candidate_sha256": _hash(str(candidate)) if candidate is not None and not isinstance(candidate, (date, int, float, bool)) else None,
        "candidate_value": candidate if isinstance(candidate, (date, type(None))) else None,
        "reconciliation_status": status,
        "provenance_status": provenance_status,
        "blocker": blocker,
        "recommended_future_action": "manual_review" if status in {"MANUAL_RECONCILIATION_REQUIRED", "BLOCKED_PROVENANCE_CONTAMINATION", "BLOCKED_PROVENANCE_AMBIGUOUS", "CONFLICT_EXISTING_CANONICAL"} else ("write_structured_owner" if status in {"SAFE_INSERT", "SAFE_UPDATE_IF_EMPTY"} else "no_write"),
    }
    if source_resolution_status is not None:
        fact["source_resolution_status"] = source_resolution_status
    return fact


def _date_fact(
    case_id: str,
    legacy_id: int,
    key: str,
    source: str,
    status: str,
    *,
    candidate: date | None,
    current: Any,
    blocker: str | None = None,
    current_value_present: bool | None = None,
    current_value_comparable: bool | None = None,
    current_comparison_blocker: str | None = None,
    legacy_value: str = "",
    source_resolution_status: str | None = None,
) -> dict[str, Any]:
    _, comparison_blocker = _normalize_canonical_date(current)
    fact = _fact(
        case_id,
        legacy_id,
        key,
        source,
        status,
        candidate=candidate,
        current=current,
        current_value_comparable=(comparison_blocker is None if current_value_comparable is None else current_value_comparable),
        current_comparison_blocker=(comparison_blocker if current_comparison_blocker is None else current_comparison_blocker),
        blocker=blocker,
        legacy_morphology=_date_morphology(legacy_value),
        source_resolution_status=source_resolution_status or _date_source_resolution(legacy_value)[0],
    )
    if current_value_present is not None:
        fact["current_value_present"] = current_value_present
    return fact


def _period_fact(
    case_id: str,
    legacy_id: int,
    *,
    status: str,
    candidate_start: date | None,
    candidate_end: date | None,
    current_start: Any,
    current_end: Any,
    provenance_status: str,
    blocker: str | None,
    legacy_value: str,
) -> dict[str, Any]:
    """Emit comparison state for both columns of the owned inspection period."""
    normalized_start, start_blocker = _normalize_canonical_date(current_start)
    normalized_end, end_blocker = _normalize_canonical_date(current_end)
    comparison_blocker = start_blocker or end_blocker
    comparable = comparison_blocker is None
    fact = _fact(
        case_id,
        legacy_id,
        "actual_inspection_period",
        "db.ktra Ngày K.tra",
        status,
        candidate=candidate_start,
        current=current_start,
        current_value_comparable=comparable,
        current_comparison_blocker=comparison_blocker,
        provenance_status=provenance_status,
        blocker=blocker,
        legacy_morphology=_date_morphology(legacy_value),
        source_resolution_status=(
            "MISSING"
            if not _present(legacy_value)
            else "DETERMINISTIC"
            if candidate_start is not None
            else "REQUIRES_BUSINESS_SELECTION"
            if _date_morphology(legacy_value) in {"DATE_RANGE", "MULTI_DATE", "PARTIAL_DATE", "ANNOTATED_DATE"}
            else "UNRESOLVED"
        ),
    )
    fact.update(
        {
            "current_value_present": _present(current_start) or _present(current_end),
            "current_period_start_present": _present(current_start),
            "current_period_end_present": _present(current_end),
            "current_period_start_matches_candidate": (
                normalized_start == candidate_start
                if comparable and normalized_start is not None and candidate_start is not None
                else False
            ),
            "legacy_period_end": None if candidate_end is None else candidate_end.isoformat(),
        }
    )
    return fact


def _canonical_certificate_field_present(
    certificates: list[dict[str, Any]], field: str
) -> bool:
    """Report presence per fact when an unselected certificate set blocks comparison."""
    return any(_present(certificate.get(field)) for certificate in certificates)


def _row_id(row: dict[str, str]) -> int | None:
    try:
        return int(float(str(row.get("ID", "")).strip()))
    except (TypeError, ValueError):
        return None


def _snapshot_error(message: str) -> RuntimeError:
    return RuntimeError(f"invalid inspection lifecycle legacy snapshot: {message}")


def _snapshot_integer(value: Any, *, field: str, section: str, index: int) -> int:
    try:
        numeric = int(float(str(value).strip()))
    except (TypeError, ValueError):
        raise _snapshot_error(f"{section} row {index} has invalid {field}") from None
    return numeric


def _snapshot_section(payload: dict[str, Any], name: str) -> list[dict[str, str]]:
    sections = payload.get("sections")
    if not isinstance(sections, dict):
        raise _snapshot_error("sections must be an object")
    section = sections.get(name)
    if not isinstance(section, dict):
        raise _snapshot_error(f"missing required section {name}")
    if section.get("source_sheet") != name:
        raise _snapshot_error(f"section {name} has mismatched source_sheet")
    rows = section.get("rows")
    if not isinstance(rows, list):
        raise _snapshot_error(f"section {name} rows must be an array")
    if section.get("row_count") != len(rows):
        raise _snapshot_error(f"section {name} row_count does not match rows")
    validated: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in row.items()):
            raise _snapshot_error(f"section {name} row {index} must contain string fields")
        validated.append(dict(row))
    return validated


def load_legacy_snapshot_payload(payload: Any, *, expected_workbook_sha256: str | None = None) -> dict[str, Any]:
    """Validate local Windows extraction evidence without importing workbook tooling."""
    if not isinstance(payload, dict):
        raise _snapshot_error("top-level payload must be an object")
    required_metadata = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "extraction_owner": SNAPSHOT_EXTRACTION_OWNER,
        "extraction_status": SNAPSHOT_EXTRACTION_STATUS,
    }
    for field, expected in required_metadata.items():
        if payload.get(field) != expected:
            raise _snapshot_error(f"unsupported or missing {field}")
    workbook_sha = payload.get("source_workbook_sha256")
    if not isinstance(workbook_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", workbook_sha):
        raise _snapshot_error("source_workbook_sha256 must be a lowercase SHA256")
    if expected_workbook_sha256 is not None and workbook_sha != expected_workbook_sha256.lower():
        raise _snapshot_error("source workbook SHA256 does not match the expected value")
    if not isinstance(payload.get("source_workbook_name"), str) or not payload["source_workbook_name"].strip():
        raise _snapshot_error("source_workbook_name is required")
    if payload.get("source_sheets") != list(SNAPSHOT_REQUIRED_SECTIONS):
        raise _snapshot_error("source_sheets must declare the required sections in canonical order")

    ktra_rows = _snapshot_section(payload, "db.ktra")
    cc_rows = _snapshot_section(payload, "db.cc")
    if payload.get("row_count") != len(ktra_rows) + len(cc_rows):
        raise _snapshot_error("row_count does not match source sections")
    eligibility_counts = payload.get("row_eligibility_counts")
    required_count_fields = {
        "db_ktra_rows_emitted",
        "db_ktra_structural_blank_rows_skipped",
        "db_cc_source_rows_seen",
        "db_cc_rows_emitted",
        "db_cc_linked_rows",
        "db_cc_unlinked_rows",
        "db_cc_unlinked_rows_with_business_payload",
        "db_cc_invalid_link_rows",
        "db_cc_structural_blank_rows_skipped",
        "db_cc_identityless_residual_rows_skipped",
        "db_cc_identityless_business_evidence_rows",
    }
    if not isinstance(eligibility_counts, dict) or set(eligibility_counts) != required_count_fields:
        raise _snapshot_error("row_eligibility_counts is missing required counters")
    if any(not isinstance(value, int) or value < 0 for value in eligibility_counts.values()):
        raise _snapshot_error("row_eligibility_counts must contain non-negative integers")
    if eligibility_counts["db_ktra_rows_emitted"] != len(ktra_rows) or eligibility_counts["db_cc_rows_emitted"] != len(cc_rows):
        raise _snapshot_error("row_eligibility_counts emitted rows do not match sections")
    if eligibility_counts["db_cc_source_rows_seen"] != (
        eligibility_counts["db_cc_rows_emitted"]
        + eligibility_counts["db_cc_structural_blank_rows_skipped"]
        + eligibility_counts["db_cc_identityless_residual_rows_skipped"]
        + eligibility_counts["db_cc_identityless_business_evidence_rows"]
    ):
        raise _snapshot_error("row_eligibility_counts db.cc source classifications do not match rows seen")
    if eligibility_counts["db_cc_identityless_business_evidence_rows"] != 0:
        raise _snapshot_error("snapshot cannot contain unresolved identityless db.cc business evidence")
    if eligibility_counts["db_cc_linked_rows"] + eligibility_counts["db_cc_unlinked_rows"] != len(cc_rows):
        raise _snapshot_error("row_eligibility_counts db.cc link states do not match rows")
    if eligibility_counts["db_cc_unlinked_rows_with_business_payload"] > eligibility_counts["db_cc_unlinked_rows"]:
        raise _snapshot_error("row_eligibility_counts unlinked payload count is invalid")

    ktra_ids: set[int] = set()
    for index, row in enumerate(ktra_rows, start=1):
        missing = [field for field in SNAPSHOT_KTRA_FIELDS if field not in row]
        if missing:
            raise _snapshot_error(f"db.ktra row {index} missing required fields: {', '.join(missing)}")
        legacy_id = _snapshot_integer(row["ID"], field="ID", section="db.ktra", index=index)
        _snapshot_integer(row["__excel_row_number"], field="__excel_row_number", section="db.ktra", index=index)
        if legacy_id in ktra_ids:
            raise _snapshot_error(f"duplicate db.ktra ID {legacy_id}")
        ktra_ids.add(legacy_id)

    certificates_by_case: dict[int, list[dict[str, str]]] = {}
    certificate_ids: set[int] = set()
    unlinked_certificate_rows = 0
    for index, row in enumerate(cc_rows, start=1):
        missing = [field for field in SNAPSHOT_CC_FIELDS if field not in row]
        if missing:
            raise _snapshot_error(f"db.cc row {index} missing required fields: {', '.join(missing)}")
        certificate_id = _snapshot_integer(row["ID"], field="ID", section="db.cc", index=index)
        _snapshot_integer(row["__excel_row_number"], field="__excel_row_number", section="db.cc", index=index)
        if certificate_id in certificate_ids:
            raise _snapshot_error(f"duplicate db.cc ID {certificate_id}")
        certificate_ids.add(certificate_id)
        raw_case_id = row["inspection_case_legacy_id_ref"].strip()
        if not raw_case_id:
            unlinked_certificate_rows += 1
            continue
        case_id = _snapshot_integer(raw_case_id, field="inspection_case_legacy_id_ref", section="db.cc", index=index)
        if case_id not in ktra_ids:
            raise _snapshot_error(f"db.cc row {index} references missing db.ktra ID {case_id}")
        certificates_by_case.setdefault(case_id, []).append(row)
    if unlinked_certificate_rows != eligibility_counts["db_cc_unlinked_rows"]:
        raise _snapshot_error("row_eligibility_counts unlinked rows do not match db.cc link state")
    if sum(len(rows) for rows in certificates_by_case.values()) != eligibility_counts["db_cc_linked_rows"]:
        raise _snapshot_error("row_eligibility_counts linked rows do not match db.cc link state")

    # Keep certificate values in their source container. The planner receives a
    # linked projection rather than a fabricated db.ktra field overlay.
    linked_rows = [
        {
            "__source_ktra": row,
            "__certificate_sources": certificates_by_case.get(
                _snapshot_integer(row["ID"], field="ID", section="db.ktra", index=index), []
            ),
        }
        for index, row in enumerate(ktra_rows, start=1)
    ]
    return {
        "legacy_rows": linked_rows,
        "provenance": {
            "schema_version": payload["schema_version"],
            "source_workbook_sha256": workbook_sha,
            "source_workbook_name": payload["source_workbook_name"],
            "extraction_owner": payload["extraction_owner"],
            "source_sheets": payload["source_sheets"],
            "row_count": payload["row_count"],
            "extraction_status": payload["extraction_status"],
            "row_eligibility_counts": eligibility_counts,
        },
        "validation_counts": {
            "db_ktra_rows": len(ktra_rows),
            "db_cc_rows": len(cc_rows),
            "linked_certificate_rows": sum(len(rows) for rows in certificates_by_case.values()),
            "unlinked_certificate_rows": unlinked_certificate_rows,
            "cases_with_multiple_linked_certificates": sum(1 for rows in certificates_by_case.values() if len(rows) > 1),
        },
    }


def load_legacy_snapshot_json(path: Path, *, expected_workbook_sha256: str | None = None) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _snapshot_error(f"cannot read JSON input: {exc}") from None
    return load_legacy_snapshot_payload(payload, expected_workbook_sha256=expected_workbook_sha256)


def build_reconciliation_plan(legacy_rows: list[dict[str, Any]], canonical_cases: list[dict[str, Any]]) -> dict[str, Any]:
    facts: list[dict[str, Any]] = []
    identity_counts = Counter()
    identity_gap_reason_counts = Counter()
    for raw in legacy_rows:
        source_ktra = raw.get("__source_ktra", raw)
        if not isinstance(source_ktra, dict):
            raise ValueError("legacy reconciliation row has invalid db.ktra source")
        row = normalize_row(source_ktra)
        source_certificates = raw.get("__certificate_sources")
        if source_certificates is None:
            # Direct in-memory test input predates the snapshot boundary.
            source_certificates = [row] if any(key in row for key in SNAPSHOT_CC_FIELDS) else []
        if not isinstance(source_certificates, list) or any(not isinstance(value, dict) for value in source_certificates):
            raise ValueError("legacy reconciliation row has invalid db.cc source list")
        certificate_rows = [normalize_row(value) for value in source_certificates]
        legacy_id = _row_id(row)
        if legacy_id is None:
            continue
        identity_status, matches = _resolve_case_identity(legacy_id, canonical_cases)
        if identity_status == "CASE_NOT_FOUND":
            identity_counts["unmatched"] += 1
            facts.append(
                _fact(
                    None,
                    legacy_id,
                    "case_identity",
                    "db.ktra.ID",
                    "CASE_NOT_FOUND",
                    blocker="no direct Case.legacy_inspection_id or Case LegacyIdMap lineage match",
                )
            )
            facts[-1]["identity_gap_reason"] = "NO_DIRECT_OR_LINEAGE"
            identity_gap_reason_counts["NO_DIRECT_OR_LINEAGE"] += 1
            continue
        if identity_status == "CASE_IDENTITY_CONFLICT":
            identity_counts["conflict"] += 1
            facts.append(_fact(None, legacy_id, "case_identity", "db.ktra.ID", "CASE_IDENTITY_CONFLICT", blocker="direct Case identity and/or applicable LegacyIdMap lineage conflict"))
            continue
        identity_counts["matched"] += 1
        case = matches[0]
        case_id = str(case["id"])
        application = case.get("application") or {}
        assessment = case.get("assessment") or {}
        outcome = case.get("outcome") or {}
        plan = case.get("plan") or {}
        canonical_certificates = case.get("certificates")
        if canonical_certificates is None:
            certificate = case.get("certificate")
            canonical_certificates = [] if certificate is None else [certificate]
        if not isinstance(canonical_certificates, list) or any(not isinstance(value, dict) for value in canonical_certificates):
            raise ValueError("canonical reconciliation case has invalid certificate list")
        certificate_context = canonical_certificates[0] if len(canonical_certificates) == 1 else {}

        if len(certificate_rows) == 0:
            certificate_source_status = "CERTIFICATE_SOURCE_MISSING"
            certificate_source_blocker = "no linked db.cc certificate source row"
        elif len(certificate_rows) == 1:
            certificate_source_status = None
            certificate_source_blocker = None
        else:
            certificate_source_status = "BLOCKED_CERTIFICATE_SOURCE_AMBIGUOUS"
            certificate_source_blocker = "multiple linked db.cc certificate source rows have no proven lifecycle selector"
        if len(canonical_certificates) > 1:
            certificate_canonical_status = "BLOCKED_CERTIFICATE_CANONICAL_AMBIGUOUS"
            certificate_canonical_blocker = "multiple canonical Certificate rows are linked to this Case"
        else:
            certificate_canonical_status = None
            certificate_canonical_blocker = None

        decision_ref, decision_date, decision_status = _split_decision(row.get("decision_reference", ""))
        facts.append(_fact(case_id, legacy_id, "inspection_decision_reference", "db.ktra Q. định", "BLOCKED_OWNER_MISSING", candidate=decision_ref, current=plan.get("decision_reference"), blocker="canonical InspectionPlan.decision_reference does not exist"))
        facts.append(_fact(case_id, legacy_id, "inspection_decision_date", "db.ktra Q. định", "BLOCKED_OWNER_MISSING", candidate=decision_date, current=plan.get("decision_date"), blocker="canonical InspectionPlan.decision_date does not exist"))
        facts[-2]["legacy_morphology"] = decision_status
        facts[-1]["legacy_morphology"] = decision_status

        decision_raw = row.get("decision_reference", "")
        facts.append(_fact(case_id, legacy_id, "application_dossier_reference_compatibility", "db.ktra Q. định", "BLOCKED_OWNER_MISMATCH", candidate=decision_raw, current=application.get("dossier_reference"), provenance_status=_misrouting_status(decision_raw, application.get("dossier_reference")), blocker="Q. định is copied to application compatibility field, not the canonical decision owner"))
        facts.append(_fact(case_id, legacy_id, "outcome_decision_reference_compatibility", "db.ktra Q. định", "BLOCKED_OWNER_MISMATCH", candidate=decision_raw, current=outcome.get("decision_reference"), provenance_status=_misrouting_status(decision_raw, outcome.get("decision_reference")), blocker="Q. định is copied to outcome compatibility field, not the canonical decision owner"))

        actual_value = row.get("inspected_at", "")
        source_segments = _period_pairs(actual_value)
        actual_start, actual_end = _period_start_end(actual_value)
        current_start = outcome.get("inspected_on")
        current_end = outcome.get("inspected_to_on")
        canonical_segments = _canonical_period_pairs(outcome)
        actual_status = _date_reconciliation(actual_value, current_start, current_end)[1]
        if len(source_segments) > 1 and source_segments == canonical_segments:
            actual_status = "ALREADY_MATCHES"
        elif len(source_segments) > 1 and canonical_segments:
            actual_status = "CONFLICT_EXISTING_CANONICAL"
        inspection_status, provenance = _classify_period_reconciliation(
            actual_status=actual_status,
            actual_start=actual_start,
            actual_end=actual_end,
            current_start=current_start,
            current_end=current_end,
        )
        period_fact = _period_fact(
                case_id,
                legacy_id,
                status=inspection_status,
                candidate_start=actual_start,
                candidate_end=actual_end,
                current_start=current_start,
                current_end=current_end,
                provenance_status=provenance,
                blocker="multiple ordered Ngày K.tra segments require the inspection_period_segment model"
                if inspection_status == "SEGMENT_MODEL_MIGRATION_REQUIRED" else None,
                legacy_value=actual_value,
            )
        period_fact.update(
            {
                "source_segment_count": len(source_segments),
                "canonical_segment_count": len(canonical_segments),
                "ordered_segment_comparison": (
                    "MATCHES" if source_segments and source_segments == canonical_segments else
                    "DIFFERS" if source_segments and canonical_segments else "NOT_REPRESENTED"
                ),
            }
        )
        facts.append(period_fact)
        b_value = row.get("bbkt_reference", "")
        facts.append(_fact(case_id, legacy_id, "bbkt_reference", "db.ktra B. bản", "BLOCKED_OWNER_MISMATCH", candidate=b_value, current=outcome.get("bbkt_reference"), provenance_status=_misrouting_status(b_value, outcome.get("bbkt_reference")), blocker="B. bản semantics are not proven and importer maps it to bbkt_reference"))

        for key, source, candidate, current in [
            ("dossier_code", "db.ktra Mã hồ sơ", row.get("dossier_code"), application.get("dossier_code")),
        ]:
            facts.append(_fact(case_id, legacy_id, key, source, _candidate_status(candidate, current), candidate=candidate, current=current))
        for key, source, legacy_value, current in [
            ("application_submitted_on", "db.ktra Ngày nộp hồ sơ", row.get("submitted_at", ""), application.get("submitted_on")),
        ]:
            status, candidate = _date_candidate_status(legacy_value, current)
            facts.append(_date_fact(case_id, legacy_id, key, source, status, candidate=candidate, current=current, legacy_value=legacy_value))
        for key, source, legacy_value, current, domain in [
            ("applicable_standard", "db.ktra TIÊU CHUẨN ÁP DỤNG", row.get("applicable_standard", ""), case.get("applicable_standard"), APPLICABLE_STANDARD_DOMAIN),
            ("inspection_type", "db.ktra LOẠI KIỂM TRA", row.get("inspection_type", ""), case.get("inspection_type"), INSPECTION_TYPE_DOMAIN),
        ]:
            status, candidate = _domain_candidate_status(legacy_value, current, domain)
            source_resolution, _ = _domain_source_resolution(legacy_value, domain)
            facts.append(
                _fact(
                    case_id,
                    legacy_id,
                    key,
                    source,
                    status,
                    candidate=candidate,
                    current=_normalize_domain(current, domain),
                    legacy_morphology=source_resolution,
                    source_resolution_status=source_resolution,
                )
            )
        for key in ("report_written_on", "final_evaluation", "compliance_due_on", "capa_incoming_reference", "approval_submission"):
            facts.append(_fact(case_id, legacy_id, key, "legacy source/profile", "BLOCKED_OWNER_MISSING", blocker="canonical semantic owner is not present"))

        certificate_row = certificate_rows[0] if len(certificate_rows) == 1 else {}
        certificate_status = certificate_source_status or certificate_canonical_status
        certificate_blocker = certificate_source_blocker or certificate_canonical_blocker
        ambiguous_issue_present = (
            _canonical_certificate_field_present(canonical_certificates, "issue_date")
            if certificate_canonical_status
            else None
        )
        ambiguous_expiry_present = (
            _canonical_certificate_field_present(canonical_certificates, "expiry_date")
            if certificate_canonical_status
            else None
        )
        certificate_current = certificate_context.get("issue_date")
        issue_value = certificate_row.get("certificate_issue_date", "")
        if certificate_status is None:
            issue_status, issue_candidate = _date_candidate_status(issue_value, certificate_current)
        else:
            issue_status, issue_candidate = certificate_status, None
        facts.append(
            _date_fact(
                case_id,
                legacy_id,
                "certificate_issue_date",
                "db.cc Ngày cấp CC",
                issue_status,
                candidate=issue_candidate,
                current=certificate_current if certificate_canonical_status is None else None,
                blocker=certificate_blocker,
                current_value_present=ambiguous_issue_present,
                current_value_comparable=False if certificate_canonical_status else None,
                current_comparison_blocker=certificate_canonical_status,
                legacy_value=issue_value,
                source_resolution_status=(
                    "CERTIFICATE_SOURCE_MISSING"
                    if certificate_source_status == "CERTIFICATE_SOURCE_MISSING"
                    else "CERTIFICATE_SOURCE_AMBIGUOUS"
                    if certificate_source_status == "BLOCKED_CERTIFICATE_SOURCE_AMBIGUOUS"
                    else None
                ),
            )
        )
        facts[-1]["legacy_certificate_candidate_count"] = len(certificate_rows)
        facts[-1]["canonical_certificate_candidate_count"] = len(canonical_certificates)

        expiry = certificate_row.get("certificate_expiry_date", "") or certificate_row.get("certificate_valid_until", "")
        expiry_morphology = _date_morphology(expiry)
        if certificate_status is not None:
            expiry_status, expiry_candidate = certificate_status, None
        elif expiry_morphology in {"PARTIAL_DATE", "ANNOTATED_DATE", "MULTI_DATE"}:
            expiry_status, expiry_candidate = "MANUAL_RECONCILIATION_REQUIRED", None
        else:
            expiry_status, expiry_candidate = _date_candidate_status(expiry, certificate_context.get("expiry_date"))
        facts.append(
            _date_fact(
                case_id,
                legacy_id,
                "certificate_expiry_date",
                "db.cc Hết hạn CC",
                expiry_status,
                candidate=expiry_candidate,
                current=certificate_context.get("expiry_date") if certificate_canonical_status is None else None,
                blocker=certificate_blocker or ("partial/annotated legacy expiry requires manual reconciliation" if expiry_status == "MANUAL_RECONCILIATION_REQUIRED" else None),
                current_value_present=ambiguous_expiry_present,
                current_value_comparable=False if certificate_canonical_status else None,
                current_comparison_blocker=certificate_canonical_status,
                legacy_value=expiry,
                source_resolution_status=(
                    "CERTIFICATE_SOURCE_MISSING"
                    if certificate_source_status == "CERTIFICATE_SOURCE_MISSING"
                    else "CERTIFICATE_SOURCE_AMBIGUOUS"
                    if certificate_source_status == "BLOCKED_CERTIFICATE_SOURCE_AMBIGUOUS"
                    else None
                ),
            )
        )
        facts[-1]["legacy_certificate_candidate_count"] = len(certificate_rows)
        facts[-1]["canonical_certificate_candidate_count"] = len(canonical_certificates)
        facts[-1]["legacy_morphology"] = expiry_morphology

    status_counts = Counter(fact["reconciliation_status"] for fact in facts)
    per_fact: dict[str, Counter[str]] = {}
    for fact in facts:
        per_fact.setdefault(fact["canonical_fact"], Counter())[fact["reconciliation_status"]] += 1
    return {
        "schema_version": "inspection-case-lifecycle-reconciliation-plan/v4",
        "status": "READ_ONLY_DRY_RUN_PLAN",
        "database_policy": {"required_database_name": REQUIRED_DATABASE_NAME, "writes_performed": False},
        "source_policy": {"legacy_values_raw_persisted": False, "candidate_values_hashed": True},
        "date_comparison_policy": DATE_COMPARISON_POLICY,
        "identity": dict(identity_counts),
        "identity_gap_reason_counts": dict(identity_gap_reason_counts),
        "summary": {"legacy_cases": len(legacy_rows), "matched_cases": identity_counts["matched"], "unmatched": identity_counts["unmatched"], "identity_conflicts": identity_counts["conflict"], "reconciliation_status_counts": dict(status_counts), "per_fact_status_counts": {key: dict(value) for key, value in sorted(per_fact.items())}},
        "facts": facts,
        "legacy_misrouting_evidence": {"decision_reference_to_application_dossier_reference": "PRESENT", "decision_reference_to_inspection_outcome": "PRESENT", "bbkt_to_outcome_reference": "PRESENT", "bbkt_parse_before_inspected_at_fallback": "HISTORICAL_REMEDIATED"},
        "guardrails": {"database_mutated": False, "workbook_mutated": False, "backfill_performed": False, "candidate_database_allowed": False},
    }


def _canonical_snapshot(session: Session, legacy_ids: list[int]) -> list[dict[str, Any]]:
    if not legacy_ids:
        return []
    legacy_keys = [str(legacy_id) for legacy_id in legacy_ids]
    lineage_targets = list(
        session.scalars(
            select(LegacyIdMap).where(
                LegacyIdMap.entity_type == LegacyEntityType.CASE,
                LegacyIdMap.target_table == "case",
                LegacyIdMap.legacy_id.in_(legacy_keys),
            )
        )
    )
    target_ids = {mapping.target_entity_id for mapping in lineage_targets}
    cases = list(session.scalars(select(Case).where(Case.legacy_inspection_id.in_(legacy_ids) | Case.id.in_(target_ids))))
    result: list[dict[str, Any]] = []
    for case in cases:
        application = session.scalar(select(CaseApplication).where(CaseApplication.case_id == case.id))
        assessment = session.scalar(select(CaseAssessment).where(CaseAssessment.case_id == case.id))
        plan = session.scalar(select(InspectionPlan).where(InspectionPlan.case_id == case.id))
        outcome = session.scalar(select(InspectionOutcome).where(InspectionOutcome.case_id == case.id))
        segments = [] if outcome is None else list(
            session.scalars(
                select(InspectionPeriodSegment)
                .where(InspectionPeriodSegment.inspection_outcome_id == outcome.id)
                .order_by(InspectionPeriodSegment.ordinal)
            )
        )
        team = session.scalar(select(InspectionTeam).where(InspectionTeam.case_id == case.id))
        members = list(session.scalars(select(InspectionTeamMember).where(InspectionTeamMember.team_id == team.id).order_by(InspectionTeamMember.sort_order, InspectionTeamMember.id))) if team else []
        capa_cycles = list(session.scalars(select(CapaCycle).where(CapaCycle.case_id == case.id).order_by(CapaCycle.round_no)))
        lineage = list(session.scalars(select(LegacyIdMap).where(LegacyIdMap.target_entity_id == case.id).order_by(LegacyIdMap.entity_type, LegacyIdMap.legacy_id)))
        certificates = list(session.scalars(select(Certificate).where(Certificate.case_id == case.id)))
        certificate_contexts: list[dict[str, Any]] = []
        for certificate in certificates:
            version = session.scalars(
                select(CertificateVersion)
                .where(CertificateVersion.certificate_id == certificate.id)
                .order_by(CertificateVersion.version_no.desc())
            ).first()
            certificate_contexts.append(
                {}
                if version is None
                else {
                    "certificate_number": version.certificate_number,
                    "issue_date": version.issue_date,
                    "expiry_date": version.expiry_date,
                }
            )
        result.append({"id": case.id, "legacy_inspection_id": case.legacy_inspection_id, "gxp_type": case.gxp_type, "applicable_standard": case.applicable_standard, "inspection_type": case.inspection_type, "application": None if application is None else {"dossier_code": application.dossier_code, "dossier_reference": application.dossier_reference, "submitted_on": application.submitted_on}, "assessment": None if assessment is None else {"assessed_on": assessment.assessed_on, "assessor_name": assessment.assessor_name, "assessment_result": assessment.assessment_result}, "plan": None if plan is None else {"decision_document_hint": plan.decision_document_hint, "plan_start_on": plan.plan_start_on, "plan_end_on": plan.plan_end_on}, "team": None if team is None else {"display_text": team.display_text, "members": [{"inspector_profile_id": member.inspector_profile_id, "person_id": member.person_id, "role_label": member.role_label, "sort_order": member.sort_order} for member in members]}, "outcome": None if outcome is None else {"inspected_on": outcome.inspected_on, "inspected_to_on": outcome.inspected_to_on, "inspection_period_segments": [{"ordinal": segment.ordinal, "started_on": segment.started_on, "ended_on": segment.ended_on} for segment in segments], "decision_reference": outcome.decision_reference, "bbkt_reference": outcome.bbkt_reference, "outcome_result": outcome.outcome_result}, "capa_cycles": [{"round_no": cycle.round_no, "requested_on": cycle.requested_on, "submitted_on": cycle.submitted_on, "assessed_on": cycle.assessed_on, "assessor_name": cycle.assessor_name, "result": cycle.result, "status": cycle.status} for cycle in capa_cycles], "certificates": certificate_contexts, "legacy_lineage": [{"entity_type": mapping.entity_type.value, "legacy_id": mapping.legacy_id, "target_table": mapping.target_table, "target_entity_id": mapping.target_entity_id} for mapping in lineage]})
    return result


def _verify_read_only_rehearsal_connection(connection: Any) -> None:
    database_name = connection.execute(text("SELECT current_database()")).scalar_one()
    if database_name != REQUIRED_DATABASE_NAME:
        raise RuntimeError("reconciliation planner connected to a database other than the required rehearsal database")
    transaction_read_only = connection.execute(text("SHOW transaction_read_only")).scalar_one()
    if str(transaction_read_only).strip().lower() not in {"on", "true", "1"}:
        raise RuntimeError("reconciliation planner requires a read-only database transaction")


def run_read_only_plan_from_snapshot(database_url: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    require_rehearsal_database(database_url)
    legacy_rows = snapshot["legacy_rows"]
    engine = build_engine(database_url)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False, expire_on_commit=False)
    try:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        _verify_read_only_rehearsal_connection(connection)
        ids = [legacy_id for legacy_id in (_row_id(normalize_row(row["__source_ktra"])) for row in legacy_rows) if legacy_id is not None]
        canonical = _canonical_snapshot(session, ids)
        report = build_reconciliation_plan(legacy_rows, canonical)
        # Provenance/counts are safe metadata only; raw snapshot rows never enter the plan.
        report["source_snapshot"] = snapshot["provenance"]
        report["source_snapshot_validation"] = snapshot["validation_counts"]
        return report
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def run_read_only_plan(database_url: str, workbook: Path, *, expected_workbook_sha256: str | None = None) -> dict[str, Any]:
    """Windows-only convenience path; JSON snapshot mode remains platform independent."""
    from backend.app.domain.legacy_snapshot import read_core_sheet_rows
    from tools.export_inspection_case_lifecycle_legacy_snapshot import build_snapshot_payload

    source_rows = read_core_sheet_rows(workbook)
    snapshot = load_legacy_snapshot_payload(
        build_snapshot_payload(workbook, source_rows),
        expected_workbook_sha256=expected_workbook_sha256,
    )
    return run_read_only_plan_from_snapshot(database_url, snapshot)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a read-only inspection lifecycle reconciliation plan.")
    parser.add_argument("--database-url", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--legacy-snapshot", type=Path)
    source.add_argument("--workbook", type=Path)
    parser.add_argument("--expected-workbook-sha256")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.legacy_snapshot is not None:
        snapshot = load_legacy_snapshot_json(
            args.legacy_snapshot.resolve(),
            expected_workbook_sha256=args.expected_workbook_sha256,
        )
        report = run_read_only_plan_from_snapshot(args.database_url, snapshot)
    else:
        report = run_read_only_plan(
            args.database_url,
            args.workbook.resolve(),
            expected_workbook_sha256=args.expected_workbook_sha256,
        )
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.resolve().write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print("STATUS=READ_ONLY_DRY_RUN_PLAN")
    print(f"MATCHED_CASES={report['summary']['matched_cases']}")
    print(f"OUTPUT={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
