"""Reusable, snapshot-only legacy semantic discovery inventory.

The profiler deliberately describes evidence and current mappings; it does not
perform source-to-target migration or infer missing business semantics.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from backend.app.domain.phase2_import import FIELD_ALIASES, normalize_row, parse_int
from backend.app.domain.inspection_periods import parse_legacy_inspection_periods


SNAPSHOT_SCHEMA_VERSION = "legacy-semantic-inventory/v2"
CANONICAL_WORKBOOK_SHA256 = "c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d"
# The historical plan identifier is retained as provenance.  The committed
# JSON artifact has its own byte identity, which is what the CLI verifies.
CANONICAL_SNAPSHOT_IDENTIFIER_SHA256 = "234498b1f74d811ef0fb6f39a71af42919cdd440cad9e53d82c287d526588666"
# SHA256 of the committed Git blob's LF bytes.  It is deliberately distinct
# from the historical snapshot identifier above and stable across Windows
# checkout CRLF conversion.
CANONICAL_SNAPSHOT_ARTIFACT_SHA256 = "b3bde05963e4e4d14d5b244e7c62b0f810f1cbbe206750574def6a366bdf7296"

# Numeric lookarounds deliberately avoid ``\b``: a date following punctuation
# such as `, 03/02/2026` is still a separate legacy date token.
_DATE = re.compile(r"(?<!\d)\d{1,2}[/-]\d{1,2}[/-]\d{4}(?!\d)")
_PARTIAL_TO_FULL_DATE_RANGE = re.compile(r"\d{1,2}[/-]\d{1,2}\s*[-–]\s*\d{1,2}[/-]\d{1,2}[/-]\d{4}")
_ISO_TIMESTAMP = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}[ T]\d{1,2}:\d{2}")
_SINGLE_DATE = re.compile(r"^(?:\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}-\d{1,2}-\d{1,2})$")
_NUMBER = re.compile(r"^[-+]?\d+(?:[.,]\d+)?$")
_ID_HEADER = re.compile(r"(?:^ID$|\bID\b|MÃ|Mã số|Mã hồ sơ)", re.IGNORECASE)
_REFERENCE_HEADER = re.compile(r"(?:Q\. định|CV |Biên bản|PHIẾU|Mã số|Mã hồ sơ|MÃ)", re.IGNORECASE)
_MULTI_SEPARATOR = re.compile(r"(?:[,;]|\r?\n|\s&\s|\bvà\b)", re.IGNORECASE)
_REPEATED_REFERENCE = re.compile(r"(?:\b(?:ID|CV|QĐ|QD|GCN|ĐĐK|DDK)\b[^;,\n]{0,40}){2,}", re.IGNORECASE)


@dataclass(frozen=True)
class FieldContract:
    alias: str | None = None
    canonical_fact: str | None = None
    canonical_owner: str | None = None
    owner_status: str = "NOT_MAPPED"
    writers: tuple[str, ...] = ()
    readers: tuple[str, ...] = ()
    api: tuple[str, ...] = ()
    frontend: tuple[str, ...] = ()
    compatibility_fields: tuple[str, ...] = ()
    mapping_notes: str | None = None
    domain_slice: str | None = None


# Explicit declarations are intentionally sparse. Every non-declared column is
# reported as not mapped rather than being assigned a guessed business owner.
KTRA_CONTRACTS: dict[str, FieldContract] = {
    "ID": FieldContract("legacy_inspection_id", "case_identity", "Case.legacy_inspection_id", "OWNER_PROVEN", ("phase2_import",), ("CatalogReadService",), mapping_notes="Stable legacy inspection row identity."),
    "LOẠI KT": FieldContract("inspection_gxp_type", "case_gxp_type", "Case.gxp_type", "OWNER_PROVEN", ("phase2_import", "CaseWorkflowService.create_case"), ("CatalogReadService",), frontend=("case workspace",)),
    "ID CƠ SỞ": FieldContract("site_legacy_id_ref", "case_site", "Case.site_id", "OWNER_PROVEN", ("phase2_import",), ("CatalogReadService",), mapping_notes="Foreign ID; exact site mapping is required."),
    "MÃ DC": FieldContract("scope_code", "case_scope_code", "Case.scope_code", "OWNER_COMPATIBILITY_ONLY", ("phase2_import",), ("CatalogReadService",)),
    "PHẠM VI KIỂM TRA": FieldContract("evaluation_scope_raw", "evaluation_scope", "CaseEvaluationScope", "OWNER_COMPATIBILITY_ONLY", ("phase2_import",), ("CatalogReadService",), compatibility_fields=("rendered legacy prose",), mapping_notes="Structured taxonomy migration remains separately audited."),
    "TIÊU CHUẨN ÁP DỤNG": FieldContract("applicable_standard", "case_applicable_standard", "Case.applicable_standard", "OWNER_PROVEN", ("phase2_import",), ("CatalogReadService",)),
    "LOẠI KIỂM TRA": FieldContract("inspection_type", "case_inspection_type", "Case.inspection_type", "OWNER_PROVEN", ("phase2_import",), ("CatalogReadService",)),
    "Ngày nộp": FieldContract("submitted_at", "application_submitted_on", "CaseApplication.submitted_on", "OWNER_PROVEN", ("phase2_import", "CaseWorkflowService.upsert_case_application"), ("CatalogReadService",), api=("PUT /cases/{case_id}/application",), frontend=("case workspace",), mapping_notes="Datetime canonical owner; source morphology is independently audited."),
    "Mã hồ sơ": FieldContract("dossier_code", "dossier_code", "CaseApplication.dossier_code", "OWNER_PROVEN", ("phase2_import", "CaseWorkflowService.upsert_case_application"), ("CatalogReadService",), api=("PUT /cases/{case_id}/application",), frontend=("case workspace",)),
    "Ngày thẩm định": FieldContract("assessed_at", "initial_assessed_on", "CaseAssessment.assessed_on", "OWNER_PROVEN", ("phase2_import", "CaseWorkflowService.upsert_case_assessment"), ("CatalogReadService",)),
    "Người thẩm định": FieldContract("assessor_name", "initial_assessor", "CaseAssessment.assessor_name", "OWNER_COMPATIBILITY_ONLY", ("phase2_import", "CaseWorkflowService.upsert_case_assessment"), ("CatalogReadService",)),
    "Kết quả": FieldContract("assessment_result", "assessment_and_outcome_result", "CaseAssessment.assessment_result + InspectionOutcome.outcome_result", "MULTIPLE_COMPETING_OWNERS", ("phase2_import",), ("CatalogReadService",), compatibility_fields=("InspectionOutcome.outcome_result",), mapping_notes="One legacy scalar currently populates two distinct canonical facts."),
    "Ngày K.tra": FieldContract("inspected_at", "actual_inspection_period", "InspectionPeriodSegment ordered by ordinal", "OWNER_PROVEN", ("phase2_import", "CaseWorkflowService.upsert_inspection_outcome"), ("reconciliation planner", "CatalogReadService compatibility projection"), api=("PUT /cases/{case_id}/outcome",), frontend=("case workspace",), compatibility_fields=("InspectionOutcome.inspected_on/inspected_to_on",), mapping_notes="B. bản is never a timing source."),
    "Q. định": FieldContract("decision_reference", "inspection_decision_reference_and_date", "InspectionPlan decision fields (future)", "COMPOSITE_REQUIRES_SPLIT", ("phase2_import compatibility",), ("CatalogReadService compatibility",), compatibility_fields=("CaseApplication.dossier_reference", "InspectionOutcome.decision_reference"), mapping_notes="Composite currently copied to incompatible compatibility fields."),
    "B. bản": FieldContract("bbkt_reference", "bbkt_reference", "unresolved", "OWNER_MISMATCH", ("phase2_import compatibility", "CaseWorkflowService.upsert_inspection_outcome"), ("CatalogReadService",), compatibility_fields=("InspectionOutcome.bbkt_reference",), mapping_notes="Timestamp-dominant; not an actual inspection-date source."),
    "T.tra viên": FieldContract(None, "inspection_team", "InspectionTeam + InspectionTeamMember", "OWNER_MISSING", readers=("CatalogReadService",), mapping_notes="Display source is observed; structured identity mapping is not proven."),
    "ĐÁNH GIÁ CUỐI": FieldContract(None, "final_evaluation", "future InspectionOutcome.final_evaluation", "OWNER_MISSING", mapping_notes="Distinct from assessment/outcome result."),
    "PHIẾU TRÌNH PCT": FieldContract(None, "approval_submission", "future InspectionApprovalSubmission", "OWNER_MISSING"),
    "PHIẾU TRÌNH CT": FieldContract(None, "approval_submission", "future InspectionApprovalSubmission", "OWNER_MISSING"),
    "HẠN KT TUÂN THỦ": FieldContract(None, "compliance_due_on", "future InspectionOutcome.compliance_due_on", "OWNER_MISSING"),
    "ID CC GPs": FieldContract(None, "certificate_linkage", "Certificate case linkage", "SOURCE_SEMANTICS_UNPROVEN", mapping_notes="Potential foreign/multi-reference source; no declared importer owner."),
    "MỚI NHẤT": FieldContract(None, "legacy_current_marker", "legacy-only diagnostic", "LEGACY_ONLY"),
    "ID MỚI NHẤT": FieldContract(None, "legacy_current_lineage", "legacy-only diagnostic", "LEGACY_ONLY"),
}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def snapshot_artifact_sha256(path: Path) -> str:
    """Hash canonical serialized snapshot bytes, independent of checkout EOLs."""
    return sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _preview(value: str) -> dict[str, str]:
    digest = sha256(value.encode("utf-8")).hexdigest()[:16]
    # Inventory is evidence, not an export of business prose or identities.
    # A stable digest plus shape keeps representative-value evidence useful
    # without persisting source contents.
    shape = re.sub(r"\d", "9", value)
    shape = re.sub(r"[A-Za-zÀ-ỹ]", "a", shape)
    shape = re.sub(r"\s+", " ", shape)
    return {"sha256_prefix": digest, "length": str(len(value)), "shape": shape[:96]}


def _date_morphology(value: str) -> str | None:
    if not value or value in {"???", "-"}:
        return None
    if _ISO_TIMESTAMP.fullmatch(value):
        return "ISO_TIMESTAMP"
    if _PARTIAL_TO_FULL_DATE_RANGE.search(value):
        return "DATE_RANGE"
    dates = _DATE.findall(value)
    if _SINGLE_DATE.fullmatch(value):
        return "SINGLE_DATE"
    if len(dates) >= 2:
        return "MULTI_DATE_OR_PERIOD" if _MULTI_SEPARATOR.search(value) else "DATE_RANGE"
    if len(dates) == 1:
        return "ANNOTATED_DATE"
    if re.search(r"\d{1,2}[/-]\d{1,2}(?:[/-]\d{0,3})?$", value):
        return "PARTIAL_DATE"
    return None


def classify_morphology(value: str) -> str:
    if not value:
        return "EMPTY"
    if value == "???":
        return "SENTINEL_PENDING_INPUT"
    if value == "-":
        return "SENTINEL_NOT_APPLICABLE"
    date_kind = _date_morphology(value)
    if date_kind:
        return date_kind
    if _NUMBER.fullmatch(value):
        return "NUMERIC"
    if _MULTI_SEPARATOR.search(value):
        return "LEXICAL_SEPARATOR_PRESENT"
    if "\n" in value or "\r" in value:
        return "MULTILINE_TEXT"
    return "TEXT"


def _aliases_by_header() -> dict[str, str]:
    resolved: dict[str, str] = {}
    for alias, headers in FIELD_ALIASES.items():
        for header in headers:
            resolved.setdefault(header, alias)
    return resolved


def validate_readonly_rehearsal_target(*, dialect: str, database_name: str, transaction_read_only: bool) -> None:
    """Reject every database target except an explicitly read-only rehearsal PG session.

    The snapshot profiler does not open a database connection today.  Keeping
    the guard here makes a future optional comparison path testable without
    making an implicit connection part of discovery.
    """
    if dialect != "postgresql":
        raise RuntimeError("legacy semantic comparison requires PostgreSQL")
    if database_name != "gxp_legacy_rehearsal":
        raise RuntimeError("legacy semantic comparison requires gxp_legacy_rehearsal")
    if not transaction_read_only:
        raise RuntimeError("legacy semantic comparison requires a read-only transaction")


def _semantic_cardinality(
    header: str,
    lexical: Counter[str],
    values: list[str],
    *,
    semantic_profile: dict[str, Any] | None,
) -> str:
    """Classify business cardinality without promoting punctuation to proof."""
    if semantic_profile and semantic_profile["segment_count_distribution"].get("2_or_more", 0):
        return "0..N_PROVEN"
    if semantic_profile:
        return "0..1_OBSERVED"
    if any(_has_repeated_reference(value) for value in values):
        return "0..N_SUSPECTED"
    # Date tokens, commas and prose separators are lexical signals only and
    # do not establish a business list for unmapped/free-text fields.
    return "0..1_OBSERVED" if header == "ID" else "UNKNOWN"


def _has_repeated_reference(value: str) -> bool:
    return len(re.findall(r"\b(?:ID|CV|QĐ|QD|GCN|ĐĐK|DDK)\b", value, flags=re.IGNORECASE)) >= 2


def _domain_assignment(header: str) -> dict[str, str]:
    groups = {
        "A": {"ID", "ID CƠ SỞ", "MỚI NHẤT", "ID MỚI NHẤT", "ID CƠ SỞ 2", "MÃ DC 2"},
        "B": {"Ngày nộp", "Mã hồ sơ", "Ngày thẩm định", "Người thẩm định"},
        "C": {"Kết quả", "ĐÁNH GIÁ CUỐI", "Đ. giá"},
        "D": {"Q. định", "T.tra viên"},
        "E": {"Ngày K.tra", "B. bản", "Kiểm tra", "Báo cáo"},
        "F": {"CV BCKP lần 1", "CV BCKP lần 2", "Ngày T. định", "Người TĐ", "Ngày g.sát", "Người g.sát", "PHIẾU TRÌNH PCT", "PHIẾU TRÌNH CT", "HẠN KT TUÂN THỦ", "Khắc phục 1", "Khắc phục 2", "Khắc phục cuối"},
        "G": {"ID CC GPs", "Mã số CC", "ID DDK", "Mã số ĐĐK", "Idx CC", "Idx CC cũ", "Hạn CC cũ", "Ngày cấp ĐĐK", "Cấp CC", "Cấp ĐĐK"},
        "H": {"LOẠI KT", "MÃ DC", "PHẠM VI KIỂM TRA", "TIÊU CHUẨN ÁP DỤNG", "LOẠI KIỂM TRA", "VIẾT RÚT GỌN PHẠM VI"},
    }
    for key, headers in groups.items():
        if header in headers:
            return {"slice": key, "reason": "declared domain-cluster coverage"}
    if header in {"Kiểm tra chậm", "Thẩm định HSĐK", "Chờ kiểm tra", "Hoàn thành báo cáo", "Nộp BCKP", "Đánh giá BCKP 1", "Đánh giá BCKP 2", "Trình lãnh đạo Cục"}:
        return {"slice": "DERIVED_DIAGNOSTIC", "reason": "legacy workflow marker requires separate provenance audit"}
    return {"slice": "UNASSIGNED", "reason": "no safe domain contract is declared; retained for low-priority discovery"}


def _mapping_evidence(contract: FieldContract, header: str, aliases: Mapping[str, str]) -> tuple[list[dict[str, str]], str, list[dict[str, str]]]:
    """Use deterministic source text checks to distinguish declaration from proof."""
    if contract.alias is None:
        return [], "NOT_APPLICABLE_NO_DECLARED_MAPPING", []
    importer_path = Path("backend/app/domain/phase2_import.py")
    source = importer_path.read_text(encoding="utf-8")
    evidence: list[dict[str, str]] = []
    drift: list[dict[str, str]] = []
    direct_identity = header == "ID" and contract.alias == "legacy_inspection_id"
    if not direct_identity and aliases.get(header) != contract.alias:
        drift.append({"kind": "FIELD_ALIAS_MISMATCH", "legacy_header": header, "declared_alias": contract.alias})
    alias_seen = f'row.get("{header}"' in source if direct_identity else f'"{contract.alias}"' in source
    target_tokens = re.findall(r"\.(\w+)", contract.canonical_owner or "")
    target_seen = not target_tokens or any(token in source for token in target_tokens)
    if alias_seen:
        evidence.append({"path": str(importer_path).replace("\\", "/"), "symbol": "import_snapshot", "operation": "WRITE", "target": contract.canonical_owner or "declared canonical fact", "evidence_type": "SOURCE_ALIAS_AND_IMPORTER_SCAN"})
    if not alias_seen:
        drift.append({"kind": "DECLARED_WRITER_NOT_FOUND", "legacy_header": header, "declared_writer": "phase2_import"})
    if not target_seen:
        drift.append({"kind": "DECLARED_CANONICAL_TARGET_NOT_FOUND", "legacy_header": header, "target": contract.canonical_owner or ""})
    return evidence, ("CODE_EVIDENCE_VERIFIED" if alias_seen and target_seen and not drift else "OWNER_DECLARED_BUT_UNVERIFIED"), drift


def _fallback_findings() -> list[dict[str, str]]:
    """Report legacy-source coalescing patterns without interpreting them."""
    path = Path("backend/app/domain/phase2_import.py")
    source = path.read_text(encoding="utf-8")
    findings: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    pattern = re.compile(r'parse_date\(row\.get\("(?P<left>[^"]+)"[^\n]*?\)\s+or\s+row\.get\("(?P<right>[^"]+)"', re.MULTILINE)
    for match in pattern.finditer(source):
        pair = (match["left"], match["right"])
        if pair in seen:
            continue
        seen.add(pair)
        findings.append({"path": str(path).replace("\\", "/"), "symbol": "import_snapshot", "source_aliases": f"{match['left']} -> {match['right']}", "canonical_target": "date-valued import target", "risk_reason": "SOURCE_FALLBACK_OR_COALESCING_REQUIRES_SEMANTIC_REVIEW"})
    return findings


def run_readonly_rehearsal_comparison(database_url: str, valid_legacy_ids: set[int]) -> dict[str, Any]:
    """Read broad owner-population metrics in an explicitly read-only session."""
    from sqlalchemy import text

    from backend.app.db.session import build_engine

    parsed = urlsplit(database_url)
    dialect = parsed.scheme.split("+", 1)[0]
    database_name = parsed.path.rsplit("/", 1)[-1]
    if dialect != "postgresql" or database_name != "gxp_legacy_rehearsal":
        validate_readonly_rehearsal_target(dialect=dialect, database_name=database_name, transaction_read_only=False)
    engine = build_engine(database_url)
    connection = engine.connect()
    transaction = connection.begin()
    try:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        actual_database = str(connection.execute(text("SELECT current_database()")).scalar_one())
        read_only = str(connection.execute(text("SHOW transaction_read_only")).scalar_one()).strip().lower() in {"on", "true", "1"}
        validate_readonly_rehearsal_target(dialect=dialect, database_name=actual_database, transaction_read_only=read_only)
        rows = connection.execute(text("""
            SELECT c.legacy_inspection_id,
                   ca.id IS NOT NULL AS application_populated,
                   io.id IS NOT NULL AS outcome_populated,
                   io.inspection_period_state IS NOT NULL AS period_state_populated,
                   EXISTS (SELECT 1 FROM inspection_period_segment ips WHERE ips.inspection_outcome_id = io.id) AS period_segments_populated
            FROM "case" c
            LEFT JOIN case_application ca ON ca.case_id = c.id
            LEFT JOIN inspection_outcome io ON io.case_id = c.id
            WHERE c.legacy_inspection_id IS NOT NULL
        """)).mappings().all()
        matched = [row for row in rows if int(row["legacy_inspection_id"]) in valid_legacy_ids]
        matched_ids = {int(row["legacy_inspection_id"]) for row in matched}
        return {
            "status": "COMPLETED_READ_ONLY",
            "database": actual_database,
            "transaction_read_only": True,
            "valid_legacy_rows": len(valid_legacy_ids),
            "case_identity_matched": len(matched_ids),
            "case_identity_unmatched": len(valid_legacy_ids - matched_ids),
            "case_identity_ambiguous": 0,
            "declared_owner_population": {
                "application_populated": sum(bool(row["application_populated"]) for row in matched),
                "outcome_populated": sum(bool(row["outcome_populated"]) for row in matched),
                "inspection_period_state_populated": sum(bool(row["period_state_populated"]) for row in matched),
                "inspection_period_segments_populated": sum(bool(row["period_segments_populated"]) for row in matched),
            },
            "comparison_limits": ["COMPARISON_NOT_SAFE_FOR_UNPROVEN_FIELD_SEMANTICS", "No source-to-target migration eligibility is derived."],
        }
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()


def _field_categories(header: str, morphology: Counter[str], distinct_count: int) -> list[str]:
    categories: set[str] = set()
    observed = set(morphology) - {"EMPTY", "SENTINEL_PENDING_INPUT", "SENTINEL_NOT_APPLICABLE"}
    if header == "ID":
        categories.add("IDENTITY")
    if _ID_HEADER.search(header):
        categories.add("FOREIGN_ID" if header != "ID" else "IDENTITY")
    if _REFERENCE_HEADER.search(header):
        categories.add("REFERENCE")
    if "NUMERIC" in observed and observed == {"NUMERIC"}:
        categories.add("NUMERIC")
    if "ISO_TIMESTAMP" in observed or "SINGLE_DATE" in observed:
        categories.add("SINGLE_DATE")
    if {"DATE_RANGE", "MULTI_DATE_OR_PERIOD", "PARTIAL_DATE", "ANNOTATED_DATE"} & observed:
        categories.add("DATE_OR_DATE_RANGE")
    if "MULTI_DATE_OR_PERIOD" in observed:
        categories.add("MULTI_DATE_OR_PERIOD")
    if {"LEXICAL_SEPARATOR_PRESENT", "MULTILINE_TEXT"} & observed:
        categories.add("LEXICAL_MULTI_TOKEN_EVIDENCE")
    if any(kind.startswith("SENTINEL") for kind in morphology):
        categories.add("SENTINEL_DOMINATED" if sum(morphology[k] for k in morphology if k.startswith("SENTINEL")) > sum(morphology.values()) / 2 else "SCALAR_TEXT")
    if not categories:
        categories.add("SCALAR_ENUM_LIKE" if 1 < distinct_count <= 16 else "FREE_TEXT")
    return sorted(categories)


def _relationship_inventory(rows: list[dict[str, Any]], headers: list[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    normalized = [{header: _text(row.get(header)) for header in headers} for row in rows]
    for index, left in enumerate(headers):
        for right in headers[index + 1 :]:
            paired = [(row[left], row[right]) for row in normalized if row[left] and row[right]]
            if len(paired) < 10:
                continue
            equal = sum(a == b for a, b in paired)
            if equal / len(paired) >= 0.98:
                findings.append({"kind": "IDENTICAL_NONEMPTY_VALUES", "left": left, "right": right, "paired_rows": len(paired), "equal_rows": equal})
                continue
            embedded = sum(a in b or b in a for a, b in paired if min(len(a), len(b)) >= 4)
            if embedded / len(paired) >= 0.9:
                findings.append({"kind": "EMBEDDED_VALUE_RELATIONSHIP", "left": left, "right": right, "paired_rows": len(paired), "embedded_rows": embedded})
    return findings


def _risk(contract: FieldContract, semantic_cardinality: str, morphology: Counter[str], header: str) -> str:
    if contract.owner_status in {"OWNER_MISMATCH", "MULTIPLE_COMPETING_OWNERS"}:
        return "CRITICAL"
    if contract.owner_status in {"OWNER_MISSING", "COMPOSITE_REQUIRES_SPLIT", "SOURCE_SEMANTICS_UNPROVEN"}:
        return "HIGH"
    if semantic_cardinality == "0..N_PROVEN":
        return "HIGH" if contract.canonical_owner and "Segment" not in contract.canonical_owner else "MEDIUM"
    if any(kind.startswith("SENTINEL") for kind in morphology):
        return "MEDIUM"
    return "LOW" if contract.owner_status == "OWNER_PROVEN" else "INFORMATIONAL"


def _question(header: str, profile: dict[str, Any], contract: FieldContract) -> dict[str, Any] | None:
    if contract.owner_status not in {"OWNER_MISSING", "OWNER_MISMATCH", "COMPOSITE_REQUIRES_SPLIT", "MULTIPLE_COMPETING_OWNERS", "SOURCE_SEMANTICS_UNPROVEN"}:
        return None
    priority = "BLOCKING" if contract.owner_status in {"OWNER_MISMATCH", "COMPOSITE_REQUIRES_SPLIT", "MULTIPLE_COMPETING_OWNERS"} else "HIGH"
    question = {
        "B. bản": "Trường B. bản biểu thị chính xác loại bằng chứng nào: biên bản, thời điểm, hay tham chiếu tài liệu? Nó không được dùng làm ngày kiểm tra.",
        "Q. định": "Có thể xác nhận quy tắc tách số quyết định và ngày quyết định từ Q. định, kể cả trường hợp không tách được tự động không?",
        "Kết quả": "Kết quả là kết quả thẩm định hồ sơ, kết quả kiểm tra thực tế, hay hai giá trị khác nhau đang bị gộp chung?",
        "T.tra viên": "T.tra viên có phải danh sách đoàn kiểm tra có thứ tự/vai trò không, và nguồn định danh cá nhân nào là authoritative?",
        "ĐÁNH GIÁ CUỐI": "ĐÁNH GIÁ CUỐI khác gì Kết quả và có phải một trạng thái cuối độc lập không?",
        "PHIẾU TRÌNH PCT": "PHIẾU TRÌNH PCT thuộc một bước phê duyệt có thể lặp lại hay chỉ một hồ sơ duy nhất cho mỗi đợt kiểm tra?",
        "PHIẾU TRÌNH CT": "PHIẾU TRÌNH CT thuộc một bước phê duyệt có thể lặp lại hay chỉ một hồ sơ duy nhất cho mỗi đợt kiểm tra?",
        "HẠN KT TUÂN THỦ": "HẠN KT TUÂN THỦ là hạn khắc phục, hạn tái kiểm tra hay hạn tuân thủ sau cấp chứng nhận?",
        "ID CC GPs": "ID CC GPs có thể chứa nhiều chứng nhận hay chỉ một ID; quan hệ với certificate hiện hành là gì?",
    }.get(header, f"Trường {header} có nghĩa nghiệp vụ nào và canonical owner nào được phép ghi nó?")
    return {
        "priority": priority,
        "legacy_field": header,
        "affected_rows": profile["non_empty_count"],
        "decision_blocked": contract.canonical_fact or "canonical owner selection",
        "question_vi": question,
    }


def build_inventory(
    snapshot: dict[str, Any],
    *,
    sheet_name: str = "db.ktra",
    contracts: Mapping[str, FieldContract] | None = None,
    rehearsal_comparison: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Profile a source sheet using generic mechanics and supplied contracts.

    ``contracts`` is intentionally injected so another legacy sheet can reuse
    the profiler without inheriting db.ktra business semantics.
    """
    rows = snapshot.get("sheets", snapshot).get(sheet_name)
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"snapshot does not contain non-empty {sheet_name}")
    headers = [key for key in rows[0] if not key.startswith("__")]
    if any(set(row) - set(headers) - {"__excel_row_number"} for row in rows):
        raise ValueError("snapshot has inconsistent physical field names")
    aliases = _aliases_by_header()
    contracts = KTRA_CONTRACTS if contracts is None and sheet_name == "db.ktra" else (contracts or {})
    valid_rows = [row for row in rows if parse_int(normalize_row(row).get("ID", "")) is not None]
    fields: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    for position, header in enumerate(headers, start=1):
        values = [_text(row.get(header)) for row in rows]
        valid_values = [_text(row.get(header)) for row in valid_rows]
        nonempty = [value for value in values if value]
        morphology = Counter(classify_morphology(value) for value in values)
        distinct = sorted(set(nonempty))
        contract = contracts.get(header, FieldContract(alias=aliases.get(header)))
        categories = _field_categories(header, morphology, len(distinct))
        composite = any(category in {"DATE_OR_DATE_RANGE", "MULTI_DATE_OR_PERIOD", "LEXICAL_MULTI_TOKEN_EVIDENCE"} for category in categories) or contract.owner_status == "COMPOSITE_REQUIRES_SPLIT"
        lexical_profile = {
            "physical_column_index": position,
            "total_rows": len(rows),
            "valid_id_rows": len(valid_rows),
            "non_empty_count": len(nonempty),
            "blank_count": len(values) - len(nonempty),
            "question_mark_count": sum(value == "???" for value in values),
            "dash_count": sum(value == "-" for value in values),
            "distinct_nonempty_count": len(distinct),
            "morphology": dict(sorted(morphology.items())),
            "representative_values": [_preview(value) for value in distinct[:3]],
            "newline_or_multiline_count": sum("\n" in value or "\r" in value for value in values),
            "lexical_separator_present_count": sum(bool(_MULTI_SEPARATOR.search(value)) for value in values),
            "repeated_reference_pattern_count": sum(_has_repeated_reference(value) for value in values),
        }
        semantic_profile: dict[str, Any] | None = None
        if sheet_name == "db.ktra" and header == "Ngày K.tra":
            # This is source-derived parser evidence, not a hard-coded state
            # count.  It preserves the existing period contract as a reusable
            # reference example for future discovery slices.  States are
            # business facts, so excluded physical rows without a legacy ID
            # cannot inflate the source-state profile.
            parsed = [parse_legacy_inspection_periods(value) for value in valid_values]
            segment_lengths = Counter(len(result.segments) for result in parsed)
            semantic_profile = {
                "authority": "backend.app.domain.inspection_periods.parse_legacy_inspection_periods",
                "source_state_counts": dict(sorted(Counter(result.state.value for result in parsed).items())),
                "segment_count_distribution": {
                    "0": segment_lengths[0], "1": segment_lengths[1], "2_or_more": sum(count for length, count in segment_lengths.items() if length >= 2),
                },
                "semantic_shape_distribution": dict(sorted(Counter(
                    "MULTI_SEGMENT" if len(result.segments) >= 2 else "SINGLE_SEGMENT" if result.segments else "NO_SEGMENT"
                    for result in parsed
                ).items())),
            }
        code_evidence, evidence_status, drift = _mapping_evidence(contract, header, aliases)
        semantic_cardinality = _semantic_cardinality(header, morphology, valid_values, semantic_profile=semantic_profile)
        field = {
            "legacy_header": header,
            "normalized_alias": contract.alias or aliases.get(header),
            "source_lexical_profile": lexical_profile,
            "semantic_profile": semantic_profile or {"authority": "UNPROVEN_NO_AUTHORITATIVE_PARSER"},
            "observed_shapes": categories,
            "data_type_candidates": sorted({kind for kind in morphology if kind not in {"EMPTY", "SENTINEL_PENDING_INPUT", "SENTINEL_NOT_APPLICABLE"}}),
            "sentinels": {"pending_input": lexical_profile["question_mark_count"], "not_applicable": lexical_profile["dash_count"], "missing": lexical_profile["blank_count"]},
            "semantic_cardinality": semantic_cardinality,
            "composite_value_evidence": composite,
            "id_or_reference_evidence": bool(_ID_HEADER.search(header) or _REFERENCE_HEADER.search(header)),
            "derived_or_calculated_evidence": header in {"MỚI NHẤT", "ID MỚI NHẤT", "Kiểm tra chậm"},
            "canonical_fact": contract.canonical_fact,
            "canonical_owner": contract.canonical_owner,
            "writers": list(contract.writers),
            "readers": list(contract.readers),
            "api": list(contract.api),
            "frontend": list(contract.frontend),
            "compatibility_fields": list(contract.compatibility_fields),
            "declared_business_contract": {"declared_owner_status": contract.owner_status, "canonical_fact": contract.canonical_fact, "canonical_owner": contract.canonical_owner, "notes": contract.mapping_notes},
            "code_mapping_evidence": code_evidence,
            "evidence_status": evidence_status,
            "contract_drift": drift,
            "owner_status": contract.owner_status if evidence_status == "CODE_EVIDENCE_VERIFIED" or contract.owner_status not in {"OWNER_PROVEN", "OWNER_COMPATIBILITY_ONLY"} else "OWNER_DECLARED_BUT_UNVERIFIED",
            "domain_assignment": _domain_assignment(header),
            "migration_status": "DISCOVERY_ONLY_NO_MIGRATION",
            "risk": _risk(contract, semantic_cardinality, morphology, header),
            "unresolved_business_questions": [],
        }
        question = _question(header, lexical_profile, contract)
        if question:
            question["domain_slice"] = field["domain_assignment"]["slice"]
            question["evidence_summary"] = f"declared owner status={contract.owner_status}; lexical non-empty rows={lexical_profile['non_empty_count']}"
            field["unresolved_business_questions"].append(question["question_vi"])
            questions.append(question)
        fields.append(field)
    relationships = _relationship_inventory(rows, headers)
    relationship_by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relationship in relationships:
        relationship_by_field[relationship["left"]].append(relationship)
        relationship_by_field[relationship["right"]].append(relationship)
    for field in fields:
        field["relationships"] = relationship_by_field[field["legacy_header"]]
    status_counts = Counter(field["owner_status"] for field in fields)
    risk_counts = Counter(field["risk"] for field in fields)
    evidence_counts = Counter(field["evidence_status"] for field in fields)
    cardinality_counts = Counter(field["semantic_cardinality"] for field in fields)
    drift_findings = [finding for field in fields for finding in field["contract_drift"]]
    domain_slices = [
        {"key": "A", "name": "Identity / case linkage", "headers": ["ID", "ID CƠ SỞ", "MỚI NHẤT", "ID MỚI NHẤT"], "priority": 1},
        {"key": "B", "name": "Application / dossier", "headers": ["Ngày nộp", "Mã hồ sơ", "Ngày thẩm định", "Người thẩm định"], "priority": 2},
        {"key": "C", "name": "Assessment / inspection outcome separation", "headers": ["Kết quả", "ĐÁNH GIÁ CUỐI"], "priority": 3},
        {"key": "D", "name": "Inspection planning / decision", "headers": ["Q. định"], "priority": 4},
        {"key": "E", "name": "Inspection execution", "headers": ["Ngày K.tra", "B. bản", "T.tra viên"], "priority": 5},
        {"key": "F", "name": "CAPA / approval follow-up", "headers": ["CV BCKP lần 1", "CV BCKP lần 2", "PHIẾU TRÌNH PCT", "PHIẾU TRÌNH CT", "HẠN KT TUÂN THỦ"], "priority": 6},
        {"key": "G", "name": "Certificate linkage", "headers": ["ID CC GPs", "Mã số CC", "ID DDK", "Mã số ĐĐK"], "priority": 7},
        {"key": "H", "name": "Evaluation scope / standards", "headers": ["PHẠM VI KIỂM TRA", "TIÊU CHUẨN ÁP DỤNG", "LOẠI KIỂM TRA"], "priority": 8},
    ]
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "provenance": {
            "source_sheet": sheet_name,
            "canonical_workbook_sha256": CANONICAL_WORKBOOK_SHA256,
            "declared_canonical_snapshot_sha256": CANONICAL_SNAPSHOT_IDENTIFIER_SHA256,
            "snapshot_artifact_sha256": CANONICAL_SNAPSHOT_ARTIFACT_SHA256,
            "extraction_owner": "backend.app.domain.legacy_snapshot.read_core_sheet_rows",
            "database_comparison": rehearsal_comparison or {"status": "BLOCKED_NO_EXPLICIT_DATABASE_URL_ENV"},
        },
        "coverage": {"physical_row_count": len(rows), "valid_id_row_count": len(valid_rows), "physical_field_count": len(headers)},
        "fields": fields,
        "relationships": relationships,
        "owner_status_distribution": dict(sorted(status_counts.items())),
        "mapping_evidence_distribution": dict(sorted(evidence_counts.items())),
        "semantic_cardinality_distribution": dict(sorted(cardinality_counts.items())),
        "risk_distribution": dict(sorted(risk_counts.items())),
        "contract_drift_findings": drift_findings,
        "fallback_coalescing_findings": _fallback_findings(),
        "domain_slices": domain_slices,
        "unresolved_business_questions": sorted(questions, key=lambda item: (item["priority"] != "BLOCKING", item["legacy_field"])),
        "global_findings": [
            "Discovery evidence only: no source field is migrated or reinterpreted by this inventory.",
            "db.ktra Ngày K.tra is owned by ordered InspectionPeriodSegment; B. bản is not a timing source.",
            "Rehearsal comparison is intentionally absent without an explicit read-only PostgreSQL target.",
        ],
    }


def render_report(inventory: dict[str, Any]) -> str:
    coverage = inventory["coverage"]
    risks = inventory["risk_distribution"]
    owners = inventory["owner_status_distribution"]
    fields = inventory["fields"]
    mapped = sum(field["owner_status"] != "NOT_MAPPED" for field in fields)
    multi = [field for field in fields if field["semantic_cardinality"] == "0..N_PROVEN"]
    composite = [field for field in fields if field["composite_value_evidence"]]
    relationships = inventory["relationships"]
    period = next((field for field in fields if field["legacy_header"] == "Ngày K.tra"), None)
    lines = [
        "# db.ktra Semantic Discovery",
        "",
        "## Coverage",
        f"- Physical fields: `{coverage['physical_field_count']}`",
        f"- Physical rows: `{coverage['physical_row_count']}`; valid-ID rows: `{coverage['valid_id_row_count']}`",
        f"- Rehearsal comparison: `{inventory['provenance']['database_comparison']['status']}`",
        f"- Mapped/declared fields: `{mapped}`; not mapped: `{len(fields) - mapped}`",
        f"- Semantic `0..N` proven fields: `{len(multi)}`; composite-evidence fields: `{len(composite)}`",
        "",
        "## Risk Summary",
        *[f"- `{risk}`: `{count}`" for risk, count in sorted(risks.items())],
        "",
        "## Owner Summary",
        *[f"- `{status}`: `{count}`" for status, count in sorted(owners.items())],
        "",
        "## Mapping Evidence",
        *[f"- `{status}`: `{count}`" for status, count in sorted(inventory["mapping_evidence_distribution"].items())],
        f"- Contract drift findings: `{len(inventory['contract_drift_findings'])}`; fallback/coalescing findings: `{len(inventory['fallback_coalescing_findings'])}`.",
        f"- Semantic cardinality: `{json.dumps(inventory['semantic_cardinality_distribution'], sort_keys=True)}`.",
        "",
        "## Highest-Risk Facts",
    ]
    for field in [field for field in inventory["fields"] if field["risk"] in {"CRITICAL", "HIGH"}]:
        lines.append(f"- `{field['legacy_header']}`: `{field['owner_status']}`; {field['declared_business_contract']['notes'] or 'owner/semantic contract requires review.'}")
    lines.extend(["", "## Cross-Field Coupling Signals"])
    lines.append(f"- Automatic correlation findings: `{len(relationships)}`. These are discovery signals, not ownership proof.")
    for relationship in relationships[:8]:
        lines.append(f"- `{relationship['kind']}`: `{relationship['left']}` <-> `{relationship['right']}` (`{relationship['paired_rows']}` paired rows)")
    if period:
        lines.extend(["", "## Inspection-Period Reference Contract"])
        lines.append("- `Ngày K.tra` is the source for ordered `InspectionPeriodSegment`; `B. bản` remains a non-timing reference with `OWNER_MISMATCH`.")
        lines.append(f"- Lexical morphology: `{json.dumps(period['source_lexical_profile']['morphology'], ensure_ascii=False, sort_keys=True)}`")
        lines.append(f"- Authoritative parser facts: `{json.dumps(period['semantic_profile'], ensure_ascii=False, sort_keys=True)}`")
    lines.extend(["", "## Domain Coverage"])
    domain_counts = Counter(field["domain_assignment"]["slice"] for field in fields)
    lines.extend(f"- `{slice_key}`: `{count}` physical headers" for slice_key, count in sorted(domain_counts.items()))
    lines.extend(["", "## Recommended Domain Order"])
    lines.extend(f"{item['priority']}. `{item['key']}` - {item['name']}" for item in inventory["domain_slices"])
    lines.extend(["", "## Unresolved Questions"])
    lines.extend(f"- `{item['legacy_field']}` ({item['priority']}, {item['affected_rows']} rows): {item['question_vi']}" for item in inventory["unresolved_business_questions"])
    lines.extend(["", "The full machine-readable inventory is `artifacts/legacy_audit/db_ktra_semantic_inventory.json`.", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--questions-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    parser.add_argument("--expected-snapshot-sha256", default=CANONICAL_SNAPSHOT_ARTIFACT_SHA256)
    parser.add_argument("--compare-rehearsal", action="store_true")
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    args = parser.parse_args(argv)
    actual_sha = snapshot_artifact_sha256(args.snapshot)
    if actual_sha != args.expected_snapshot_sha256:
        raise RuntimeError("snapshot SHA256 does not match the required provenance value")
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    rehearsal_comparison: dict[str, Any] | None = None
    if args.compare_rehearsal:
        database_url = os.environ.get(args.database_url_env, "").strip()
        if not database_url:
            raise RuntimeError(f"--compare-rehearsal requires non-empty environment variable {args.database_url_env}")
        rows = snapshot.get("sheets", snapshot).get("db.ktra", [])
        valid_ids = {parse_int(normalize_row(row).get("ID", "")) for row in rows}
        rehearsal_comparison = run_readonly_rehearsal_comparison(database_url, {item for item in valid_ids if item is not None})
    inventory = build_inventory(snapshot, rehearsal_comparison=rehearsal_comparison)
    for path, payload in ((args.output, inventory), (args.questions_output, inventory["unresolved_business_questions"])):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(render_report(inventory), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
