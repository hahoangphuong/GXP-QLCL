"""Internal, read-only dossier readiness contract. Never a render authorization.

Approval records must come from the caller's trusted owner-review ledger, not
request JSON. This module validates their scope; it does not authenticate a
reviewer, replace DocumentService controls, or call a renderer/StorageService.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Literal, Mapping, Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select

from backend.app.db.models.phase1 import Case, CaseApplication, Site
from backend.app.document.inspection_qd_kt_dossier_bookmark_evidence import (
    load_qdkt_dossier_bookmark_source_evidence,
)
from backend.app.document.inspection_qd_kt_dotx_binary_audit import (
    QdKtDotxBinaryAudit, classify_qdkt_target_bookmark, inspect_qdkt_dotx_binary,
)
from backend.app.document.inspection_qd_kt_template_asset_contract import (
    InspectionQdKtTemplateAsset, load_inspection_qd_kt_template_assets,
)

CONTRACT_PATH = Path(__file__).with_name("inspection_qd_kt_renderer_decision.json")
TARGETS = ("HsDK", "NgaynopHsDK")
DateRule = Literal["UNDECIDED", "ISO_DATE_ONLY", "AWARE_RECORDED_OFFSET_DATE"]
SYNTHETIC_INPUT = {"HsDK": "UAT-SYNTHETIC-001", "NgaynopHsDK": "2026-01-02"}
SYNTHETIC_INPUT_SHA256 = sha256(json.dumps(SYNTHETIC_INPUT, sort_keys=True).encode()).hexdigest()


class StrictEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class BookmarkPlacement(StrictEvidence):
    bookmark: Literal["HsDK", "NgaynopHsDK"]
    part: str = Field(pattern=r"^word/(document|header[0-9]+|footer[0-9]+)\.xml$")
    start_location: str = Field(min_length=1)
    end_location: str = Field(min_length=1)
    semantic_context: str = Field(min_length=1)


class TemplateDecision(StrictEvidence):
    gxp_type: Literal["GLP", "GMP", "GMPbb", "GSP"]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_version: str | None = None
    candidate_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    placements: tuple[BookmarkPlacement, ...] = ()


class RendererDecision(StrictEvidence):
    schema_version: Literal["qdkt-dossier-renderer-decision/v1"]
    decision: Literal["UNDECIDED", "ADD_BOOKMARKS", "DEPRECATE_WRITES"]
    submission_date_rule: DateRule
    date_display_format: Literal["UNDECIDED", "DD/MM/YYYY", "YYYY-MM-DD"] = "UNDECIDED"
    templates: tuple[TemplateDecision, ...]
    approval_record_ids: tuple[str, ...] = ()
    ready_to_render: Literal[False] = False

    @field_validator("ready_to_render", mode="before")
    @classmethod
    def no_activation(cls, value):
        if value is not False:
            raise ValueError("QDKT_RENDER_ACTIVATION_FORBIDDEN")
        return value

    @field_validator("templates")
    @classmethod
    def exact_template_set(cls, rows: tuple[TemplateDecision, ...]):
        assets = {a.gxp_type: a for a in load_inspection_qd_kt_template_assets()}
        if len(rows) != 4 or {r.gxp_type for r in rows} != set(assets):
            raise ValueError("QDKT_DECISION_TEMPLATE_SET_INVALID")
        if any(r.source_sha256 != assets[r.gxp_type].checksum_sha256 for r in rows):
            raise ValueError("QDKT_DECISION_SOURCE_SHA_CONFLICT")
        return rows

    @field_validator("approval_record_ids")
    @classmethod
    def unique_approvals(cls, ids: tuple[str, ...]):
        if len(set(ids)) != len(ids) or any(not value.strip() for value in ids):
            raise ValueError("QDKT_APPROVAL_REFERENCE_INVALID")
        return ids


class ApprovalRecord(StrictEvidence):
    record_id: str = Field(min_length=1)
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    purpose: Literal["LEGAL_TEMPLATE", "DOSSIER_SEMANTICS", "DATE_NORMALIZATION", "DEPRECATE_WRITES", "WORD_UAT"]
    role: Literal["LEGAL_OWNER", "BUSINESS_OWNER", "UAT_OWNER"]
    reviewer_ref: str = Field(min_length=1)
    evidence_ref: str = Field(min_length=1)
    approved_at: str
    disposition: Literal["APPROVED", "REJECTED"]
    subject_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("record_id", "reviewer_ref", "evidence_ref")
    @classmethod
    def exact_nonblank_reference(cls, value: str):
        if not value.strip() or value != value.strip():
            raise ValueError("QDKT_APPROVAL_REFERENCE_INVALID")
        return value

    @field_validator("approved_at")
    @classmethod
    def aware_approval_time(cls, value: str):
        parsed = datetime.fromisoformat(value)
        if parsed.utcoffset() is None:
            raise ValueError("QDKT_APPROVAL_TIME_OFFSET_REQUIRED")
        return value


class WordUatEvidence(StrictEvidence):
    gxp_type: Literal["GLP", "GMP", "GMPbb", "GSP"]
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    template_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    template_version: str
    execution: Literal["NOT_EXECUTED", "MICROSOFT_WORD_DESKTOP"]
    result: Literal["NOT_EXECUTED", "PASS", "FAIL"]
    word_version: str | None = None
    tester_ref: str | None = None
    executed_at: str | None = None
    output_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    synthetic_input_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    screenshot_refs: tuple[str, ...] = ()
    acceptance_checks: tuple[str, ...] = ()


UAT_CHECKS = frozenset({
    "DOSSIER_VALUES", "MISSING_VALUE_BLOCKED", "IDENTITY_MISMATCH_BLOCKED",
    "FORMATTING", "PAGINATION", "SIGNATURE", "HEADER_FOOTER", "LEGAL_WORDING",
})


def load_renderer_decision(path: Path = CONTRACT_PATH) -> RendererDecision:
    return RendererDecision.model_validate_json(path.read_text(encoding="utf-8"))


def decision_digest(decision: RendererDecision) -> str:
    # Approval references are excluded to avoid self-referential signatures.
    content = decision.model_dump(mode="json", exclude={"approval_record_ids"})
    return sha256(json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def word_uat_digest(evidence: Sequence[WordUatEvidence]) -> str:
    content = [r.model_dump(mode="json") for r in sorted(evidence, key=lambda r: r.gxp_type)]
    return sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class SubmissionDateBlocked(ValueError):
    pass


def normalize_submission_date(value: date | datetime | str | None, *, rule: DateRule) -> date:
    """Only explicit calendar-day preservation; no implicit zone conversion.

    An aware timestamp's recorded offset supplies a local calendar day, not a
    proven business timezone. Choosing that rule requires separate owner approval
    in preflight. Naive timestamps remain unresolved even at midnight.
    """
    if value is None or value == "":
        raise SubmissionDateBlocked("QDKT_SUBMISSION_DATE_MISSING")
    if rule == "UNDECIDED":
        raise SubmissionDateBlocked("QDKT_DATE_NORMALIZATION_UNDECIDED")
    if isinstance(value, str):
        try:
            if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
                value = date.fromisoformat(value)
            elif re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])?", value):
                value = datetime.fromisoformat(value)
            else:
                raise ValueError("strict ISO representation required")
        except ValueError as exc:
            raise SubmissionDateBlocked("QDKT_SUBMISSION_DATE_INVALID") from exc
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise SubmissionDateBlocked("QDKT_NAIVE_TIMESTAMP_UNRESOLVED")
        if rule != "AWARE_RECORDED_OFFSET_DATE":
            raise SubmissionDateBlocked("QDKT_TIMESTAMP_TO_DATE_NOT_APPROVED")
        return value.date()
    if type(value) is date and rule == "ISO_DATE_ONLY":
        return value
    raise SubmissionDateBlocked("QDKT_DATE_REPRESENTATION_CONFLICT")


@dataclass(frozen=True)
class DossierSnapshot:
    case_id: str
    site_id: str
    application_id: str
    application_case_id: str
    application_version: int
    dossier_code: str | None
    submitted_on: datetime | None
    origin: str = "UNVERIFIED"


def read_dossier_snapshot(session, *, case_id: str) -> DossierSnapshot:
    """Current persisted owner only. No workbook/KHKT or implicit inheritance.

    Scalar SELECTs avoid identity-map cache and preserve pending user edits.
    Transaction isolation still limits visibility. The caller owns transaction
    scope and access control.
    """
    with session.no_autoflush:
        rows = session.execute(
            select(Case.id, Site.id, CaseApplication.id, CaseApplication.case_id,
                   CaseApplication.row_version, CaseApplication.dossier_code,
                   CaseApplication.submitted_on)
            .join(Site, Site.id == Case.site_id)
            .join(CaseApplication, CaseApplication.case_id == Case.id)
            .where(Case.id == case_id)
        ).all()
    if len(rows) != 1:
        raise ValueError("QDKT_CASE_APPLICATION_OWNER_MISSING_OR_AMBIGUOUS")
    case_id, site_id, application_id, application_case_id, version, code, submitted = rows[0]
    return DossierSnapshot(
        case_id=case_id, site_id=site_id, application_id=application_id,
        application_case_id=application_case_id, application_version=version,
        dossier_code=code, submitted_on=submitted, origin="PERSISTED_CASE_APPLICATION",
    )


@dataclass(frozen=True)
class PhysicalTemplateEvidence:
    audit: QdKtDotxBinaryAudit
    origin: Literal["PRIMARY_CANDIDATE_BYTES", "SYNTHETIC"]


def inspect_renderer_candidates(
    decision: RendererDecision, *, paths: Mapping[str, Path],
) -> tuple[PhysicalTemplateEvidence, ...]:
    """Explicit local candidate paths, pinned hashes, zero writes/storage calls."""
    if set(paths) != {t.gxp_type for t in decision.templates}:
        raise ValueError("QDKT_CANDIDATE_SET_INCOMPLETE")
    results = []
    for template in decision.templates:
        if not template.candidate_sha256 or not template.candidate_version:
            raise ValueError("QDKT_CANDIDATE_VERSION_UNAPPROVED")
        asset = InspectionQdKtTemplateAsset(
            gxp_type=template.gxp_type, filename=paths[template.gxp_type].name,
            storage_root="template", storage_relative_path=paths[template.gxp_type].name,
            checksum_sha256=template.candidate_sha256,
        )
        results.append(PhysicalTemplateEvidence(
            inspect_qdkt_dotx_binary(paths[template.gxp_type], asset=asset),
            "PRIMARY_CANDIDATE_BYTES",
        ))
    return tuple(results)


@dataclass(frozen=True)
class RendererPreflightResult:
    blockers: tuple[str, ...]
    contract_evidence_complete: bool
    # Intentionally cannot be set through the constructor.
    @property
    def ready_to_render(self) -> Literal[False]:
        return False


def assess_renderer_preflight(
    *, decision: RendererDecision, expected: DossierSnapshot | None,
    observed: DossierSnapshot | None,
    trusted_approvals: Mapping[str, ApprovalRecord],
    physical: Sequence[PhysicalTemplateEvidence] = (),
    word_uat: Sequence[WordUatEvidence] = (),
) -> RendererPreflightResult:
    """Collect review blockers; even complete evidence grants no render authority.

    Trusted approval ledger and primary-byte origin are internal caller trust
    boundaries. No JSON flag can authenticate legal/business approval here.
    Historical PR #159 crosswalk remains independent and is not a prerequisite
    for a modern Case without a legacy inspection ID.
    """
    blocks: list[str] = []
    def block(code: str):
        if code not in blocks:
            blocks.append(code)

    # Revalidate even internal model_copy/model_construct objects before trusting
    # their shape. Such constructors intentionally bypass Pydantic validation.
    try:
        decision = RendererDecision.model_validate_json(decision.model_dump_json())
        trusted_approvals = {
            ref: ApprovalRecord.model_validate_json(row.model_dump_json())
            for ref, row in trusted_approvals.items()
        }
        word_uat = tuple(WordUatEvidence.model_validate_json(row.model_dump_json()) for row in word_uat)
    except (ValidationError, AttributeError, TypeError, ValueError):
        return RendererPreflightResult(("QDKT_EVIDENCE_SCHEMA_INVALID",), False)
    if any(not isinstance(item, PhysicalTemplateEvidence) or not isinstance(item.audit, QdKtDotxBinaryAudit) for item in physical):
        return RendererPreflightResult(("QDKT_PHYSICAL_EVIDENCE_INVALID",), False)
    digest = decision_digest(decision)
    purposes: set[tuple[str, str]] = set()
    for ref in decision.approval_record_ids:
        record = trusted_approvals.get(ref)
        if record is None or record.record_id != ref:
            block("QDKT_APPROVAL_NOT_IN_TRUSTED_LEDGER")
        elif record.contract_sha256 != digest or record.disposition != "APPROVED":
            block("QDKT_APPROVAL_REJECTED_OR_STALE")
        elif record.purpose == "WORD_UAT" and record.subject_sha256 != word_uat_digest(word_uat):
            block("QDKT_WORD_UAT_APPROVAL_SUBJECT_CONFLICT")
        else:
            purposes.add((record.purpose, record.role))
    for purpose, role, code in (
        ("LEGAL_TEMPLATE", "LEGAL_OWNER", "QDKT_LEGAL_TEMPLATE_UNAPPROVED"),
        ("DOSSIER_SEMANTICS", "BUSINESS_OWNER", "QDKT_DOSSIER_SEMANTICS_UNAPPROVED"),
        ("DATE_NORMALIZATION", "BUSINESS_OWNER", "QDKT_DATE_NORMALIZATION_UNAPPROVED"),
        ("WORD_UAT", "UAT_OWNER", "QDKT_WORD_UAT_ACCEPTANCE_UNAPPROVED"),
    ):
        if (purpose, role) not in purposes:
            block(code)
    if decision.decision == "UNDECIDED":
        block("QDKT_LEGAL_DECISION_UNDECIDED")
    if decision.date_display_format == "UNDECIDED":
        block("QDKT_DATE_DISPLAY_UNAPPROVED")
    if decision.decision == "DEPRECATE_WRITES" and ("DEPRECATE_WRITES", "LEGAL_OWNER") not in purposes:
        block("QDKT_LEGACY_WRITE_DEPRECATION_UNAPPROVED")
    try:
        source_semantics = load_qdkt_dossier_bookmark_source_evidence().date_semantics
    except (ValueError, KeyError, TypeError, OSError):
        source_semantics = None
    if source_semantics != "DOSSIER_SUBMISSION_DATE":
        block("QDKT_SUBMISSION_SEMANTICS_UNVERIFIED")

    if not isinstance(expected, DossierSnapshot) or not isinstance(observed, DossierSnapshot):
        block("QDKT_CANONICAL_PROVENANCE_MISSING")
    else:
        for item in (expected, observed):
            try:
                if any(str(UUID(value)) != value for value in (
                    item.case_id, item.site_id, item.application_id, item.application_case_id,
                )):
                    raise ValueError("noncanonical UUID")
            except (ValueError, TypeError, AttributeError):
                block("QDKT_CANONICAL_UUID_INVALID")
            if item.origin != "PERSISTED_CASE_APPLICATION":
                block("QDKT_SYNTHETIC_SOURCE_UNSUPPORTED")
            if item.case_id != item.application_case_id:
                block("QDKT_APPLICATION_CASE_IDENTITY_CONFLICT")
            if type(item.application_version) is not int or item.application_version < 1:
                block("QDKT_APPLICATION_VERSION_INVALID")
            if not isinstance(item.dossier_code, str) or not item.dossier_code.strip() or item.dossier_code.strip() == "-":
                block("QDKT_DOSSIER_CODE_MISSING")
            elif item.dossier_code != item.dossier_code.strip() or len(item.dossier_code) > 128:
                block("QDKT_DOSSIER_CODE_INVALID")
            try:
                normalize_submission_date(item.submitted_on, rule=decision.submission_date_rule)
            except SubmissionDateBlocked as exc:
                block(str(exc))
        if (expected.case_id, expected.site_id, expected.application_id) != (
            observed.case_id, observed.site_id, observed.application_id,
        ):
            block("QDKT_CANONICAL_IDENTITY_CONFLICT")
        if expected.application_version != observed.application_version:
            block("QDKT_APPLICATION_VERSION_STALE")
        # Exact serialization detects equal instants with contradictory recorded
        # offsets, whose calendar dates may differ under the proposed rule.
        if (expected.dossier_code, str(expected.submitted_on)) != (observed.dossier_code, str(observed.submitted_on)):
            block("QDKT_DOSSIER_VALUE_CONFLICT")

    by_type = {item.audit.gxp_type: item for item in physical}
    if len(physical) != 4 or set(by_type) != {t.gxp_type for t in decision.templates}:
        block("QDKT_PHYSICAL_TEMPLATE_SET_INCOMPLETE")
    uat_by_type = {item.gxp_type: item for item in word_uat}
    if len(word_uat) != 4 or set(uat_by_type) != set(by_type):
        block("QDKT_WORD_UAT_SET_INCOMPLETE")
    for template in decision.templates:
        prefix = template.gxp_type
        if not template.candidate_version or not template.candidate_version.strip() or not template.candidate_sha256:
            block(f"QDKT_TEMPLATE_VERSION_UNAPPROVED:{prefix}")
        if decision.decision == "ADD_BOOKMARKS":
            if template.candidate_sha256 == template.source_sha256:
                block(f"QDKT_TEMPLATE_CANDIDATE_UNCHANGED:{prefix}")
            if len(template.placements) != 2 or {p.bookmark for p in template.placements} != set(TARGETS):
                block(f"QDKT_BOOKMARK_PLACEMENT_UNAPPROVED:{prefix}")
        elif template.placements:
            block(f"QDKT_UNEXPECTED_BOOKMARK_PLACEMENT:{prefix}")
        measured = by_type.get(prefix)
        if measured:
            audit = measured.audit
            if measured.origin != "PRIMARY_CANDIDATE_BYTES":
                block(f"QDKT_SYNTHETIC_PHYSICAL_EVIDENCE:{prefix}")
            if (audit.binary_checksum_verified is not True or
                audit.actual_sha256 != template.candidate_sha256 or
                audit.expected_sha256 != template.candidate_sha256):
                block(f"QDKT_TEMPLATE_CHECKSUM_CONFLICT:{prefix}")
            if audit.ready_to_render is not False or audit.bookmark_owner_parity_verified is not False:
                block(f"QDKT_PHYSICAL_UNSUPPORTED_APPROVAL_CLAIM:{prefix}")
            placements = {p.bookmark: p for p in template.placements}
            for target in TARGETS:
                evidence = classify_qdkt_target_bookmark(audit, target)
                if evidence.case_variant_names:
                    block(f"QDKT_BOOKMARK_CASE_VARIANT:{prefix}:{target}")
                if decision.decision == "ADD_BOOKMARKS":
                    if evidence.status != "EXACT_PRESENT" or len(evidence.exact_spans) != 1:
                        block(f"QDKT_REQUIRED_BOOKMARK_ABSENT_OR_AMBIGUOUS:{prefix}:{target}")
                    elif target in placements:
                        span, placement = evidence.exact_spans[0], placements[target]
                        if (span.part_name, span.start_location, span.end_location) != (
                            placement.part, placement.start_location, placement.end_location,
                        ) or span.nested_with or span.overlapping_with:
                            block(f"QDKT_BOOKMARK_PLACEMENT_CONFLICT:{prefix}:{target}")
                elif decision.decision == "DEPRECATE_WRITES" and evidence.status != "ABSENT":
                    block(f"QDKT_DEPRECATED_BOOKMARK_STILL_PRESENT:{prefix}:{target}")
        uat = uat_by_type.get(prefix)
        if uat is None or uat.execution != "MICROSOFT_WORD_DESKTOP" or uat.result != "PASS":
            block(f"QDKT_WORD_UAT_NOT_EXECUTED_OR_FAILED:{prefix}")
        elif (uat.contract_sha256 != digest or uat.template_sha256 != template.candidate_sha256 or
              uat.template_version != template.candidate_version):
            block(f"QDKT_WORD_UAT_IDENTITY_CONFLICT:{prefix}")
        else:
            if not all((uat.word_version, uat.tester_ref, uat.executed_at, uat.output_sha256,
                        uat.synthetic_input_sha256, uat.screenshot_refs)) or set(uat.acceptance_checks) != UAT_CHECKS:
                block(f"QDKT_WORD_UAT_EVIDENCE_INCOMPLETE:{prefix}")
            if any(not text or not text.strip() for text in (uat.word_version, uat.tester_ref, *uat.screenshot_refs)):
                block(f"QDKT_WORD_UAT_EVIDENCE_INCOMPLETE:{prefix}")
            if uat.synthetic_input_sha256 != SYNTHETIC_INPUT_SHA256:
                block(f"QDKT_WORD_UAT_INPUT_CONFLICT:{prefix}")
            try:
                if datetime.fromisoformat(uat.executed_at or "").utcoffset() is None:
                    raise ValueError("offset required")
            except ValueError:
                block(f"QDKT_WORD_UAT_TIME_INVALID:{prefix}")
    return RendererPreflightResult(tuple(blocks), not blocks)
