"""Offline documentary validator. Run: python -m tools.validate_qdkt_owner_evidence.

Untrusted package records NEVER enter assess_renderer_preflight's trusted ledger.
No DB, storage service, network, Word automation, renderer, or output-file writes.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
from typing import Literal
from zipfile import BadZipFile, ZipFile

from pydantic import Field, ValidationError

from backend.app.document.inspection_qd_kt_dotx_binary_audit import inspect_qdkt_dotx_bytes, classify_qdkt_target_bookmark
from backend.app.document.inspection_qd_kt_renderer_contract import (
    ApprovalRecord, RendererDecision, StrictEvidence, WordUatEvidence,
    SYNTHETIC_INPUT_SHA256, TARGETS, UAT_CHECKS, decision_digest, word_uat_digest,
    _evidence_timestamp,
)
from backend.app.document.inspection_qd_kt_template_asset_contract import InspectionQdKtTemplateAsset
from tools._qdkt_evidence_io import EvidenceBlocked, FILE_LIMIT, JSON_LIMIT, PACKAGE_LIMIT, read_evidence, relative_parts

RefId = str
Gxp = Literal["GLP", "GMP", "GMPbb", "GSP"]
VARIANTS = {"GLP", "GMP", "GMPbb", "GSP"}
ROLES = {"LEGAL_TEMPLATE": "LEGAL_OWNER", "DOSSIER_SEMANTICS": "BUSINESS_OWNER", "DATE_NORMALIZATION": "BUSINESS_OWNER", "DEPRECATE_WRITES": "LEGAL_OWNER", "WORD_UAT": "UAT_OWNER"}
LIMITATIONS = [
    "PACKAGE_JSON_IS_NOT_A_TRUSTED_APPROVAL_LEDGER",
    "REVIEWER_AUTHENTICATION_AND_OWNER_AUTHORIZATION_NOT_VERIFIED",
    "WORD_DESKTOP_EXECUTION_AND_VISUAL_ACCEPTANCE_NOT_VERIFIED",
    "CHECKSUM_IS_CONTENT_INTEGRITY_NOT_IMMUTABLE_STORAGE_GENERATION",
    "FILE_SNAPSHOTS_ARE_NOT_AN_ATOMIC_PACKAGE_OR_FRESHNESS_PROOF",
    "NO_PERSISTED_CASE_APPLICATION_OR_RUNTIME_READINESS_VERIFICATION",
    "SUPPORTING_DOCUMENT_MEANING_AND_LEGAL_WORDING_NOT_VERIFIED",
]


class EvidenceReference(StrictEvidence):
    ref_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    path: str = Field(max_length=512)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    kind: Literal["decision", "source_template", "candidate_template", "approval_record", "word_uat", "supporting_document", "uat_output", "uat_screenshot"]


class VariantReferences(StrictEvidence):
    gxp_type: Gxp
    source_ref: RefId | None = None
    candidate_ref: RefId | None = None
    candidate_version: str | None = Field(default=None, min_length=1, max_length=128)
    word_uat_ref: RefId | None = None
    word_output_ref: RefId | None = None


class OwnerEvidenceManifest(StrictEvidence):
    schema_version: Literal["qdkt-owner-evidence-package/v1"]
    decision_ref: RefId
    decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    templates: tuple[VariantReferences, ...] = Field(max_length=4)
    approval_record_refs: tuple[RefId, ...] = Field(max_length=16)
    evidence: tuple[EvidenceReference, ...] = Field(max_length=128)


def _json(data: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise EvidenceBlocked("QDKT_PACKAGE_JSON_DUPLICATE_KEY")
            result[key] = value
        return result
    def invalid_constant(_):
        raise EvidenceBlocked("QDKT_PACKAGE_JSON_INVALID")
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=unique, parse_constant=invalid_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise EvidenceBlocked("QDKT_PACKAGE_JSON_INVALID") from exc


def _model(cls, data: bytes):
    # JSON-mode validation preserves existing tuple schemas; duplicate keys have
    # already been rejected, including inside referenced evidence documents.
    return cls.model_validate_json(json.dumps(_json(data), allow_nan=False))


def _audit_template(data: bytes, gxp_type: str, checksum: str):
    # Package-level resource policy, before the shared semantic byte auditor.
    # No archive extraction, external relationship resolution or code execution.
    try:
        with ZipFile(BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) > 256 or sum(m.file_size for m in members) > 64 * 1024 * 1024:
                raise ValueError("QDKT_PACKAGE_ZIP_LIMIT")
            for member in members:
                name = member.filename
                if "\\" in name or name.startswith("/") or any(p in (".", "..") for p in name.split("/")) or ":" in name:
                    raise ValueError("QDKT_PACKAGE_ZIP_PATH")
    except BadZipFile as exc:
        raise ValueError("QDKT_PACKAGE_ZIP_INVALID") from exc
    return inspect_qdkt_dotx_bytes(data, asset=InspectionQdKtTemplateAsset(gxp_type, "evidence.dotx", "template", "evidence.dotx", checksum))


def _report() -> dict:
    return {
        "schema_version": "qdkt-owner-evidence-report/v1",
        "manifest_schema_version": None, "source_manifest_sha256": None,
        "decision_sha256": None, "decision": "UNDECIDED", "candidates": [],
        "submission_date_rule": "UNDECIDED", "date_display_format": "UNDECIDED",
        "evidence_references": [], "documentary_blockers": [],
        "trust_blockers": ["QDKT_PACKAGE_AUTHORIZATION_NOT_VERIFIED", "QDKT_PACKAGE_WORD_EXECUTION_NOT_VERIFIED"],
        "evidence_complete": False, "trusted_authorization_verified": False,
        "word_uat_verified": False, "ready_to_render": False,
        "owner_checklists": [
            {"option": "ADD_BOOKMARKS", "requirements": ["EXACT_BOOKMARK_NAMES_AND_PLACEMENT", "LEGAL_WORDING_APPROVAL", "INDEPENDENT_CANDIDATE_VERSION_AND_SHA256", "DOSSIER_AND_DATE_POLICY_APPROVAL", "FOUR_VARIANT_WORD_UAT_AND_ACCEPTANCE"]},
            {"option": "DEPRECATE_WRITES", "requirements": ["LEGAL_AND_BUSINESS_ACCEPTANCE_OF_OMITTED_FIELDS", "DEPRECATION_APPROVAL", "CANDIDATE_VERSION_AND_SHA256", "DOSSIER_AND_DATE_POLICY_APPROVAL", "FOUR_VARIANT_WORD_UAT_AND_ACCEPTANCE"]},
        ],
        "limitations": LIMITATIONS.copy(),
    }


def validate_package(manifest_path: Path) -> dict:
    """Return deterministic, redacted documentary findings; never authorization."""
    report = _report()
    blocks: set[str] = set()
    try:
        # absolute(), deliberately not resolve(): links must be rejected, not
        # normalized away. The manifest's own parent is the explicit read root.
        path = Path(manifest_path).absolute()
        relative_parts(path.name)
        root = path.parent
        manifest_bytes = read_evidence(root, path.name, JSON_LIMIT)
        report["source_manifest_sha256"] = sha256(manifest_bytes).hexdigest()
        manifest = _model(OwnerEvidenceManifest, manifest_bytes)
        report["manifest_schema_version"] = manifest.schema_version
        if len(manifest.templates) != 4 or {t.gxp_type for t in manifest.templates} != VARIANTS:
            blocks.add("QDKT_PACKAGE_VARIANT_SET_INVALID")
        refs = {r.ref_id: r for r in manifest.evidence}
        if len(refs) != len(manifest.evidence):
            raise EvidenceBlocked("QDKT_PACKAGE_REFERENCE_DUPLICATE")
        paths = set()
        for ref in manifest.evidence:
            relative_parts(ref.path)
            canonical_path = ref.path.casefold()
            if canonical_path in paths or canonical_path == path.name.casefold():
                raise EvidenceBlocked("QDKT_PACKAGE_REFERENCE_PATH_CONFLICT")
            paths.add(canonical_path)
        data_by_ref = {}
        total = len(manifest_bytes)
        for ref in sorted(manifest.evidence, key=lambda r: r.ref_id):
            summary = {"ref_id": ref.ref_id, "kind": ref.kind, "declared_sha256": ref.sha256, "actual_sha256": None, "status": "BLOCKED"}
            report["evidence_references"].append(summary)
            try:
                limit = JSON_LIMIT if ref.kind in {"decision", "approval_record", "word_uat"} else FILE_LIMIT
                data = read_evidence(root, ref.path, min(limit, PACKAGE_LIMIT - total))
                total += len(data)
                actual = sha256(data).hexdigest()
                summary["actual_sha256"] = actual
                if actual != ref.sha256:
                    blocks.add(f"QDKT_PACKAGE_REFERENCE_SHA_CONFLICT:{ref.ref_id}")
                else:
                    data_by_ref[ref.ref_id] = data
                    summary["status"] = "BYTES_VERIFIED"
            except EvidenceBlocked as exc:
                blocks.add(f"{exc}:{ref.ref_id}")

        used = set()
        def require(ref_id, kind):
            if ref_id is None:
                blocks.add(f"QDKT_PACKAGE_REFERENCE_MISSING:{kind}")
                return None
            used.add(ref_id)
            ref = refs.get(ref_id)
            if ref is None or ref.kind != kind:
                blocks.add(f"QDKT_PACKAGE_REFERENCE_KIND_OR_ID_INVALID:{kind}")
                return None
            return data_by_ref.get(ref_id)

        decision_bytes = require(manifest.decision_ref, "decision")
        if decision_bytes is None:
            raise EvidenceBlocked("QDKT_PACKAGE_DECISION_UNAVAILABLE")
        decision = _model(RendererDecision, decision_bytes)
        digest = decision_digest(decision)
        report.update(decision=decision.decision, decision_sha256=digest, submission_date_rule=decision.submission_date_rule, date_display_format=decision.date_display_format)
        if digest != manifest.decision_sha256:
            blocks.add("QDKT_PACKAGE_DECISION_DIGEST_CONFLICT")
        if decision.decision == "UNDECIDED":
            blocks.add("QDKT_PACKAGE_DECISION_UNDECIDED")
        if decision.submission_date_rule == "UNDECIDED" or decision.date_display_format == "UNDECIDED":
            blocks.add("QDKT_PACKAGE_DATE_POLICY_UNDECIDED")
        templates = {t.gxp_type: t for t in decision.templates}
        uat_rows = []
        for variant in sorted(manifest.templates, key=lambda t: t.gxp_type):
            t = templates[variant.gxp_type]
            report["candidates"].append({"gxp_type": t.gxp_type, "declared_sha256": t.candidate_sha256, "actual_sha256": None,
                "candidate_version_sha256": sha256(t.candidate_version.encode()).hexdigest() if t.candidate_version else None,
                "version_matches_manifest": variant.candidate_version == t.candidate_version})
            for kind, ref_id, checksum in (("source_template", variant.source_ref, t.source_sha256), ("candidate_template", variant.candidate_ref, t.candidate_sha256)):
                data = require(ref_id, kind)
                if data is None:
                    continue
                actual = sha256(data).hexdigest()
                if kind == "candidate_template":
                    report["candidates"][-1]["actual_sha256"] = actual
                if checksum != actual:
                    blocks.add(f"QDKT_PACKAGE_{kind.upper()}_SHA_CONFLICT:{t.gxp_type}")
                    continue
                try:
                    audit = _audit_template(data, t.gxp_type, actual)
                    if kind == "candidate_template":
                        _check_placements(decision, t, audit, blocks)
                except ValueError:
                    blocks.add(f"QDKT_PACKAGE_TEMPLATE_BINARY_INVALID:{t.gxp_type}:{kind}")
            if not t.candidate_sha256 or not t.candidate_version or not t.candidate_version.strip():
                blocks.add(f"QDKT_PACKAGE_CANDIDATE_UNDECLARED:{t.gxp_type}")
            if variant.candidate_version != t.candidate_version:
                blocks.add(f"QDKT_PACKAGE_CANDIDATE_VERSION_CONFLICT:{t.gxp_type}")
            if decision.decision == "ADD_BOOKMARKS" and t.candidate_sha256 == t.source_sha256:
                blocks.add(f"QDKT_PACKAGE_CANDIDATE_NOT_INDEPENDENT:{t.gxp_type}")
            uat_bytes = require(variant.word_uat_ref, "word_uat")
            if uat_bytes is not None:
                try:
                    uat = _model(WordUatEvidence, uat_bytes)
                    uat_rows.append(uat)
                    _check_uat(uat, t, digest, variant.word_output_ref, refs, require, blocks)
                except (ValueError, ValidationError):
                    blocks.add(f"QDKT_PACKAGE_WORD_UAT_INVALID:{t.gxp_type}")
        if len(uat_rows) != 4 or {u.gxp_type for u in uat_rows} != VARIANTS:
            blocks.add("QDKT_PACKAGE_WORD_UAT_SET_INCOMPLETE")
        records = []
        if len(set(manifest.approval_record_refs)) != len(manifest.approval_record_refs):
            blocks.add("QDKT_PACKAGE_APPROVAL_REFERENCE_DUPLICATE")
        for ref_id in manifest.approval_record_refs:
            raw = require(ref_id, "approval_record")
            if raw is not None:
                try:
                    records.append(_model(ApprovalRecord, raw))
                except ValueError:
                    blocks.add("QDKT_PACKAGE_APPROVAL_RECORD_INVALID")
        if len({r.record_id for r in records}) != len(records) or len({r.purpose for r in records}) != len(records):
            blocks.add("QDKT_PACKAGE_APPROVAL_RECORD_CONFLICT")
        if {r.record_id for r in records} != set(decision.approval_record_ids):
            blocks.add("QDKT_PACKAGE_APPROVAL_SELECTION_CONFLICT")
        required = {"LEGAL_TEMPLATE", "DOSSIER_SEMANTICS", "DATE_NORMALIZATION", "WORD_UAT"}
        if decision.decision == "DEPRECATE_WRITES":
            required.add("DEPRECATE_WRITES")
        for purpose in required - {r.purpose for r in records}:
            blocks.add(f"QDKT_PACKAGE_APPROVAL_DOCUMENT_MISSING:{purpose}")
        for record in records:
            require(record.evidence_ref, "supporting_document")
            if record.contract_sha256 != digest or record.disposition != "APPROVED" or record.role != ROLES[record.purpose]:
                blocks.add(f"QDKT_PACKAGE_APPROVAL_SCOPE_CONFLICT:{record.purpose}")
            if record.purpose == "WORD_UAT":
                if record.subject_sha256 != word_uat_digest(uat_rows):
                    blocks.add("QDKT_PACKAGE_UAT_SUBJECT_CONFLICT")
                for uat in uat_rows:
                    try:
                        if _evidence_timestamp(record.approved_at) < _evidence_timestamp(uat.executed_at or ""):
                            blocks.add("QDKT_PACKAGE_UAT_ACCEPTANCE_TIME_CONFLICT")
                    except ValueError:
                        blocks.add("QDKT_PACKAGE_WORD_UAT_TIME_INVALID")
            elif record.subject_sha256 is not None:
                blocks.add("QDKT_PACKAGE_APPROVAL_SUBJECT_UNEXPECTED")
        if set(refs) - used:
            blocks.add("QDKT_PACKAGE_UNREFERENCED_EVIDENCE")
    except EvidenceBlocked as exc:
        blocks.add(str(exc))
    except (ValueError, TypeError, RecursionError, OSError):
        # Never echo validation payloads, document text, reviewer IDs or paths.
        blocks.add("QDKT_PACKAGE_SCHEMA_INVALID")
    report["documentary_blockers"] = sorted(blocks)
    report["evidence_complete"] = not blocks
    return report


def _check_placements(decision, template, audit, blocks):
    placements = {p.bookmark: p for p in template.placements}
    if decision.decision == "ADD_BOOKMARKS" and (len(template.placements) != 2 or set(placements) != set(TARGETS)):
        blocks.add(f"QDKT_PACKAGE_PLACEMENT_INCOMPLETE:{template.gxp_type}")
    if decision.decision == "DEPRECATE_WRITES" and template.placements:
        blocks.add(f"QDKT_PACKAGE_DEPRECATION_PLACEMENT_CONFLICT:{template.gxp_type}")
    for target in TARGETS:
        evidence = classify_qdkt_target_bookmark(audit, target)
        if decision.decision == "ADD_BOOKMARKS":
            if evidence.case_variant_names or evidence.status != "EXACT_PRESENT" or len(evidence.exact_spans) != 1 or target not in placements:
                blocks.add(f"QDKT_PACKAGE_BOOKMARK_CONFLICT:{template.gxp_type}:{target}")
            else:
                span, placement = evidence.exact_spans[0], placements[target]
                if (span.part_name, span.start_location, span.end_location) != (placement.part, placement.start_location, placement.end_location) or span.nested_with or span.overlapping_with:
                    blocks.add(f"QDKT_PACKAGE_BOOKMARK_CONFLICT:{template.gxp_type}:{target}")
        elif decision.decision == "DEPRECATE_WRITES" and (evidence.status != "ABSENT" or evidence.case_variant_names):
            blocks.add(f"QDKT_PACKAGE_DEPRECATED_BOOKMARK_PRESENT:{template.gxp_type}")


def _check_uat(uat, template, digest, output_ref, refs, require, blocks):
    if (uat.gxp_type, uat.contract_sha256, uat.template_sha256, uat.template_version) != (template.gxp_type, digest, template.candidate_sha256, template.candidate_version):
        blocks.add(f"QDKT_PACKAGE_WORD_UAT_IDENTITY_CONFLICT:{template.gxp_type}")
    if uat.evidence_origin != "OWNER_ATTESTED_WORD_EXECUTION" or uat.execution != "MICROSOFT_WORD_DESKTOP" or uat.result != "PASS":
        blocks.add(f"QDKT_PACKAGE_WORD_UAT_NOT_ATTESTED:{template.gxp_type}")
    if (not uat.word_version or not uat.word_version.strip() or not uat.tester_ref or not uat.tester_ref.strip()
        or not uat.screenshot_refs or set(uat.acceptance_checks) != UAT_CHECKS
        or uat.synthetic_input_sha256 != SYNTHETIC_INPUT_SHA256):
        blocks.add(f"QDKT_PACKAGE_WORD_UAT_INCOMPLETE:{template.gxp_type}")
    try:
        _evidence_timestamp(uat.executed_at or "")
    except ValueError:
        blocks.add("QDKT_PACKAGE_WORD_UAT_TIME_INVALID")
    # The variant explicitly owns an output ref: no hash/filename lookup.
    require(output_ref, "uat_output")
    if output_ref not in refs or refs[output_ref].sha256 != uat.output_sha256:
        blocks.add(f"QDKT_PACKAGE_WORD_UAT_OUTPUT_CONFLICT:{template.gxp_type}")
    for ref_id in uat.screenshot_refs:
        require(ref_id, "uat_screenshot")


def render_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2) + "\n"


def render_markdown(report: dict) -> str:
    # Embed exactly the same structured report; JSON escaping prevents Markdown
    # injection and avoids a second, divergent interpretation of the findings.
    return "# QDKT offline documentary evidence report\n\nNot authorization, Word execution proof, or render readiness.\n\n```json\n" + render_json(report) + "```\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    report = validate_package(args.manifest)
    sys.stdout.write(render_json(report) if args.format == "json" else render_markdown(report))
    # No offline package can authorize this process. Never emit an exit status
    # that a caller might mistake for permission to render.
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
