"""Read-only B6A legacy workbook coverage discovery; it never opens a DB."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any

from backend.app.domain.legacy_db_ktra_reconciliation import (
    parse_legacy_inspection_decisions,
    parse_legacy_minutes_records,
    safe_evidence,
)
from backend.app.domain.legacy_db_ktra_source_v2 import (
    excel_serial_date,
    snapshot_cell_value,
    snapshot_columns,
    substantive_source_value,
)
from backend.app.domain.legacy_db_ktra_repeatable_v2 import excel_serial_minutes_representation_equivalent
from backend.app.domain.legacy_ttvien_personnel import build_personnel_plan
from backend.app.domain.legacy_snapshot_v2 import SCHEMA_VERSION, snapshot_bytes
from backend.app.domain.phase2_import import parse_int
from tools.plan_db_ktra_reconciliation import SNAPSHOT as SNAPSHOT_V1_PATH
from tools.plan_db_ktra_reconciliation import load_snapshot as load_v1_snapshot

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK_SHA256 = "c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d"
SNAPSHOT_SHA256 = "484cf37603aacc5ff01a7bde5ffab01ed444748d5c7b1a0b30e7fc3a04936caa"
SNAPSHOT_V1_SHA256 = "b3bde05963e4e4d14d5b244e7c62b0f810f1cbbe206750574def6a366bdf7296"
_ABSENT_SOURCE_ROW = object()
CORE = {"db.cty", "db.cso", "db.ktra", "db.cc", "db.dkkd", "db.Tdoi", "db.Tdoi2"}
REPORT_ONLY = {"DsCB", "DsCB GMP", "DsCBKT", "DsCBDDK", "DsCs", "DsCty", "KH", "Lịch sử TTV", "Thống kê"}
OBSOLETE = {"Nhóm 1c"}
REFERENCE = {"Địa danh", "Dịch-Viết tắt", "Loc", "Phạm vi CN", "GSP", "GMP", "GLP", "GMPbb", "GMPnn", "KHKT", "Liên hệ", "Ngừng CN", "SXVX", "db.DC"}


def _chain(domain, sheet, region, headers, owner, fields, roles, state, **extra):
    return {"domain": domain, "sheet": sheet, "region": region, "headers": tuple(headers), "owner": owner, "fields": fields, "roles": roles, "state": state, **extra}


# Each header is (literal header, visual occurrence). Roles are reviewed owners,
# never inferred from another role's module-name string.
CHAINS = (
    _chain("companies", "db.cty", "company identity and names", [("ID", 1), ("MÃ CTY GMP", 1), ("MÃ CTY GLP", 1), ("MÃ CTY GMPbb", 1), ("TÊN CÔNG TY", 1), ("COMPANY NAME", 1)], "Company", ["Company.legacy_company_id"], {"semantic_parser_owner": None, "planner_owner": None, "writer_owner": "backend.app.domain.phase2_import.import_snapshot", "schema_owner": "backend.app.db.models.phase1.Company", "runtime_writer": "company service/API", "runtime_reader": "company/search read models"}, ("PRESENT", "ABSENT", "IMPLEMENTED", "UNKNOWN", "NONE", "PRESENT", "PRESENT", "V1")),
    _chain("sites_facilities", "db.cso", "site identity and address", [("ID", 1), ("ID Cty", 1), ("TÊN CƠ SỞ", 1), ("SITE NAME", 1), ("ĐỊA CHỈ CƠ SỞ", 1), ("TỈNH/TP", 1)], "Site", ["Site.legacy_site_id"], {"semantic_parser_owner": None, "planner_owner": None, "writer_owner": "backend.app.domain.phase2_import.import_snapshot", "schema_owner": "backend.app.db.models.phase1.Site", "runtime_writer": "site service/API", "runtime_reader": "case/search read models"}, ("PRESENT", "ABSENT", "IMPLEMENTED", "UNKNOWN", "NONE", "PRESENT", "PRESENT", "V1")),
    _chain("cases_inspections", "db.ktra", "case identity and inspection context", [("ID", 1), ("LOẠI KT", 1), ("ID CƠ SỞ", 1), ("MÃ DC", 1), ("TIÊU CHUẨN ÁP DỤNG", 1), ("LOẠI KIỂM TRA", 1)], "Case", ["Case.legacy_inspection_id", "Case.gxp_type", "Case.site_id"], {"semantic_parser_owner": "backend.app.domain.phase2_import", "planner_owner": "tools.plan_db_ktra_reconciliation", "writer_owner": "backend.app.domain.phase2_import.import_snapshot", "schema_owner": "backend.app.db.models.phase1.Case", "runtime_writer": "workflow service", "runtime_reader": "case workspace and search"}, ("PRESENT", "PRESENT", "IMPLEMENTED", "UNKNOWN", "NONE", "PRESENT", "PRESENT", "V1")),
    _chain("case_evaluation_scope", "db.ktra", "PHẠM VI KIỂM TRA", [("PHẠM VI KIỂM TRA", 1)], "CaseEvaluationScope", ["CaseEvaluationScope"], {"semantic_parser_owner": "backend.app.domain.phase2_import._import_case_evaluation_scope", "planner_owner": None, "writer_owner": "backend.app.domain.phase2_import.import_snapshot", "schema_owner": "backend.app.db.models.phase1.CaseEvaluationScope", "runtime_writer": "case scope service", "runtime_reader": "case workspace scope"}, ("PRESENT", "PRESENT", "IMPLEMENTED", "UNKNOWN", "NONE", "PRESENT", "PRESENT", "V1")),
    _chain("inspection_planning", "db.ktra", "application and assessment", [("Ngày nộp", 1), ("Mã hồ sơ", 1), ("Ngày thẩm định", 1), ("Người thẩm định", 1), ("Kết quả", 1)], "CaseApplication; CaseAssessment", ["CaseApplication", "CaseAssessment"], {"semantic_parser_owner": "backend.app.domain.phase2_import", "planner_owner": None, "writer_owner": "backend.app.domain.phase2_import.import_snapshot", "schema_owner": "backend.app.db.models.phase1.CaseApplication; CaseAssessment", "runtime_writer": "case workflow service", "runtime_reader": "case workspace"}, ("PRESENT", "PRESENT", "IMPLEMENTED", "UNKNOWN", "NONE", "PRESENT", "PRESENT", "V1")),
    _chain("inspection_periods", "db.ktra", "Ngày K.tra", [("Ngày K.tra", 1)], "InspectionOutcome; InspectionPeriodSegment", ["InspectionOutcome inspection period fields", "InspectionPeriodSegment"], {"semantic_parser_owner": "backend.app.domain.inspection_periods", "planner_owner": "tools.plan_db_ktra_reconciliation", "writer_owner": "backend.app.domain.phase2_import.import_snapshot", "schema_owner": "backend.app.db.models.phase1.InspectionOutcome; InspectionPeriodSegment", "runtime_writer": "inspection workflow service", "runtime_reader": "case workspace inspection projection"}, ("PRESENT", "PRESENT", "IMPLEMENTED", "UNKNOWN", "NONE", "PRESENT", "PRESENT", "V1")),
    _chain("inspection_decisions", "db.ktra", "Q. định", [("Q. định", 1)], "InspectionDecision", ["InspectionDecision reference/date/raw/relation"], {"semantic_parser_owner": "backend.app.domain.legacy_db_ktra_reconciliation.parse_legacy_inspection_decisions", "planner_owner": "tools.plan_db_ktra_repeatable_semantics", "writer_owner": "tools.apply_db_ktra_repeatable_semantics", "schema_owner": "backend.app.db.models.phase1.InspectionDecision; migrations 0013/0014", "runtime_writer": "inspection workflow service", "runtime_reader": "case workspace inspection projection"}, ("PRESENT", "PRESENT", "IMPLEMENTED", "UNKNOWN", "NONE", "PRESENT", "PRESENT", "V1"), candidate={"count": 1219, "evidence_type": "CODE_FENCE_EXPECTATION", "evidence_source": "tools.apply_db_ktra_repeatable_semantics.EXPECTED_COUNTS.decisions", "required_revision": "20260913_0014", "idempotency": "guarded same-or-empty validation"}),
    _chain("inspection_minutes", "db.ktra", "B. bản", [("B. bản", 1)], "InspectionMinutesRecord", ["InspectionMinutesRecord date/time/raw"], {"semantic_parser_owner": "backend.app.domain.legacy_db_ktra_reconciliation.parse_legacy_minutes_records", "planner_owner": "tools.plan_db_ktra_repeatable_semantics", "writer_owner": "tools.apply_db_ktra_repeatable_semantics", "schema_owner": "backend.app.db.models.phase1.InspectionMinutesRecord; migrations 0013/0014", "runtime_writer": "inspection workflow service", "runtime_reader": "case workspace inspection projection"}, ("PRESENT", "PRESENT", "IMPLEMENTED", "UNKNOWN", "NONE", "PRESENT", "PRESENT", "V1"), candidate={"count": 1162, "evidence_type": "CODE_FENCE_EXPECTATION", "evidence_source": "tools.apply_db_ktra_repeatable_semantics.EXPECTED_COUNTS.minutes", "required_revision": "20260913_0014", "idempotency": "guarded same-or-empty validation"}),
    _chain("inspection_outcomes", "db.ktra", "outcome, final evaluation, and compliance", [("Đ. giá", 1), ("ĐÁNH GIÁ CUỐI", 1), ("HẠN KT TUÂN THỦ", 1)], "InspectionOutcome", ["InspectionOutcome.outcome_result", "InspectionOutcome.final_evaluation", "InspectionOutcome.compliance_due_on"], {"semantic_parser_owner": "backend.app.domain.legacy_db_ktra_reconciliation", "planner_owner": "tools.plan_db_ktra_reconciliation", "writer_owner": "tools.apply_db_ktra_reconciliation", "schema_owner": "backend.app.db.models.phase1.InspectionOutcome", "runtime_writer": "inspection workflow service", "runtime_reader": "case workspace inspection projection"}, ("PRESENT", "PRESENT", "IMPLEMENTED", "UNKNOWN", "NONE", "PRESENT", "PRESENT", "V1")),
    _chain("approval_submissions", "db.ktra", "PCT and CT submissions", [("PHIẾU TRÌNH PCT", 1), ("PHIẾU TRÌNH CT", 1)], "InspectionApprovalSubmission", ["InspectionApprovalSubmission PCT/CT occurrences"], {"semantic_parser_owner": "backend.app.domain.legacy_db_ktra_reconciliation", "planner_owner": None, "writer_owner": None, "schema_owner": "backend.app.db.models.phase1.InspectionApprovalSubmission", "runtime_writer": "inspection workflow service", "runtime_reader": "case workspace inspection projection"}, ("PRESENT", "PRESENT", "ABSENT", "UNKNOWN", "NONE", "PRESENT", "PRESENT", "V1")),
    _chain("inspection_teams", "db.ktra", "T.tra viên", [("T.tra viên", 1)], "InspectionTeam; InspectionTeamMember", ["InspectionTeam display_text", "InspectionTeamMember identity/provenance"], {"semantic_parser_owner": "backend.app.domain.legacy_inspection_team", "planner_owner": "tools.plan_inspection_teams_b5b", "writer_owner": "backend.app.services.legacy_inspection_team_import", "schema_owner": "backend.app.db.models.phase1.InspectionTeam; InspectionTeamMember; migrations 0016", "runtime_writer": "backend.app.services.workflow", "runtime_reader": "case workspace team read model"}, ("PRESENT", "PRESENT", "IMPLEMENTED", "NONE", "PASS", "PRESENT", "PRESENT", "V2"), implementation_verified="DISPOSABLE_POSTGRES_PASS_REHEARSAL_NOT_APPLIED"),
    _chain("certificates", "db.cc", "certificate identity and validity", [("ID", 1), ("LOẠI CC", 1), ("ID ĐỢT KTRA", 1), ("Mã số CC", 1), ("Ngày cấp CC", 1), ("Hết hạn CC", 1)], "Certificate; CertificateVersion; CertificateScope", ["Certificate", "CertificateVersion", "CertificateScope"], {"semantic_parser_owner": "backend.app.domain.phase2_import", "planner_owner": None, "writer_owner": "backend.app.domain.phase2_import.import_snapshot", "schema_owner": "backend.app.db.models.phase1.Certificate", "runtime_writer": "certificate service", "runtime_reader": "certificate/case workspace"}, ("PRESENT", "PRESENT", "IMPLEMENTED", "UNKNOWN", "NONE", "PRESENT", "PRESENT", "V1")),
    _chain("business_eligibility", "db.dkkd", "business-eligibility certificate and replacement", [("ID", 1), ("ID CƠ SỞ", 1), ("Số QĐ cấp", 1), ("Mã số CC", 1), ("Ngày cấp CC", 1), ("THAY THẾ GIẤY ID", 1)], "BusinessEligibilityCertificate; BusinessEligibilityVersion", ["BusinessEligibilityCertificate", "BusinessEligibilityVersion"], {"semantic_parser_owner": "backend.app.domain.phase2_import", "planner_owner": None, "writer_owner": "backend.app.domain.phase2_import.import_snapshot", "schema_owner": "backend.app.db.models.phase1.BusinessEligibilityCertificate", "runtime_writer": "business eligibility service", "runtime_reader": "business eligibility read model"}, ("PRESENT", "PRESENT", "IMPLEMENTED", "UNKNOWN", "NONE", "PRESENT", "PRESENT", "V1")),
    _chain("change_management", "db.Tdoi", "change request", [("ID", 1), ("PHẠM VI", 1), ("ID CƠ SỞ", 1), ("Ngày nộp", 1), ("PHIẾU TRÌNH PCT", 1), ("PHIẾU TRÌNH CT", 1)], "ChangeRequest; ChangeApproval", ["ChangeRequest", "ChangeApproval"], {"semantic_parser_owner": "backend.app.domain.phase2_import", "planner_owner": None, "writer_owner": "backend.app.domain.phase2_import.import_snapshot", "schema_owner": "backend.app.db.models.phase1.ChangeRequest", "runtime_writer": "change workflow service", "runtime_reader": "change workspace"}, ("PRESENT", "PRESENT", "IMPLEMENTED", "UNKNOWN", "NONE", "PRESENT", "PRESENT", "V1")),
    _chain("change_management", "db.Tdoi2", "change request details", [("ID", 1), ("ID Gốc", 1), ("PHÂN LOẠI", 1), ("TÌNH TRẠNG CHẤP NHẬN", 1), ("THÔNG TIN CŨ", 1), ("THÔNG TIN MỚI", 1)], "ChangeRequestDetail", ["ChangeRequestDetail"], {"semantic_parser_owner": "backend.app.domain.phase2_import", "planner_owner": None, "writer_owner": "backend.app.domain.phase2_import.import_snapshot", "schema_owner": "backend.app.db.models.phase1.ChangeRequestDetail", "runtime_writer": "change workflow service", "runtime_reader": "change workspace"}, ("PRESENT", "PRESENT", "IMPLEMENTED", "UNKNOWN", "NONE", "PRESENT", "PRESENT", "V1")),
    _chain("personnel", "TTviên", "TTviên personnel roster", [("HỌ TÊN", 1), ("CHỨC DANH", 1), ("ĐƠN VỊ", 1), ("Ngừng hoạt động", 1), ("Chuyên môn", 1)], "Person; InspectorProfile; LegacyInspectorSourceRecord", ["Person", "InspectorProfile", "LegacyInspectorSourceRecord"], {"semantic_parser_owner": "backend.app.domain.legacy_ttvien_personnel", "planner_owner": "tools.plan_ttvien_personnel", "writer_owner": "backend.app.services.legacy_ttvien_personnel_import", "schema_owner": "backend.app.db.models.phase1.Person; InspectorProfile; LegacyInspectorSourceRecord; migrations 0015", "runtime_writer": "catalog/personnel service", "runtime_reader": "inspection-team selector/read model"}, ("PRESENT", "PRESENT", "IMPLEMENTED", "PASS", "NONE", "PRESENT", "PRESENT", "V2"), implementation_verified="HISTORICALLY_VERIFIED_NOT_RECHECKED", historical_counts={"Person": 358, "InspectorProfile": 358, "LegacyInspectorSourceRecord": 358, "evidence_type": "REHEARSAL_OBSERVED"}),
)


def _sha(path: Path) -> str: return sha256(path.read_bytes()).hexdigest()

def _shape(value: object) -> str:
    if value is None: return "NULL"
    if isinstance(value, bool): return "BOOLEAN"
    if isinstance(value, (int, float)): return "NUMBER"
    if not isinstance(value, str): return type(value).__name__.upper()
    if not value: return "BLANK"
    if value.strip() in {"-", "???"}: return "SENTINEL"
    return "TEXT_MULTILINE" if "\n" in value or "\r" in value else "TEXT"

def _sheet_classification(name: str) -> str:
    if name in CORE or name == "TTviên": return "AUTHORITATIVE_SOURCE" if name == "TTviên" else "TRANSACTION_SOURCE"
    if name in REPORT_ONLY: return "REPORT_OR_DERIVED_ONLY"
    if name in OBSOLETE: return "OBSOLETE"
    if name in REFERENCE: return "REFERENCE_SOURCE"
    return "UNKNOWN_REQUIRES_REVIEW"

def _field_evidence(sheet: dict[str, Any], label: str, wanted_occurrence: int, *, eligible_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    matches = [{"header": label, "header_row_number": row["source_row_number"], "column_ordinal": cell["column_ordinal"]} for row in sheet.get("raw_rows", []) for cell in row.get("cells", []) if cell.get("raw_value") == label]
    matches.sort(key=lambda item: (item["header_row_number"], item["column_ordinal"]))
    if wanted_occurrence > len(matches): raise ValueError(f"Snapshot V2 header {label!r} occurrence {wanted_occurrence} is absent from {sheet.get('sheet_name')}")
    header = {**matches[wanted_occurrence - 1], "occurrence": wanted_occurrence}
    raw_rows = [row for row in sheet.get("raw_rows", []) if row.get("source_row_number", 0) > header["header_row_number"]]
    rows = raw_rows if eligible_rows is None else eligible_rows
    values = [snapshot_cell_value(row, header["column_ordinal"]) for row in rows]
    nonblank = [value for value in values if value not in (None, "")]
    return {"source_header": header, "raw_post_header_rows": len(raw_rows), "source_candidate_rows": len(rows), "migration_eligible_rows": len(rows), "observed_value_count": len(values), "nonblank_count": len(nonblank), "distinct_count": len({json.dumps(value, ensure_ascii=False, sort_keys=True) for value in nonblank}), "source_state_counts": dict(sorted(Counter(_shape(value) for value in values).items()))}

def _region_evidence(sheet: dict[str, Any], headers: tuple[tuple[str, int], ...], *, eligible_rows: list[dict[str, Any]] | None = None, population_basis: str = "POPULATION_CONTRACT_UNRESOLVED") -> dict[str, Any]:
    fields = [_field_evidence(sheet, label, occurrence, eligible_rows=eligible_rows) for label, occurrence in headers]
    states = Counter()
    for field in fields: states.update(field["source_state_counts"])
    return {"population_basis": population_basis, "region_kind": "FIELD" if len(fields) == 1 else "MULTI_FIELD_REGION", "fields": fields, "aggregate": {"field_count": len(fields), "raw_post_header_rows": max(field["raw_post_header_rows"] for field in fields), "source_candidate_rows": max(field["source_candidate_rows"] for field in fields), "migration_eligible_rows": max(field["migration_eligible_rows"] for field in fields), "observed_value_count": sum(field["observed_value_count"] for field in fields), "nonblank_count": sum(field["nonblank_count"] for field in fields), "distinct_count_per_field_total": sum(field["distinct_count"] for field in fields), "source_state_counts": dict(sorted(states.items()))}}


def _db_ktra_eligible_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Use the shared Snapshot V2 coordinate and eligibility primitives."""
    required = ("ID", "LOẠI KT", "ID CƠ SỞ")
    rows, columns = snapshot_columns(snapshot, "db.ktra", required_headers=required)
    if any(name not in columns for name in required):
        raise ValueError("db.ktra effective-case eligibility columns are missing")
    return [
        row for row in rows
        if isinstance(row.get("source_row_number"), int)
        and row["source_row_number"] > 4
        and parse_int(snapshot_cell_value(row, columns["ID"])) is not None
        and substantive_source_value(snapshot_cell_value(row, columns["LOẠI KT"]))
        and substantive_source_value(snapshot_cell_value(row, columns["ID CƠ SỞ"]))
    ]


def _ttvien_evidence(snapshot: dict[str, Any], snapshot_sha256: str) -> dict[str, Any]:
    """Use the personnel planner's c4..c16 semantic contract, not its layout header."""
    plan = build_personnel_plan(snapshot, expected_snapshot_sha256=snapshot_sha256)
    sheet = next(item for item in snapshot["sheets"] if item.get("sheet_name") == "TTviên")
    rows_by_number = {row["source_row_number"]: row for row in sheet["raw_rows"]}
    eligible = [rows_by_number[item["source_row_number"]] for item in plan["records"]]
    layout_header = _field_evidence(sheet, "HỌ TÊN", 1)
    fields = []
    for column, semantic_name in ((4, "honorific"), (5, "qualification"), (6, "full_name"), (7, "position"), (8, "organizational_unit"), (14, "inactive_marker"), (16, "professional_specialty")):
        values = [snapshot_cell_value(row, column) for row in eligible]
        nonblank = [value for value in values if value not in (None, "")]
        fields.append({"semantic_field": semantic_name, "semantic_column_ordinal": column, "layout_header_evidence": layout_header["source_header"], "raw_post_header_rows": layout_header["raw_post_header_rows"], "source_candidate_rows": len(eligible), "migration_eligible_rows": len(eligible), "observed_value_count": len(values), "nonblank_count": len(nonblank), "distinct_count": len({json.dumps(value, ensure_ascii=False, sort_keys=True) for value in nonblank}), "source_state_counts": dict(sorted(Counter(_shape(value) for value in values).items()))})
    specialty = next(item for item in fields if item["semantic_field"] == "professional_specialty")
    if len(plan["records"]) != 358 or specialty["nonblank_count"] != 38 or specialty["distinct_count"] != 7:
        raise ValueError("TTviên semantic-coordinate population invariant failed")
    return {"population_basis": "CANONICAL_TTVIEN_PERSONNEL", "region_kind": "SEMANTIC_LAYOUT_REGION", "fields": fields, "aggregate": {"field_count": len(fields), "raw_post_header_rows": layout_header["raw_post_header_rows"], "source_candidate_rows": len(eligible), "migration_eligible_rows": len(eligible), "professional_specialty_nonblank_count": specialty["nonblank_count"], "professional_specialty_distinct_count": specialty["distinct_count"]}, "layout_header_evidence": layout_header["source_header"]}


def _v2_repeatable_rows(snapshot: dict[str, Any]) -> dict[int, dict[str, object]]:
    required = ("ID", "Q. định", "B. bản")
    rows, columns = snapshot_columns(snapshot, "db.ktra", required_headers=required)
    result: dict[int, dict[str, object]] = {}
    for row in rows:
        legacy_id = parse_int(snapshot_cell_value(row, columns["ID"]))
        if legacy_id is None:
            continue
        if legacy_id in result:
            raise ValueError("Snapshot V2 db.ktra has duplicate valid legacy ID")
        result[legacy_id] = {"decision": snapshot_cell_value(row, columns["Q. định"]), "minutes": snapshot_cell_value(row, columns["B. bản"])}
    return result


def _minutes_numeric_conversion(value: object) -> tuple[object, str]:
    """Only whole Excel serial dates have a proven date-only conversion here."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return value, "NOT_NUMERIC"
    numeric = float(value)
    if not numeric.is_integer():
        return value, "NUMERIC_UNRESOLVED"
    converted = excel_serial_date(value)
    if converted is None:
        return value, "NUMERIC_UNRESOLVED"
    return converted.strftime("%d/%m/%Y"), "NUMERIC_CONVERTED_EXCEL_SERIAL_DATE"


def _safe_occurrences(
    parsed: dict[str, Any],
    keys: tuple[str, ...],
    *,
    kind: str,
) -> list[tuple[object, ...]]:
    result = []
    for item in parsed["occurrences"]:
        normalized = dict(item)
        result.append(tuple(normalized.get(key).isoformat() if hasattr(normalized.get(key), "isoformat") else normalized.get(key) for key in keys))
    return result


def _crosswalk_row(legacy_id: int, v1_value: object, v2_value: object, *, kind: str) -> dict[str, Any]:
    parser = parse_legacy_inspection_decisions if kind == "decisions" else parse_legacy_minutes_records
    conversion = "NOT_APPLICABLE"
    parser_value = v2_value
    if kind == "minutes":
        parser_value, conversion = _minutes_numeric_conversion(v2_value)
    if v1_value is _ABSENT_SOURCE_ROW:
        return {"legacy_inspection_id": legacy_id, "classification": "V2_ONLY", "conversion_classification": "SOURCE_DIFFERENCE"}
    if v2_value is _ABSENT_SOURCE_ROW:
        return {"legacy_inspection_id": legacy_id, "classification": "V1_ONLY", "conversion_classification": "SOURCE_DIFFERENCE"}
    v1, v2 = parser(v1_value), parser(parser_value)
    keys = ("ordinal", "reference", "decision_on", "relation_type", "replaces_source_reference") if kind == "decisions" else ("ordinal", "recorded_on", "recorded_time", "precision", "source_format")
    representation_equivalent = (
        kind == "minutes"
        and len(v1["occurrences"]) == len(v2["occurrences"])
        and bool(v1["occurrences"])
        and all(
            excel_serial_minutes_representation_equivalent(
                source_representation=conversion,
                expected=v2_occurrence,
                historical=v1_occurrence,
            )
            for v1_occurrence, v2_occurrence in zip(v1["occurrences"], v2["occurrences"], strict=True)
        )
    )
    semantic_match = v1["state"] == v2["state"] and (
        representation_equivalent
        or _safe_occurrences(v1, keys, kind=kind) == _safe_occurrences(v2, keys, kind=kind)
    )
    if semantic_match:
        classification = "EXACT_SEMANTIC_MATCH" if str(v1_value).strip() == str(v2_value).strip() else "REPRESENTATION_ONLY_DIFFERENCE"
        conversion_classification = (
            "NUMERIC_DATE_EQUIVALENT" if conversion == "NUMERIC_CONVERTED_EXCEL_SERIAL_DATE" else
            "MISSING_EQUIVALENT" if v1["state"] == "MISSING" else "TEXT_EQUIVALENT"
        )
    else:
        classification = "PARSER_SEMANTIC_DIFFERENCE"
        conversion_classification = "NUMERIC_DATE_MISMATCH" if conversion == "NUMERIC_CONVERTED_EXCEL_SERIAL_DATE" else "NUMERIC_UNRESOLVED" if conversion == "NUMERIC_UNRESOLVED" else "SOURCE_DIFFERENCE"
    return {
        "legacy_inspection_id": legacy_id, "classification": classification,
        "conversion_classification": conversion_classification,
        "v1_state": v1["state"], "v2_state": v2["state"],
        "v1_occurrence_count": len(v1["occurrences"]), "v2_occurrence_count": len(v2["occurrences"]),
        "v1_evidence": safe_evidence(v1_value), "v2_evidence": safe_evidence(v2_value),
        "conversion_evidence": conversion,
    }


def _repeatable_crosswalk(snapshot: dict[str, Any]) -> dict[str, Any]:
    v1_rows = {parse_int(row.get("ID", "")): row for row in load_v1_snapshot(SNAPSHOT_V1_PATH) if parse_int(row.get("ID", "")) is not None}
    v2_rows = _v2_repeatable_rows(snapshot)
    ids = sorted(set(v1_rows) | set(v2_rows))
    fields = {
        "decisions": ("decision_reference", "decision"),
        "minutes": ("bbkt_reference", "minutes"),
    }
    compared: dict[str, dict[str, Any]] = {}
    for name, (v1_key, v2_key) in fields.items():
        rows = [_crosswalk_row(legacy_id, v1_rows[legacy_id][v1_key] if legacy_id in v1_rows else _ABSENT_SOURCE_ROW, v2_rows[legacy_id][v2_key] if legacy_id in v2_rows else _ABSENT_SOURCE_ROW, kind=name) for legacy_id in ids]
        compared[name] = {
            "rows": rows,
            "classification_counts": dict(sorted(Counter(row["classification"] for row in rows).items())),
            "conversion_classification_counts": dict(sorted(Counter(row["conversion_classification"] for row in rows).items())),
            "mismatch_legacy_ids": [row["legacy_inspection_id"] for row in rows if row["classification"] in {"V1_ONLY", "V2_ONLY", "PARSER_SEMANTIC_DIFFERENCE", "UNRESOLVED"}],
            "v1_source_occurrences": sum(row["v1_occurrence_count"] for row in rows if "v1_occurrence_count" in row),
            "v2_source_occurrences": sum(row["v2_occurrence_count"] for row in rows if "v2_occurrence_count" in row),
        }
    return {
        "schema_version": "b6a-v1-v2-repeatable-crosswalk/v1",
        "provenance": {"v1_snapshot_path": "artifacts/phase3c/legacy_snapshot.json", "v1_snapshot_sha256": SNAPSHOT_V1_SHA256, "v2_snapshot_path": "artifacts/phase3c/legacy_snapshot_v2.json", "v2_snapshot_sha256": SNAPSHOT_SHA256, "population_basis": "VALID_LEGACY_ID", "v1_valid_legacy_ids": len(v1_rows), "v2_valid_legacy_ids": len(v2_rows), "shared_legacy_ids": len(set(v1_rows) & set(v2_rows))},
        "fields": compared,
        "old_v1_rehearsal_write_candidate_fence": {"classification": "REHEARSAL_OWNER_FILTERED_WRITE_CANDIDATES", "decisions": 1219, "minutes": 1162, "current_rehearsal_verification": "NOT_CHECKED"},
        "owner_filtering_accounting": {"decisions": {"v1_source_occurrences": compared["decisions"]["v1_source_occurrences"], "old_v1_write_candidate_fence": 1219, "unattributed_without_rehearsal_classification_artifact": compared["decisions"]["v1_source_occurrences"] - 1219}, "minutes": {"v1_source_occurrences": compared["minutes"]["v1_source_occurrences"], "old_v1_write_candidate_fence": 1162, "unattributed_without_rehearsal_classification_artifact": compared["minutes"]["v1_source_occurrences"] - 1162}},
        "numeric_conversion_contract": {"owner": "backend.app.domain.legacy_db_ktra_source_v2.excel_serial_date", "input": "whole-number Excel serial date", "output": "DMY date-only parser input; no clock time or timezone is invented", "canonical_precision": "DATE_ONLY", "recorded_time": None, "fractional_serial_policy": "NUMERIC_UNRESOLVED"},
    }

def _state(chain: dict[str, Any]) -> dict[str, str]:
    schema, parser, writer, historical, disposable, reader, runtime_writer, lineage = chain["state"]
    status = "IMPLEMENTATION_PRESENT_CURRENT_REHEARSAL_NOT_CHECKED"
    if writer == "ABSENT": status = "NO_STRUCTURED_WRITER_IMPLEMENTED"
    if chain.get("implementation_verified") == "HISTORICALLY_VERIFIED_NOT_RECHECKED": status = "HISTORICALLY_VERIFIED_NOT_RECHECKED"
    if chain.get("implementation_verified") == "DISPOSABLE_POSTGRES_PASS_REHEARSAL_NOT_APPLIED": status = "IMPLEMENTATION_VERIFIED_REHEARSAL_NOT_APPLIED"
    return {"schema": schema, "parser": parser, "planner": "PRESENT" if chain["roles"]["planner_owner"] else "ABSENT", "writer": writer, "historical_rehearsal_verification": historical, "current_rehearsal_verification": "NOT_CHECKED", "disposable_postgres_verification": disposable, "runtime_reader": reader, "runtime_writer": runtime_writer, "source_lineage": lineage, "migration_status": status}

def _owner_status(owner: str | None) -> str:
    if owner is None:
        return "ABSENT"
    first = owner.split(";", 1)[0].strip()
    parts = first.split(".")
    for size in range(len(parts), 0, -1):
        candidate = ROOT.joinpath(*parts[:size]).with_suffix(".py")
        if candidate.exists():
            if size == len(parts):
                return "VERIFIED_MODULE"
            symbol = parts[size]
            tree = ast.parse(candidate.read_text(encoding="utf-8"))
            if any(getattr(node, "name", None) == symbol for node in ast.walk(tree)):
                return "VERIFIED_SYMBOL"
            return "VERIFIED_MODULE"
    return "DECLARED_NOT_INTROSPECTED"


def _population_basis(chain: dict[str, Any]) -> str:
    if chain["sheet"] == "TTviên":
        return "CANONICAL_TTVIEN_PERSONNEL"
    if chain["sheet"] == "db.ktra":
        return "CANONICAL_DB_KTRA_CASE"
    if chain["sheet"] in CORE:
        return "VALID_LEGACY_ID"
    return "POPULATION_CONTRACT_UNRESOLVED"


def _valid_id_rows(sheet: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        id_header = _field_evidence(sheet, "ID", 1)["source_header"]
    except ValueError:
        return []
    return [row for row in sheet.get("raw_rows", []) if row.get("source_row_number", 0) > id_header["header_row_number"] and parse_int(snapshot_cell_value(row, id_header["column_ordinal"])) is not None]


def _record(snapshot: dict[str, Any], sheet: dict[str, Any], chain: dict[str, Any], *, snapshot_sha256: str, crosswalk: dict[str, Any]) -> dict[str, Any]:
    basis = _population_basis(chain)
    if chain["sheet"] == "TTviên":
        evidence = _ttvien_evidence(snapshot, snapshot_sha256)
    elif chain["sheet"] == "db.ktra":
        evidence = _region_evidence(sheet, chain["headers"], eligible_rows=_db_ktra_eligible_rows(snapshot), population_basis=basis)
    else:
        eligible = _valid_id_rows(sheet) if basis == "VALID_LEGACY_ID" else None
        evidence = _region_evidence(sheet, chain["headers"], eligible_rows=eligible, population_basis=basis)
    item = {"domain": chain["domain"], "source_sheet": chain["sheet"], "source_field_or_region": chain["region"], "source_evidence": evidence, "business_classification": _sheet_classification(chain["sheet"]), "canonical_owner": chain["owner"], "canonical_fields": chain["fields"], **chain["roles"], "owner_verification": {role: _owner_status(owner) for role, owner in chain["roles"].items()}, "state_vector": _state(chain), "evidence_strength": "SNAPSHOT_V2_FIELD_COORDINATES_PLUS_SOURCE_LEVEL_OWNER_TRACE", "known_contamination_or_legacy_compatibility": ["No DB connection; current rehearsal verification is NOT_CHECKED."], "unresolved_questions": []}
    for key in ("candidate", "historical_counts", "implementation_verified"):
        if key in chain: item[{"candidate": "candidate_count_evidence", "historical_counts": "historical_verification_evidence", "implementation_verified": "implementation_verification_status"}[key]] = chain[key]
    if "candidate_count_evidence" in item:
        observed_key = "decisions" if chain["domain"] == "inspection_decisions" else "minutes"
        source = crosswalk["fields"][observed_key]
        item["candidate_count_evidence"] = {"v1_source_occurrences": source["v1_source_occurrences"], "v2_source_occurrences": source["v2_source_occurrences"], "old_v1_rehearsal_write_candidate_fence": item["candidate_count_evidence"]["count"], "write_candidate_evidence_type": "REHEARSAL_OWNER_FILTERED_WRITE_CANDIDATES", **{key: value for key, value in item["candidate_count_evidence"].items() if key != "count"}}
    return item

def _tracking(path: Path | None) -> dict[str, Any]:
    if path is None: return {"snapshot_v2_path": None, "git_tracking_status": "NOT_CHECKED", "origin_status": "NOT_CHECKED", "regeneration_performed": False, "regeneration_result": "NOT_REQUESTED"}
    rel = path.resolve().relative_to(ROOT).as_posix()
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "--", rel], cwd=ROOT, capture_output=True).returncode == 0
    ignored = subprocess.run(["git", "check-ignore", "-q", "--", rel], cwd=ROOT).returncode == 0
    return {"snapshot_v2_path": rel, "git_tracking_status": "TRACKED" if tracked else "LOCAL_UNTRACKED_CANONICAL_ARTIFACT", "origin_status": "GIT_TRACKED" if tracked else "LOCAL_IGNORED" if ignored else "LOCAL_UNTRACKED", "regeneration_performed": False, "regeneration_result": "NOT_REQUESTED"}

def _lineage(crosswalk: dict[str, Any]) -> dict[str, Any]:
    tools = [
        ("tools/plan_db_ktra_reconciliation.py", "V1", "planner", None), ("tools/apply_db_ktra_reconciliation.py", "V1", "guarded_writer", None), ("tools/plan_db_ktra_repeatable_semantics.py", "V1", "planner", None), ("tools/apply_db_ktra_repeatable_semantics.py", "V1", "guarded_writer", "20260913_0014"),
        ("tools/plan_ttvien_personnel.py", "V2", "planner", None), ("tools/plan_inspection_teams_b5b.py", "V2", "planner", None),
    ]
    tool_rows = []
    for tool, fmt, role, revision in tools:
        is_repeatable = "repeatable_semantics" in tool
        expected = {"decisions": 1219, "minutes": 1162} if is_repeatable else None
        source_summary = None if not is_repeatable else {name: {"v1_source_occurrences": crosswalk["fields"][name]["v1_source_occurrences"], "v2_source_occurrences": crosswalk["fields"][name]["v2_source_occurrences"], "classification_counts": crosswalk["fields"][name]["classification_counts"], "conversion_classification_counts": crosswalk["fields"][name]["conversion_classification_counts"]} for name in ("decisions", "minutes")}
        def source_semantics_status(name: str) -> str:
            field = crosswalk["fields"][name]
            if field["mismatch_legacy_ids"]:
                return "SOURCE_SEMANTICS_DIFFER"
            # Only minutes uses the proven Excel-serial representation adapter.
            if field["conversion_classification_counts"].get("NUMERIC_DATE_EQUIVALENT", 0):
                return "REPRESENTATION_EQUIVALENT_AFTER_PROVEN_CONVERSION"
            return "SOURCE_SEMANTICS_EQUIVALENT"

        states = [] if source_summary is None else [source_semantics_status(name) for name in ("decisions", "minutes")]
        verdict = "NOT_APPLICABLE" if fmt == "V2" else "REQUIRES_REPRESENTATION_ADAPTER" if "REPRESENTATION_EQUIVALENT_AFTER_PROVEN_CONVERSION" in states else "SAFE_TO_ADAPT_TO_V2" if states and all(state == "SOURCE_SEMANTICS_EQUIVALENT" for state in states) else "BLOCKED_UNRESOLVED"
        tool_rows.append({"tool": tool, "snapshot_format": fmt, "expected_snapshot_sha256": SNAPSHOT_V1_SHA256 if fmt == "V1" else SNAPSHOT_SHA256, "role": role, "parser_owner": "backend.app.domain.legacy_db_ktra_reconciliation" if "db_ktra" in tool else None, "writer_target": "InspectionDecision; InspectionMinutesRecord" if "repeatable" in tool else "legacy scalar owners" if "db_ktra" in tool else None, "old_v1_rehearsal_write_candidate_fence": expected, "current_rehearsal_candidate_counts": "NOT_CHECKED_NO_EXPLICIT_DATABASE_URL" if is_repeatable else None, "source_semantics": source_summary, "source_semantics_status": states or ["EQUIVALENCE_NOT_PROVEN"], "required_revision": revision, "reuse_verdict": verdict})
    return {"schema_version": "b6a-source-lineage-drift/v3", "snapshot_formats_equivalent": "ROW_LEVEL_REPEATABLE_SEMANTICS_PROVEN_ONLY_AS_REPORTED", "tools": tool_rows, "findings": [{"classification": "BLOCKS_B6B", "code": "V1_BOUND_DBKTRA_WRITER", "evidence": "Even row-level equivalence does not authorize reuse of a V1-bound writer; B6B must adapt the source contract."}]}

def build_reports(snapshot: dict[str, Any], *, snapshot_sha256: str, workbook_sha256: str, snapshot_path: Path | None = None):
    if snapshot.get("schema_version") != SCHEMA_VERSION or sha256(snapshot_bytes(snapshot)).hexdigest() != snapshot_sha256: raise ValueError("Snapshot V2 provenance guard failed")
    if snapshot.get("workbook", {}).get("sha256") != workbook_sha256: raise ValueError("Snapshot V2 workbook lineage guard failed")
    sheets = snapshot.get("sheets")
    if not isinstance(sheets, list): raise ValueError("Snapshot V2 sheets are malformed")
    indexed = {sheet.get("sheet_name"): sheet for sheet in sheets if isinstance(sheet, dict)}
    if len(indexed) != len(sheets): raise ValueError("Snapshot V2 sheet inventory is duplicated or malformed")
    crosswalk = _repeatable_crosswalk(snapshot)
    records = [_record(snapshot, indexed[chain["sheet"]], chain, snapshot_sha256=snapshot_sha256, crosswalk=crosswalk) for chain in CHAINS]
    covered = {chain["sheet"] for chain in CHAINS}
    for name in sorted(indexed):
        if name not in covered:
            cls = _sheet_classification(name)
            records.append({"domain": "unclassified_reference_or_report", "source_sheet": name, "source_field_or_region": "entire sheet region", "source_evidence": {"region_kind": "ENTIRE_SHEET_UNMAPPED", "fields": [], "aggregate": {"field_count": 0}}, "business_classification": cls, "canonical_owner": None, "canonical_fields": [], "semantic_parser_owner": None, "planner_owner": None, "writer_owner": None, "schema_owner": None, "runtime_writer": None, "runtime_reader": None, "state_vector": {"schema": "ABSENT", "parser": "ABSENT", "planner": "ABSENT", "writer": "ABSENT", "historical_rehearsal_verification": "NONE", "current_rehearsal_verification": "NOT_CHECKED", "disposable_postgres_verification": "NONE", "runtime_reader": "ABSENT", "runtime_writer": "ABSENT", "source_lineage": "UNKNOWN", "migration_status": "LEGACY_ONLY"}, "evidence_strength": "SNAPSHOT_V2_SHEET_INVENTORY_ONLY", "known_contamination_or_legacy_compatibility": [], "unresolved_questions": ["No approved canonical owner was found."] if cls == "REFERENCE_SOURCE" else []})
    records.sort(key=lambda item: (item["source_sheet"], item["source_field_or_region"]))
    provenance = {"snapshot_v2_sha256": snapshot_sha256, "snapshot_v2_schema_version": SCHEMA_VERSION, "workbook_sha256": workbook_sha256, **_tracking(snapshot_path), "database_inspection": "NOT_PERFORMED_NO_EXPLICIT_DATABASE_URL", "database_mutated": False, "importer_invoked": False}
    sheet_counts, region_counts = Counter(_sheet_classification(name) for name in indexed), Counter(item["business_classification"] for item in records)
    matrix = {"schema_version": "b6a-legacy-coverage-matrix/v2", "provenance": provenance, "sheet_classification_counts": dict(sorted(sheet_counts.items())), "field_region_classification_counts": dict(sorted(region_counts.items())), "records": records}
    domains: dict[str, list[dict[str, Any]]] = {}
    for item in records: domains.setdefault(item["domain"], []).append(item)
    summary = {"schema_version": "b6a-domain-coverage-summary/v2", "provenance": provenance, "sheet_classification_counts": matrix["sheet_classification_counts"], "field_region_classification_counts": matrix["field_region_classification_counts"], "domains": [{"domain": domain, "source_sheets": sorted({item["source_sheet"] for item in rows}), "total_relevant_fields_or_regions": len(rows), "migration_states": dict(sorted(Counter(item["state_vector"]["migration_status"] for item in rows).items())), "current_canonical_owners": sorted({item["canonical_owner"] for item in rows if item["canonical_owner"]})} for domain, rows in sorted(domains.items())]}
    lineage = _lineage(crosswalk)
    state = {"schema_version": "b6a-migration-state-vector/v1", "provenance": provenance, "records": [{"domain": item["domain"], "source_sheet": item["source_sheet"], "source_field_or_region": item["source_field_or_region"], "state": item["state_vector"]} for item in records]}
    questions = {"schema_version": "b6a-unresolved-business-questions/v2", "provenance": provenance, "questions": [{"question_id": "B6A-DBKTRA-PCT-CT-OCCURRENCES", "source_sheet": "db.ktra", "source_field": "PHIẾU TRÌNH PCT; PHIẾU TRÌNH CT", "unresolved_part": "Occurrence parsing and parent linkage have separate unresolved contracts.", "migration_blocked": True, "recommended_evidence_needed": "Approved multi-occurrence grammar and explicit parent-reference policy."}, {"question_id": "B6A-REFERENCE-MASTERS", "source_sheet": "db.DC; Địa danh; Dịch-Viết tắt; Phạm vi CN", "source_field": "reference/master regions", "unresolved_part": "No approved source-to-owner decision exists for each reference sheet.", "migration_blocked": True, "recommended_evidence_needed": "Per-sheet authoritative-owner decision."}], "resolved_trace_notes": [{"fields": ["outcome_result", "final_evaluation", "compliance_due_on"], "owner": "InspectionOutcome", "evidence": "Model, Batch 4 reconciliation planner/apply, and runtime workflow owner exist; B6A does not reopen their semantics."}], "defects_or_architecture_drift": lineage["findings"], "b6b_candidates": [{"candidate_id": "B6B-INSPECTION-DECISIONS-MINUTES", "known_blockers": ["V1-bound db.ktra writers are BLOCKS_B6B until equivalence is proven or adapted."], "candidate_count_evidence": [item["candidate_count_evidence"] for item in records if "candidate_count_evidence" in item]}]}
    return matrix, summary, questions, lineage, state, crosswalk

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only B6A legacy coverage discovery.")
    parser.add_argument("--snapshot", type=Path, default=ROOT / "artifacts/phase3c/legacy_snapshot_v2.json")
    parser.add_argument("--workbook", type=Path, default=ROOT / "legacy/Danh sách Kiểm tra GPs.xlsb")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/legacy_audit")
    args = parser.parse_args(argv); snapshot_path, workbook_path = args.snapshot.resolve(), args.workbook.resolve()
    if _sha(snapshot_path) != SNAPSHOT_SHA256 or _sha(workbook_path) != WORKBOOK_SHA256: raise ValueError("B6A canonical workbook or Snapshot V2 provenance guard failed")
    reports = build_reports(json.loads(snapshot_path.read_text(encoding="utf-8")), snapshot_sha256=SNAPSHOT_SHA256, workbook_sha256=WORKBOOK_SHA256, snapshot_path=snapshot_path)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in zip(("b6a_legacy_coverage_matrix.json", "b6a_domain_coverage_summary.json", "b6a_unresolved_business_questions.json", "b6a_source_lineage_drift.json", "b6a_migration_state_vector.json", "b6a_v1_v2_repeatable_crosswalk.json"), reports, strict=True):
        (args.output_dir / name).write_bytes((json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    return 0

if __name__ == "__main__": raise SystemExit(main())
