"""Coherent read-only QĐKT dossier bookmark and date-source evidence gate.

This module connects source-pinned template observations, the legacy Rg3
assignment chain and the canonical Case/Application/Site crosswalk.  It never
renders, mutates a template, reads storage or authorizes document creation.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Sequence

from backend.app.document.inspection_qd_kt_cross_system_identity_evidence import (
    QdKtRg3CrosswalkResult,
)
from backend.app.document.inspection_qd_kt_dossier_legacy_pair import (
    QdKtDossierLegacyPair,
    inspect_qdkt_dossier_legacy_pair,
)
from backend.app.document.inspection_qd_kt_dotx_binary_audit import (
    QdKtDotxBinaryAudit,
    classify_qdkt_target_bookmark,
)
from backend.app.document.inspection_qd_kt_template_asset_contract import (
    load_inspection_qd_kt_template_assets,
)


_ROOT = Path(__file__).resolve().parents[3]
_SOURCE = (
    _ROOT
    / "artifacts/legacy_audit/inspection_qd_kt_dossier_bookmark_source_evidence.json"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GXP_TYPES = frozenset({"GMP", "GLP", "GMPbb", "GSP"})
_TARGETS = ("HsDK", "NgaynopHsDK")


@dataclass(frozen=True)
class QdKtDossierTemplateSourceEvidence:
    gxp_type: str
    filename: str
    sha256: str
    byte_size: int
    scanned_word_parts: tuple[str, ...]
    bookmark_count: int
    nested_pair_count: int
    overlapping_pair_count: int
    dossier_plain_text_paragraph_count: int


@dataclass(frozen=True)
class QdKtDossierBookmarkSourceEvidence:
    workbook_sha256: str
    workbook_sheet: str
    workbook_named_range: str
    workbook_named_range_address: str
    vba_archive_sha256: str
    registration_group_label: str
    submission_column: int
    submission_header: str
    submission_named_ranges: tuple[str, ...]
    dossier_column: int
    dossier_header: str
    date_semantics: str
    receipt_date_equivalence: bool
    date_display_transform: str
    canonical_date_timezone_rule: str
    template_findings: tuple[QdKtDossierTemplateSourceEvidence, ...]
    contains_raw_business_values: bool = False
    ready_to_render: bool = False


@dataclass(frozen=True)
class QdKtDossierFieldEvidence:
    bookmark_name: str
    physical_bookmark_status: str
    runtime_source: str
    business_semantics: str
    business_semantics_confidence: str
    canonical_owner: str
    canonical_mapping_confidence: str
    date_normalization_rule: str | None = None


@dataclass(frozen=True)
class QdKtDossierBookmarkEvidenceResult:
    status: str
    fields: tuple[QdKtDossierFieldEvidence, ...] = ()
    template_identity_verified: bool = False
    legacy_assignment_chain_verified: bool = False
    canonical_case_application_site_verified: bool = False
    ready_to_render: bool = False


def _require(condition: bool, status: str) -> None:
    if not condition:
        raise ValueError(status)


def load_qdkt_dossier_bookmark_source_evidence(
    path: Path = _SOURCE,
) -> QdKtDossierBookmarkSourceEvidence:
    """Load privacy-safe primary-source observations and reject contract drift."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("QDKT_DOSSIER_BOOKMARK_SOURCE_EVIDENCE_UNAVAILABLE") from exc
    _require(isinstance(payload, dict), "QDKT_DOSSIER_BOOKMARK_SOURCE_EVIDENCE_INVALID")
    _require(
        payload.get("schema_version")
        == "inspection-qd-kt-dossier-bookmark-source-evidence/v1",
        "QDKT_DOSSIER_BOOKMARK_SOURCE_SCHEMA_DRIFT",
    )
    _require(
        payload.get("evidence_origin") == "PRIMARY_LEGACY_BINARY_AND_VBA_AUDIT",
        "QDKT_DOSSIER_BOOKMARK_SOURCE_ORIGIN_UNVERIFIED",
    )
    _require(payload.get("contains_raw_business_values") is False, "QDKT_DOSSIER_RAW_VALUES_FORBIDDEN")
    _require(payload.get("ready_to_render") is False, "QDKT_DOSSIER_RENDER_PROMOTION_FORBIDDEN")

    sources = payload["sources"]
    workbook = sources["workbook"]
    vba = sources["vba_archive"]
    columns = payload["workbook_column_contract"]
    runtime = payload["runtime_assignment_contract"]
    date_semantics = payload["date_semantics"]
    dossier_semantics = payload["dossier_code_semantics"]
    _require(_SHA256.fullmatch(workbook["sha256"]) is not None, "QDKT_DOSSIER_WORKBOOK_SHA_INVALID")
    _require(_SHA256.fullmatch(vba["sha256"]) is not None, "QDKT_DOSSIER_VBA_SHA_INVALID")
    _require(
        workbook["sheet"] == "db.ktra"
        and workbook["named_range"] == "db_ktra"
        and workbook["named_range_address"] == "$A$5:$CV$1549",
        "QDKT_DOSSIER_WORKBOOK_COORDINATE_DRIFT",
    )
    _require(
        columns == {
            "group_header_row": 3,
            "group_start_column": 8,
            "group_label": "ĐĂNG KÝ",
            "field_header_row": 4,
            "submission_column": 8,
            "submission_header": "Ngày nộp",
            "submission_named_ranges": ["db_NgayDky_ktra", "Ngay_nop_HS"],
            "dossier_code_column": 9,
            "dossier_code_header": "Mã hồ sơ",
        },
        "QDKT_DOSSIER_WORKBOOK_HEADER_DRIFT",
    )
    _require(
        runtime["module"] == "RecordForm.frm"
        and runtime["selected_row_assignment_line"] == 334
        and runtime["value_assignment_line"] == 343
        and runtime["dossier_code_expression"]
        == "Rg3.Cells(1, ColDB_HSDK_Ktra + 1).Value"
        and runtime["submission_date_expression"]
        == "Rg3.Cells(1, ColDB_HSDK_Ktra).Value"
        and runtime["writer_procedure"] == "Tao_QDKT_KHKT_BBKT"
        and runtime["dossier_write_line"] == 748
        and runtime["submission_write_line"] == 749
        and runtime["dossier_bookmark"] == "HsDK"
        and runtime["submission_bookmark"] == "NgaynopHsDK"
        and runtime["submission_display_transform"] == "Replace('-', '/')"
        and runtime["replace_bookmark_procedure_lines"] == "589-603"
        and runtime["missing_bookmark_behavior"]
        == "SILENT_NO_OP_ON_ERROR_RESUME_NEXT",
        "QDKT_DOSSIER_VBA_ASSIGNMENT_DRIFT",
    )
    _require(
        date_semantics["classification"] == "VERIFIED"
        and date_semantics["business_meaning"] == "DOSSIER_SUBMISSION_DATE"
        and date_semantics["receipt_date_equivalence"] is False
        and date_semantics["decision_date_equivalence"] is False
        and date_semantics["inspection_date_equivalence"] is False
        and date_semantics["khkt_planning_date_equivalence"] is False
        and date_semantics["canonical_candidate"] == "CaseApplication.submitted_on"
        and date_semantics["canonical_mapping_confidence"] == "PARTIAL"
        and date_semantics["canonical_timezone_rule"]
        == "PARTIAL_UNPROVEN_BUSINESS_TIMEZONE"
        and date_semantics["legacy_display_normalization"] == "Replace('-', '/')",
        "QDKT_DOSSIER_DATE_SEMANTICS_DRIFT",
    )
    _require(
        dossier_semantics == {
            "classification": "VERIFIED",
            "business_meaning": "DOSSIER_CODE",
            "canonical_candidate": "CaseApplication.dossier_code",
            "canonical_mapping_confidence": "VERIFIED",
        },
        "QDKT_DOSSIER_CODE_SEMANTICS_DRIFT",
    )

    assets = {asset.gxp_type: asset for asset in load_inspection_qd_kt_template_assets()}
    findings: list[QdKtDossierTemplateSourceEvidence] = []
    rows = payload["templates"]
    _require(
        isinstance(rows, list) and {row.get("gxp_type") for row in rows} == _GXP_TYPES,
        "QDKT_DOSSIER_TEMPLATE_SET_DRIFT",
    )
    for row in rows:
        gxp_type = row["gxp_type"]
        asset = assets[gxp_type]
        _require(
            row["filename"] == asset.filename
            and row["sha256"] == asset.checksum_sha256
            and isinstance(row["byte_size"], int)
            and row["byte_size"] > 0,
            "QDKT_DOSSIER_TEMPLATE_IDENTITY_DRIFT",
        )
        _require(
            isinstance(row["scanned_word_parts"], list)
            and "word/document.xml" in row["scanned_word_parts"],
            "QDKT_DOSSIER_TEMPLATE_PARTS_UNVERIFIED",
        )
        targets = row["targets"]
        _require(set(targets) == set(_TARGETS), "QDKT_DOSSIER_TARGET_SET_DRIFT")
        for target in _TARGETS:
            observation = targets[target]
            _require(
                observation == {
                    "status": "VERIFIED_ABSENT",
                    "exact_case_match_count": 0,
                    "case_variant_count": 0,
                    "xml_location": None,
                    "enclosing_paragraph": None,
                    "field_code_context": None,
                    "span_structure": None,
                },
                "QDKT_DOSSIER_PHYSICAL_TARGET_DRIFT",
            )
        findings.append(
            QdKtDossierTemplateSourceEvidence(
                gxp_type=gxp_type,
                filename=row["filename"],
                sha256=row["sha256"],
                byte_size=row["byte_size"],
                scanned_word_parts=tuple(row["scanned_word_parts"]),
                bookmark_count=row["bookmark_count"],
                nested_pair_count=row["nested_pair_count"],
                overlapping_pair_count=row["overlapping_pair_count"],
                dossier_plain_text_paragraph_count=row[
                    "dossier_plain_text_paragraph_count"
                ],
            )
        )
    return QdKtDossierBookmarkSourceEvidence(
        workbook_sha256=workbook["sha256"],
        workbook_sheet=workbook["sheet"],
        workbook_named_range=workbook["named_range"],
        workbook_named_range_address=workbook["named_range_address"],
        vba_archive_sha256=vba["sha256"],
        registration_group_label=columns["group_label"],
        submission_column=columns["submission_column"],
        submission_header=columns["submission_header"],
        submission_named_ranges=tuple(columns["submission_named_ranges"]),
        dossier_column=columns["dossier_code_column"],
        dossier_header=columns["dossier_code_header"],
        date_semantics=date_semantics["business_meaning"],
        receipt_date_equivalence=date_semantics["receipt_date_equivalence"],
        date_display_transform=date_semantics["legacy_display_normalization"],
        canonical_date_timezone_rule=date_semantics["canonical_timezone_rule"],
        template_findings=tuple(sorted(findings, key=lambda item: item.gxp_type)),
    )


def _result(status: str, **evidence: object) -> QdKtDossierBookmarkEvidenceResult:
    if "ready_to_render" in evidence:
        raise ValueError("QDKT_DOSSIER_RENDER_OVERRIDE_DENIED")
    return QdKtDossierBookmarkEvidenceResult(status=status, **evidence)


def assess_qdkt_dossier_bookmark_evidence(
    *,
    template_audits: Sequence[QdKtDotxBinaryAudit],
    crosswalk: QdKtRg3CrosswalkResult,
    source_evidence: QdKtDossierBookmarkSourceEvidence | None = None,
    legacy_pair: QdKtDossierLegacyPair | None = None,
    allow_synthetic_template_checksums: bool = False,
) -> QdKtDossierBookmarkEvidenceResult:
    """Connect physical, legacy and canonical evidence without promotion.

    ``allow_synthetic_template_checksums`` exists only for unit testing the
    fail-closed state machine.  Results from that mode are explicitly marked
    synthetic and can never claim authoritative template identity.
    """
    source = source_evidence or load_qdkt_dossier_bookmark_source_evidence()
    pair = legacy_pair or inspect_qdkt_dossier_legacy_pair()
    audits = tuple(template_audits)
    if len(audits) != 4 or {audit.gxp_type for audit in audits} != _GXP_TYPES:
        return _result("TEMPLATE_SET_UNVERIFIED")
    if any(not audit.binary_checksum_verified for audit in audits):
        return _result("TEMPLATE_IDENTITY_UNVERIFIED")

    authoritative = not allow_synthetic_template_checksums
    if authoritative:
        expected = {row.gxp_type: row for row in source.template_findings}
        for audit in audits:
            row = expected[audit.gxp_type]
            if (
                audit.actual_sha256 != row.sha256
                or audit.expected_sha256 != row.sha256
                or audit.scanned_word_parts != row.scanned_word_parts
                or audit.bookmark_count != row.bookmark_count
                or len(audit.nested_bookmark_pairs) != row.nested_pair_count
                or len(audit.overlapping_bookmark_pairs) != row.overlapping_pair_count
                or audit.dossier_plain_text_paragraph_count
                != row.dossier_plain_text_paragraph_count
            ):
                return _result("TEMPLATE_PRIMARY_EVIDENCE_CONFLICT")

    if (
        not pair.same_legacy_row_proven
        or pair.code_column_offset != 1
        or pair.date_column_offset != 0
        or pair.code_expression != "s_MaHsDk"
        or pair.date_expression != 'Replace(s_NgaynopHsDk, "-", "/")'
        or pair.source_zip_sha256 != source.vba_archive_sha256
    ):
        return _result(
            "LEGACY_ASSIGNMENT_CHAIN_UNVERIFIED",
            template_identity_verified=authoritative,
        )

    per_target: dict[str, list[str]] = {target: [] for target in _TARGETS}
    for audit in audits:
        for target in _TARGETS:
            observed = classify_qdkt_target_bookmark(audit, target)
            if observed.status == "CASE_VARIANT_ONLY":
                return _result(
                    f"BOOKMARK_CASE_MISMATCH:{audit.gxp_type}:{target}",
                    template_identity_verified=authoritative,
                    legacy_assignment_chain_verified=True,
                )
            per_target[target].append(observed.status)

    if crosswalk.status == "KHKT_PATH_HAS_NO_RG3_SELECTION":
        return _result(
            "KHKT_PATH_HAS_NO_RG3_LINEAGE",
            template_identity_verified=authoritative,
            legacy_assignment_chain_verified=True,
        )
    required_crosswalk_flags = (
        crosswalk.same_worksheet_row,
        crosswalk.same_inspection_record,
        crosswalk.same_registered_site,
        crosswalk.same_canonical_case,
        crosswalk.same_application,
        crosswalk.dossier_value_projection_verified,
        crosswalk.submitted_value_projection_verified,
    )
    if crosswalk.status != "IDENTITY_PROVEN_SEMANTICS_PARTIAL" or not all(
        required_crosswalk_flags
    ):
        detail = (
            crosswalk.status
            if crosswalk.status != "IDENTITY_PROVEN_SEMANTICS_PARTIAL"
            else "INCOMPLETE_PROVEN_FLAGS"
        )
        return _result(
            f"CANONICAL_PROVENANCE_BLOCKED:{detail}",
            template_identity_verified=authoritative,
            legacy_assignment_chain_verified=True,
        )
    if not crosswalk.dossier_value_present or not crosswalk.submitted_value_present:
        return _result(
            "REQUIRED_DOSSIER_VALUES_MISSING",
            template_identity_verified=authoritative,
            legacy_assignment_chain_verified=True,
            canonical_case_application_site_verified=True,
        )

    physical: dict[str, str] = {}
    for target, statuses in per_target.items():
        if statuses == ["ABSENT"] * 4:
            physical[target] = "VERIFIED_ABSENT" if authoritative else "SYNTHETIC_ABSENT"
        elif statuses == ["EXACT_PRESENT"] * 4:
            physical[target] = "VERIFIED_PRESENT" if authoritative else "SYNTHETIC_PRESENT"
        else:
            return _result(
                f"BOOKMARK_SET_INCONSISTENT:{target}",
                template_identity_verified=authoritative,
                legacy_assignment_chain_verified=True,
                canonical_case_application_site_verified=True,
            )

    fields = (
        QdKtDossierFieldEvidence(
            bookmark_name="HsDK",
            physical_bookmark_status=physical["HsDK"],
            runtime_source="db.ktra selected Rg3 row, column 9 (ColDB_HSDK_Ktra + 1)",
            business_semantics="DOSSIER_CODE",
            business_semantics_confidence="VERIFIED",
            canonical_owner="CaseApplication.dossier_code",
            canonical_mapping_confidence="VERIFIED",
        ),
        QdKtDossierFieldEvidence(
            bookmark_name="NgaynopHsDK",
            physical_bookmark_status=physical["NgaynopHsDK"],
            runtime_source="db.ktra selected Rg3 row, column 8 (ColDB_HSDK_Ktra)",
            business_semantics="DOSSIER_SUBMISSION_DATE",
            business_semantics_confidence="VERIFIED",
            canonical_owner="CaseApplication.submitted_on",
            canonical_mapping_confidence="PARTIAL",
            date_normalization_rule=source.canonical_date_timezone_rule,
        ),
    )
    if not authoritative:
        status = "SYNTHETIC_PHYSICAL_BEHAVIOR_ONLY"
    elif set(physical.values()) == {"VERIFIED_ABSENT"}:
        status = "PHYSICAL_BOOKMARKS_VERIFIED_ABSENT"
    elif set(physical.values()) == {"VERIFIED_PRESENT"}:
        status = "PHYSICAL_BOOKMARKS_VERIFIED_PRESENT_OWNER_REVIEW_REQUIRED"
    else:
        status = "PHYSICAL_BOOKMARK_SET_INCONSISTENT"
    return _result(
        status,
        fields=fields,
        template_identity_verified=authoritative,
        legacy_assignment_chain_verified=True,
        canonical_case_application_site_verified=True,
    )
