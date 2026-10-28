"""Internal, read-only dossier readiness contract. Never a render authorization.

Approval records must come from the caller's trusted owner-review ledger, not
request JSON. This module validates their scope; it does not authenticate a
reviewer, replace DocumentService controls, or call a renderer/StorageService.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Literal, Mapping, Sequence
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select

from backend.app.db.models.phase1 import Case, CaseApplication, Site
from backend.app.document.inspection_qd_kt_dossier_bookmark_evidence import (
    load_qdkt_dossier_bookmark_source_evidence,
)
from backend.app.document.inspection_qd_kt_dotx_binary_audit import (
    MAX_QDKT_DOTX_BYTES, QdKtBookmarkSpan, QdKtDotxAuditBlocked, QdKtDotxBinaryAudit, classify_qdkt_target_bookmark,
    inspect_qdkt_dotx_bytes,
)
from backend.app.document.inspection_qd_kt_template_asset_contract import (
    InspectionQdKtTemplateAsset, load_inspection_qd_kt_template_assets,
)

CONTRACT_PATH = Path(__file__).with_name("inspection_qd_kt_renderer_decision.json")
TARGETS = ("HsDK", "NgaynopHsDK")
DateRule = Literal["UNDECIDED", "ISO_DATE_ONLY", "AWARE_RECORDED_OFFSET_DATE"]
SYNTHETIC_INPUT = {"HsDK": "UAT-SYNTHETIC-001", "NgaynopHsDK": "2026-01-02"}
SYNTHETIC_INPUT_SHA256 = sha256(json.dumps(SYNTHETIC_INPUT, sort_keys=True).encode()).hexdigest()


def _evidence_timestamp(value: str) -> datetime:
    if type(value) is not str or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])", value,
    ) or value.endswith("-00:00"):
        raise ValueError("QDKT_EVIDENCE_TIME_INVALID")
    return datetime.fromisoformat(value)


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
        parsed = _evidence_timestamp(value)
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
    evidence_origin: Literal["UNVERIFIED", "OWNER_ATTESTED_WORD_EXECUTION", "SYNTHETIC"] = "UNVERIFIED"


UAT_CHECKS = frozenset({
    "DOSSIER_VALUES", "MISSING_VALUE_BLOCKED", "IDENTITY_MISMATCH_BLOCKED",
    "FORMATTING", "PAGINATION", "SIGNATURE", "HEADER_FOOTER", "LEGAL_WORDING",
})


def load_renderer_decision(path: Path = CONTRACT_PATH) -> RendererDecision:
    return RendererDecision.model_validate_json(path.read_text(encoding="utf-8"))


def _plain_evidence(value, depth: int = 0):
    """Snapshot only exact builtins/known models, without invoking serializers.

    In-process arbitrary-code execution is outside this validation boundary.
    Reject subclasses, callbacks, cycles and undeclared instance attributes.
    """
    if depth > 24:
        raise ValueError("QDKT_EVIDENCE_NESTING_INVALID")
    if type(value) in (str, int, bool, float, type(None)):
        return value
    if type(value) in (tuple, list):
        return type(value)(_plain_evidence(v, depth + 1) for v in value)
    if type(value) is dict:
        if any(type(k) is not str for k in value):
            raise ValueError("QDKT_EVIDENCE_KEYS_INVALID")
        return {k: _plain_evidence(v, depth + 1) for k, v in value.items()}
    if type(value) in (RendererDecision, TemplateDecision, BookmarkPlacement, ApprovalRecord, WordUatEvidence):
        raw = object.__getattribute__(value, "__dict__")
        extra = object.__getattribute__(value, "__pydantic_extra__")
        if type(raw) is not dict or extra is not None or set(raw) - set(type(value).model_fields):
            raise ValueError("QDKT_EVIDENCE_UNDECLARED_FIELDS")
        return _plain_evidence(raw, depth + 1)
    raise ValueError("QDKT_EVIDENCE_TYPE_INVALID")


def _checked_model(cls, value):
    if type(value) is not cls:
        raise ValueError("QDKT_EVIDENCE_MODEL_TYPE_INVALID")
    return cls.model_validate(_plain_evidence(value), strict=True)


def decision_digest(decision: RendererDecision) -> str:
    # Approval references are excluded to avoid self-referential signatures.
    return _decision_digest_checked(_checked_model(RendererDecision, decision))


def _decision_digest_checked(decision: RendererDecision) -> str:
    # Internal only: use the fresh model already validated at the entry boundary,
    # without re-reading the manifest midway through the same assessment.
    content = decision.model_dump(mode="json", exclude={"approval_record_ids"})
    return sha256(json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def word_uat_digest(evidence: Sequence[WordUatEvidence]) -> str:
    if type(evidence) not in (tuple, list):
        raise ValueError("QDKT_UAT_CONTAINER_INVALID")
    evidence = tuple(_checked_model(WordUatEvidence, row) for row in evidence)
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
    if type(rule) is not str or rule not in ("UNDECIDED", "ISO_DATE_ONLY", "AWARE_RECORDED_OFFSET_DATE"):
        raise SubmissionDateBlocked("QDKT_DATE_RULE_INVALID")
    if type(value) not in (str, date, datetime, type(None)):
        raise SubmissionDateBlocked("QDKT_DATE_REPRESENTATION_CONFLICT")
    if type(value) is datetime and type(value.tzinfo) not in (type(None), timezone, ZoneInfo):
        raise SubmissionDateBlocked("QDKT_TIMESTAMP_ZONE_TYPE_INVALID")
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
    candidate_bytes: bytes | None = field(default=None, repr=False)


def inspect_renderer_candidates(
    decision: RendererDecision, *, paths: Mapping[str, Path],
) -> tuple[PhysicalTemplateEvidence, ...]:
    """Explicit local candidate paths, pinned hashes, zero writes/storage calls."""
    decision = _checked_model(RendererDecision, decision)
    if type(paths) is not dict or set(paths) != {t.gxp_type for t in decision.templates}:
        raise ValueError("QDKT_CANDIDATE_SET_INCOMPLETE")
    if any(type(path) is not type(Path()) for path in paths.values()):
        raise ValueError("QDKT_CANDIDATE_PATH_TYPE_INVALID")
    results = []
    for template in decision.templates:
        if not template.candidate_sha256 or not template.candidate_version:
            raise ValueError("QDKT_CANDIDATE_VERSION_UNAPPROVED")
        asset = InspectionQdKtTemplateAsset(
            gxp_type=template.gxp_type, filename=paths[template.gxp_type].name,
            storage_root="template", storage_relative_path=paths[template.gxp_type].name,
            checksum_sha256=template.candidate_sha256,
        )
        try:
            with paths[template.gxp_type].open("rb") as stream:
                data = stream.read(MAX_QDKT_DOTX_BYTES + 1)
        except OSError as exc:
            raise QdKtDotxAuditBlocked("QDKT_DOTX_BINARY_UNAVAILABLE") from exc
        results.append(PhysicalTemplateEvidence(
            inspect_qdkt_dotx_bytes(data, asset=asset), "PRIMARY_CANDIDATE_BYTES", data,
        ))
    return tuple(results)


@dataclass(frozen=True)
class RendererPreflightResult:
    blockers: tuple[str, ...]
    contract_evidence_complete: bool
    def __post_init__(self):
        if (type(self.blockers) is not tuple or
            any(type(code) is not str or not code.strip() for code in self.blockers) or
            type(self.contract_evidence_complete) is not bool or
            self.contract_evidence_complete != (not self.blockers)):
            raise ValueError("QDKT_PREFLIGHT_RESULT_INCONSISTENT")
    # Intentionally cannot be set through the constructor.
    @property
    def ready_to_render(self) -> Literal[False]:
        return False


def _audit_snapshot(value, depth=0):
    if depth > 24:
        raise ValueError("QDKT_AUDIT_NESTING_INVALID")
    if type(value) in (QdKtDotxBinaryAudit, QdKtBookmarkSpan):
        raw = object.__getattribute__(value, "__dict__")
        if type(raw) is not dict or set(raw) != {f.name for f in fields(type(value))}:
            raise ValueError("QDKT_AUDIT_FIELDS_INVALID")
        return {k: _audit_snapshot(v, depth + 1) for k, v in raw.items()}
    if type(value) in (list, tuple):
        return type(value)(_audit_snapshot(v, depth + 1) for v in value)
    # Python considers 0 == 0.0 == False. Audit comparison must preserve types.
    plain = _plain_evidence(value)
    return (type(plain).__name__, plain)


def _checked_dossier(value):
    if value is None:
        return None
    if type(value) is not DossierSnapshot:
        raise ValueError("QDKT_DOSSIER_TYPE_INVALID")
    raw = object.__getattribute__(value, "__dict__")
    if type(raw) is not dict or set(raw) != {f.name for f in fields(DossierSnapshot)}:
        raise ValueError("QDKT_DOSSIER_FIELDS_INVALID")
    for name in ("case_id", "site_id", "application_id", "application_case_id", "origin"):
        if type(raw[name]) is not str:
            raise ValueError("QDKT_DOSSIER_SCALAR_INVALID")
    if type(raw["application_version"]) is not int or type(raw["dossier_code"]) not in (str, type(None)):
        raise ValueError("QDKT_DOSSIER_SCALAR_INVALID")
    value_date = raw["submitted_on"]
    if type(value_date) not in (datetime, type(None)) or (
        type(value_date) is datetime and type(value_date.tzinfo) not in (type(None), timezone, ZoneInfo)
    ):
        raise ValueError("QDKT_DOSSIER_TIMESTAMP_INVALID")
    return DossierSnapshot(**raw)


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

    # Validate raw Python values BEFORE serializers can erase fields/coerce types.
    try:
        if (type(trusted_approvals) is not dict or type(physical) not in (tuple, list) or
            type(word_uat) not in (tuple, list) or
            any(type(ref) is not str for ref in trusted_approvals)):
            raise ValueError("QDKT_EVIDENCE_CONTAINER_INVALID")
        decision = _checked_model(RendererDecision, decision)
        trusted_approvals = {
            ref: _checked_model(ApprovalRecord, row)
            for ref, row in trusted_approvals.items()
        }
        word_uat = tuple(_checked_model(WordUatEvidence, row) for row in word_uat)
        expected, observed = _checked_dossier(expected), _checked_dossier(observed)
    except (ValidationError, AttributeError, TypeError, ValueError):
        return RendererPreflightResult(("QDKT_EVIDENCE_SCHEMA_INVALID",), False)
    checked_physical = []
    try:
        for item in physical:
            if (type(item) is not PhysicalTemplateEvidence or type(item.audit) is not QdKtDotxBinaryAudit or
                type(item.audit.gxp_type) is not str or item.audit.gxp_type not in ("GLP", "GMP", "GMPbb", "GSP") or
                type(item.origin) is not str or item.origin not in ("PRIMARY_CANDIDATE_BYTES", "SYNTHETIC")):
                raise ValueError("QDKT_PHYSICAL_TYPE_INVALID")
            raw = object.__getattribute__(item, "__dict__")
            if type(raw) is not dict or set(raw) != {f.name for f in fields(PhysicalTemplateEvidence)}:
                raise ValueError("QDKT_PHYSICAL_FIELDS_INVALID")
            supplied = _audit_snapshot(item.audit)
            if type(item.candidate_bytes) is not bytes:
                block(f"QDKT_PHYSICAL_BYTES_UNBOUND:{item.audit.gxp_type}")
                continue
            if type(item.audit.expected_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", item.audit.expected_sha256):
                raise ValueError("QDKT_PHYSICAL_HASH_INVALID")
            asset = InspectionQdKtTemplateAsset(item.audit.gxp_type, "candidate.dotx", "template", "candidate.dotx", item.audit.expected_sha256)
            measured = inspect_qdkt_dotx_bytes(item.candidate_bytes, asset=asset)
            if supplied != _audit_snapshot(measured):
                block(f"QDKT_PHYSICAL_AUDIT_CONFLICT:{item.audit.gxp_type}")
            checked_physical.append(PhysicalTemplateEvidence(measured, item.origin, item.candidate_bytes))
    except (ValueError, TypeError, AttributeError, RecursionError):
        return RendererPreflightResult(("QDKT_PHYSICAL_EVIDENCE_INVALID",), False)
    physical = tuple(checked_physical)
    digest = _decision_digest_checked(decision)
    purposes: set[tuple[str, str]] = set()
    seen_purposes: set[str] = set()
    allowed_roles = {"LEGAL_TEMPLATE": "LEGAL_OWNER", "DOSSIER_SEMANTICS": "BUSINESS_OWNER", "DATE_NORMALIZATION": "BUSINESS_OWNER", "DEPRECATE_WRITES": "LEGAL_OWNER", "WORD_UAT": "UAT_OWNER"}
    for ref in decision.approval_record_ids:
        record = trusted_approvals.get(ref)
        if record is None or record.record_id != ref:
            block("QDKT_APPROVAL_NOT_IN_TRUSTED_LEDGER")
        elif record.contract_sha256 != digest or record.disposition != "APPROVED":
            block("QDKT_APPROVAL_REJECTED_OR_STALE")
        elif record.purpose in seen_purposes:
            block("QDKT_APPROVAL_PURPOSE_AMBIGUOUS")
        elif record.role != allowed_roles[record.purpose]:
            block("QDKT_APPROVAL_PURPOSE_ROLE_CONFLICT")
        elif record.purpose != "WORD_UAT" and record.subject_sha256 is not None:
            block("QDKT_APPROVAL_UNEXPECTED_SUBJECT")
        elif record.purpose == "WORD_UAT" and record.subject_sha256 != word_uat_digest(word_uat):
            block("QDKT_WORD_UAT_APPROVAL_SUBJECT_CONFLICT")
        else:
            purposes.add((record.purpose, record.role))
        if record is not None:
            seen_purposes.add(record.purpose)
            if record.purpose == "WORD_UAT" and record.disposition == "APPROVED":
                for row in word_uat:
                    try:
                        when = _evidence_timestamp(row.executed_at or "")
                        if when.utcoffset() is None or _evidence_timestamp(record.approved_at) < when:
                            block("QDKT_WORD_UAT_APPROVAL_TIME_CONFLICT")
                    except ValueError:
                        block("QDKT_WORD_UAT_APPROVAL_TIME_CONFLICT")
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
            if uat.evidence_origin != "OWNER_ATTESTED_WORD_EXECUTION":
                block(f"QDKT_WORD_UAT_ORIGIN_UNVERIFIED:{prefix}")
            if not all((uat.word_version, uat.tester_ref, uat.executed_at, uat.output_sha256,
                        uat.synthetic_input_sha256, uat.screenshot_refs)) or set(uat.acceptance_checks) != UAT_CHECKS:
                block(f"QDKT_WORD_UAT_EVIDENCE_INCOMPLETE:{prefix}")
            if any(not text or not text.strip() for text in (uat.word_version, uat.tester_ref, *uat.screenshot_refs)):
                block(f"QDKT_WORD_UAT_EVIDENCE_INCOMPLETE:{prefix}")
            if uat.synthetic_input_sha256 != SYNTHETIC_INPUT_SHA256:
                block(f"QDKT_WORD_UAT_INPUT_CONFLICT:{prefix}")
            try:
                if _evidence_timestamp(uat.executed_at or "").utcoffset() is None:
                    raise ValueError("offset required")
            except ValueError:
                block(f"QDKT_WORD_UAT_TIME_INVALID:{prefix}")
    return RendererPreflightResult(tuple(blocks), not blocks)
