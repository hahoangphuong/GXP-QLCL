"""Fail-closed B6I human review workspace for blocked ProductionLine evidence.

This module owns review presentation and review-decision validation only.  It
does not create ProductionLine rows or alter any canonical relationship.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping
from uuid import UUID

from backend.app.domain.legacy_db_ktra_source_v2 import snapshot_cell_value, snapshot_columns
from backend.app.domain.production_line_population import (
    CANONICAL_SNAPSHOT_SHA256,
    PLANNER_VERSION,
    ProductionLinePlanningError,
    build_production_line_population_plan,
    canonical_artifact_bytes,
    canonical_json_bytes,
    source_line_evidence,
)


REVIEW_SCHEMA_VERSION = "production-line-physical-identity-review/v2"
PENDING_DECISION = "PENDING_HUMAN_REVIEW"
DECISIONS = frozenset({
    "APPROVE_NEW_PHYSICAL_LINE",
    "MAP_TO_EXISTING_PRODUCTION_LINE",
    "REJECT_NOT_PHYSICAL_LINE",
    "DEFER_INSUFFICIENT_EVIDENCE",
    "SPLIT_REQUIRED",
    "CONFLICT",
})


class ProductionLineReviewWorkspaceError(ValueError):
    """Raised when a human review workbook/roster is not provenance-safe."""


def _sha256(value: Mapping[str, Any]) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


def _uuid(value: object, *, label: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ProductionLineReviewWorkspaceError(f"B6I {label} must be a UUID")
    try:
        return str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ProductionLineReviewWorkspaceError(f"B6I {label} must be a valid UUID") from exc


def _site_names(snapshot: Mapping[str, Any]) -> dict[int, str | None]:
    rows, columns = snapshot_columns(snapshot, "db.cso", required_headers=("ID", "TÊN CƠ SỞ"))
    result: dict[int, str | None] = {}
    for row in rows:
        raw_id = snapshot_cell_value(row, columns["ID"])
        site_id = int(raw_id) if isinstance(raw_id, int) or isinstance(raw_id, float) and raw_id.is_integer() else None
        if site_id is None:
            continue
        name = snapshot_cell_value(row, columns["TÊN CƠ SỞ"])
        result[site_id] = name if isinstance(name, str) and name.strip() else None
    return result


def candidate_set_digest(items: list[Mapping[str, Any]]) -> str:
    """Bind the immutable review surface, excluding reviewer-controlled columns."""
    value = [{
        "candidate_key": item["candidate_key"],
        "source_site_legacy_id": item["source_site_legacy_id"],
        "canonical_site_id": item["canonical_site_id"],
        "canonical_line_text": item["canonical_line_text"],
        "review_tags": item["review_tags"],
    } for item in sorted(items, key=lambda row: row["candidate_key"])]
    return _sha256({"items": value})


def _primary_batch(tags: list[str]) -> str:
    if {"CERTIFICATE_SITE_MISMATCH_CONTEXT", "COMBINED_NOTATION", "MULTIPLE_RAW_TEXT_VARIANTS"} & set(tags):
        return "C_SPECIAL_EXCEPTION"
    if "LOW_INFORMATION_TEXT" in tags:
        return "D_LOW_INFORMATION"
    if "CASE_ONLY" in tags:
        return "B_CASE_ONLY"
    return "A_MULTI_SOURCE_HIGH_INFORMATION"


def _batch_order(batch: str) -> int:
    return {
        "A_MULTI_SOURCE_HIGH_INFORMATION": 1,
        "B_CASE_ONLY": 2,
        "C_SPECIAL_EXCEPTION": 3,
        "D_LOW_INFORMATION": 4,
    }[batch]


def _sample_evidence(snapshot: Mapping[str, Any]) -> tuple[dict[int, Mapping[str, Any]], dict[int, Mapping[str, Any]]]:
    cases, certificates = source_line_evidence(snapshot)
    return (
        {item["legacy_inspection_id"]: item for item in cases},
        {item["legacy_certificate_id"]: item for item in certificates},
    )


def build_review_workspace(
    snapshot: Mapping[str, Any],
    *,
    snapshot_sha256: str,
    canonical_state: Mapping[str, Any],
    canonical_state_sha256: str,
) -> dict[str, Any]:
    """Build deterministic B6I review records from verified read-only inputs."""
    if snapshot_sha256 != CANONICAL_SNAPSHOT_SHA256:
        raise ProductionLineReviewWorkspaceError("B6I requires the authoritative Legacy Snapshot V2 SHA256")
    try:
        plan = build_production_line_population_plan(
            snapshot,
            snapshot_sha256=snapshot_sha256,
            canonical_state=canonical_state,
            canonical_state_sha256=canonical_state_sha256,
        )
    except ProductionLinePlanningError as exc:
        raise ProductionLineReviewWorkspaceError(str(exc)) from exc
    discovery = plan["discovery"]
    candidates = discovery["candidates"]
    if any(candidate["canonical_site_id"] is None for candidate in candidates):
        raise ProductionLineReviewWorkspaceError("B6I requires every review candidate to resolve to a canonical Site")
    site_names = _site_names(snapshot)
    source_cases, source_certificates = _sample_evidence(snapshot)
    case_records = {record["legacy_inspection_id"]: record for record in plan["case_linkage"]["records"]}
    certificate_records = {record["legacy_certificate_id"]: record for record in plan["certificate_linkage"]["records"]}
    mismatch_certificate_ids = {
        record["legacy_certificate_id"]
        for record in plan["certificate_linkage"]["records"]
        if record["classification"] == "BLOCKED_SITE_MISMATCH"
    }
    items: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for candidate in candidates:
        tags = list(candidate.get("review_tags") or [])
        if not tags:
            # The v1 discovery artifact predates review tags; derive under the v2 owner.
            from backend.app.domain.production_line_population import review_tags_for_candidate
            text_occurrences = sum(other["canonical_line_text"] == candidate["canonical_line_text"] for other in candidates)
            tags = review_tags_for_candidate(candidate, cross_site_same_text=text_occurrences > 1)
        if mismatch_certificate_ids.intersection(candidate["source_certificate_ids"]):
            tags.append("CERTIFICATE_SITE_MISMATCH_CONTEXT")
        batch = _primary_batch(tags)
        case_samples = [{
            "legacy_inspection_id": legacy_id,
            "canonical_case_id": case_records[legacy_id]["canonical_case_id"],
            "scope_code": source_cases[legacy_id].get("scope_code"),
            "source_ref": source_cases[legacy_id]["source_ref"],
        } for legacy_id in candidate["source_case_ids"]]
        certificate_samples = [{
            "legacy_certificate_id": legacy_id,
            "canonical_certificate_id": certificate_records[legacy_id]["canonical_certificate_id"],
            "line_code_raw": source_certificates[legacy_id]["line"].get("source_text"),
            "certificate_reference": source_certificates[legacy_id].get("certificate_reference"),
            "source_ref": source_certificates[legacy_id]["source_ref"],
        } for legacy_id in candidate["source_certificate_ids"]]
        item = {
            "candidate_key": candidate["candidate_key"],
            "source_site_legacy_id": candidate["source_site_legacy_id"],
            "canonical_site_id": candidate["canonical_site_id"],
            "site_display_name": site_names.get(candidate["source_site_legacy_id"]),
            "canonical_line_text": candidate["canonical_line_text"],
            "observed_line_texts_raw": candidate["observed_line_texts"],
            "source_case_ids": candidate["source_case_ids"],
            "source_certificate_ids": candidate["source_certificate_ids"],
            "case_count": len(candidate["source_case_ids"]),
            "certificate_count": len(candidate["source_certificate_ids"]),
            "gxp_contexts": candidate["gxp_contexts"],
            "case_certificate_agreement": "CASE_AND_CERTIFICATE_AGREE" in tags,
            "cross_site_same_text": "CROSS_SITE_TEXT_REUSE" in tags,
            "review_tags": tags,
            "primary_review_batch": batch,
            "review_status": PENDING_DECISION,
            "review_decision": PENDING_DECISION,
            "approved_display_code": None,
            "existing_production_line_id": None,
            "review_reason": None,
            "reviewer": None,
            "reviewed_at": None,
        }
        items.append(item)
        evidence.append({"candidate_key": candidate["candidate_key"], "case_samples": case_samples, "certificate_samples": certificate_samples})
    items.sort(key=lambda item: (_batch_order(item["primary_review_batch"]), item["source_site_legacy_id"], item["canonical_line_text"], item["candidate_key"]))
    for order, item in enumerate(items, start=1):
        item["review_order"] = order
    candidate_set_digest_value = candidate_set_digest(items)
    roster = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "artifact_kind": "production_line_physical_identity_review_roster",
        "generated_at": None,
        "planner_version": PLANNER_VERSION,
        "legacy_snapshot_sha256": snapshot_sha256,
        "canonical_state_sha256": canonical_state_sha256,
        "candidate_set_sha256": candidate_set_digest_value,
        "items": items,
    }
    roster["content_sha256"] = sha256(canonical_artifact_bytes(roster)).hexdigest()
    return {
        "roster": roster,
        "evidence": evidence,
        "plan": plan,
        "source_evidence": (list(source_cases.values()), list(source_certificates.values())),
    }


def validate_review_decision(item: Mapping[str, Any], *, existing_line_ids: set[str]) -> None:
    decision = item.get("review_decision")
    if decision == PENDING_DECISION:
        if any(item.get(key) not in {None, ""} for key in ("approved_display_code", "existing_production_line_id", "review_reason")):
            raise ProductionLineReviewWorkspaceError("B6I pending review row cannot carry a decision payload")
        return
    if decision not in DECISIONS:
        raise ProductionLineReviewWorkspaceError("B6I review row has unsupported decision")
    if not isinstance(item.get("review_reason"), str) or not item["review_reason"].strip():
        raise ProductionLineReviewWorkspaceError("B6I non-pending review decision requires review_reason")
    if decision == "APPROVE_NEW_PHYSICAL_LINE":
        if not isinstance(item.get("approved_display_code"), str) or not item["approved_display_code"].strip():
            raise ProductionLineReviewWorkspaceError("B6I new physical line approval requires approved_display_code")
        if item.get("existing_production_line_id") not in {None, ""}:
            raise ProductionLineReviewWorkspaceError("B6I new physical line approval cannot reference an existing line")
    elif decision == "MAP_TO_EXISTING_PRODUCTION_LINE":
        line_id = _uuid(item.get("existing_production_line_id"), label="mapped ProductionLine ID")
        if line_id not in existing_line_ids:
            raise ProductionLineReviewWorkspaceError("B6I mapped ProductionLine is not available in the bound canonical state")
    elif any(item.get(key) not in {None, ""} for key in ("approved_display_code", "existing_production_line_id")):
        raise ProductionLineReviewWorkspaceError("B6I non-mapping review decision has incompatible line payload")


def reviewed_roster_from_rows(
    template: Mapping[str, Any],
    *,
    workbook_metadata: Mapping[str, Any],
    review_rows: list[Mapping[str, Any]],
    existing_line_ids: set[str],
) -> dict[str, Any]:
    """Validate an XLSX extraction against its authoritative template, no repair."""
    required_metadata = ("legacy_snapshot_sha256", "canonical_state_sha256", "planner_version", "candidate_set_sha256")
    if any(workbook_metadata.get(key) != template.get(key) for key in required_metadata):
        raise ProductionLineReviewWorkspaceError("B6I workbook provenance metadata does not match its template")
    template_items = {item["candidate_key"]: item for item in template.get("items", [])}
    if len(template_items) != len(template.get("items", [])):
        raise ProductionLineReviewWorkspaceError("B6I template has duplicate candidate_key")
    incoming = {item.get("candidate_key"): item for item in review_rows}
    if len(incoming) != len(review_rows) or set(incoming) != set(template_items):
        raise ProductionLineReviewWorkspaceError("B6I workbook candidate set was altered")
    output_items: list[dict[str, Any]] = []
    immutable = ("source_site_legacy_id", "canonical_site_id", "canonical_line_text")
    for candidate_key, original in template_items.items():
        row = incoming[candidate_key]
        if any(row.get(field) != original.get(field) for field in immutable):
            raise ProductionLineReviewWorkspaceError("B6I workbook changed immutable candidate evidence")
        reviewed = deepcopy(original)
        for field in ("review_decision", "approved_display_code", "existing_production_line_id", "review_reason", "reviewer", "reviewed_at"):
            reviewed[field] = row.get(field)
        validate_review_decision(reviewed, existing_line_ids=existing_line_ids)
        reviewed["review_status"] = PENDING_DECISION if reviewed["review_decision"] == PENDING_DECISION else "REVIEWED"
        output_items.append(reviewed)
    output_items.sort(key=lambda item: item["review_order"])
    result = {key: template[key] for key in (
        "schema_version", "artifact_kind", "generated_at", "planner_version", "legacy_snapshot_sha256", "canonical_state_sha256", "candidate_set_sha256"
    )}
    result["items"] = output_items
    result["content_sha256"] = sha256(canonical_artifact_bytes(result)).hexdigest()
    return result


def build_review_summary(
    roster: Mapping[str, Any],
    *,
    certificate_mismatch_report: Mapping[str, Any] | None = None,
    cross_site_report: Mapping[str, Any] | None = None,
) -> str:
    items = roster["items"]
    tags = Counter(tag for item in items for tag in item["review_tags"])
    batches = Counter(item["primary_review_batch"] for item in items)
    decisions = Counter(item["review_decision"] for item in items)
    selected_tags = (
        "CASE_AND_CERTIFICATE_AGREE",
        "CASE_ONLY",
        "MULTIPLE_CASES",
        "MULTIPLE_CERTIFICATES",
        "SINGLE_CASE_SINGLE_CERTIFICATE",
    )
    mismatch_counts = Counter(
        record["review_classification"]
        for record in (certificate_mismatch_report or {}).get("records", [])
    )
    cross_site_records = (cross_site_report or {}).get("records", [])
    return "\n".join([
        "# ProductionLine Physical Identity Review Summary V2",
        "",
        "Review priority is not physical identity confidence and authorizes no database write.",
        "",
        f"- Total candidates: {len(items)}",
        f"- Pending: {decisions[PENDING_DECISION]}",
        f"- Reviewed: {len(items) - decisions[PENDING_DECISION]}",
        f"- Multi-source high-information: {batches['A_MULTI_SOURCE_HIGH_INFORMATION']}",
        f"- Case-only: {batches['B_CASE_ONLY']}",
        f"- Special exceptions: {batches['C_SPECIAL_EXCEPTION']}",
        f"- Low-information: {batches['D_LOW_INFORMATION']}",
        *[f"- {key}: {tags[key]}" for key in selected_tags],
        f"- Cross-site groups: {len(cross_site_records)}",
        f"- Cross-site candidate count: {sum(len(record['candidate_keys']) for record in cross_site_records)}",
        f"- Certificate Site mismatch records: {sum(mismatch_counts.values())}",
        *[f"- Certificate Site mismatch {key}: {mismatch_counts[key]}" for key in sorted(mismatch_counts)],
        "",
        "Universal descriptive tags, such as LETTER_ONLY when universal, are intentionally excluded from priority counts.",
        "",
    ])


def build_certificate_site_mismatch_report(workspace: Mapping[str, Any], canonical_state: Mapping[str, Any]) -> dict[str, Any]:
    plan = workspace["plan"]
    cases = {item["legacy_inspection_id"]: item for item in canonical_state["cases"]}
    certificates = {item["legacy_certificate_id"]: item for item in canonical_state["certificates"]}
    records = []
    for record in plan["certificate_linkage"]["records"]:
        if record["classification"] != "BLOCKED_SITE_MISMATCH":
            continue
        certificate = certificates.get(record["legacy_certificate_id"])
        source_case_id = next((item["source_inspection_legacy_id"] for item in source_line_evidence_from_workspace(workspace)[1] if item["legacy_certificate_id"] == record["legacy_certificate_id"]), None)
        case = cases.get(source_case_id)
        records.append({
            "legacy_certificate_id": record["legacy_certificate_id"],
            "canonical_certificate_id": None if certificate is None else certificate["id"],
            "legacy_inspection_id": source_case_id,
            "canonical_case_id": None if case is None else case["id"],
            "certificate_canonical_site_id": None if certificate is None else certificate["site_id"],
            "case_canonical_site_id": None if case is None else case["site_id"],
            "line_code_raw": record["source_line_text_raw"],
            "source_evidence": record["source_ref"],
            "planner_block_reason": record["block_reason"],
            "review_classification": "INSUFFICIENT_EVIDENCE",
        })
    return {"schema_version": REVIEW_SCHEMA_VERSION, "artifact_kind": "production_line_certificate_site_mismatch_review", "input": {key: workspace["roster"][key] for key in ("legacy_snapshot_sha256", "canonical_state_sha256", "planner_version", "candidate_set_sha256")}, "records": sorted(records, key=lambda item: item["legacy_certificate_id"])}


def source_line_evidence_from_workspace(workspace: Mapping[str, Any]) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    """Workspace retains only compact evidence; callers must use the plan's source IDs."""
    # This small bridge deliberately avoids embedding raw snapshot payload in review JSON.
    evidence = workspace.get("source_evidence")
    if not isinstance(evidence, tuple) or len(evidence) != 2:
        raise ProductionLineReviewWorkspaceError("B6I workspace does not retain source evidence for reporting")
    return evidence


def build_cross_site_text_report(roster: Mapping[str, Any]) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in roster["items"]:
        grouped[item["canonical_line_text"]].append(item)
    records = [{
        "canonical_line_text": text,
        "candidate_keys": [item["candidate_key"] for item in sorted(items, key=lambda item: item["candidate_key"])],
        "source_site_legacy_ids": sorted({item["source_site_legacy_id"] for item in items}),
        "canonical_site_ids": sorted({item["canonical_site_id"] for item in items}),
        "classification": "SEPARATE_SITE_SCOPED_CANDIDATES",
    } for text, items in grouped.items() if len({item["source_site_legacy_id"] for item in items}) > 1]
    return {"schema_version": REVIEW_SCHEMA_VERSION, "artifact_kind": "production_line_cross_site_text_review", "input": {key: roster[key] for key in ("legacy_snapshot_sha256", "canonical_state_sha256", "planner_version", "candidate_set_sha256")}, "records": sorted(records, key=lambda item: item["canonical_line_text"])}
