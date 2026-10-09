"""Read-only B6K evidence alignment; never authorizes a B6J apply."""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from backend.app.domain.production_line_population_b6j import (
    PLAN_SCHEMA_VERSION,
    ProductionLinePopulationPlanError,
    bind_candidate_roster,
    plan_digest,
)
from backend.app.domain.production_line_population_writer_b6j import (
    ProductionLinePopulationApplyError,
    _validate_plan,
)
from backend.app.domain.production_line_review_workspace import (
    ProductionLineReviewWorkspaceError,
    validate_review_decision,
)


class B6KReviewAlignmentError(ValueError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise B6KReviewAlignmentError(reason)


def audit_b6j_review_alignment(plan: Mapping[str, Any], roster: Mapping[str, Any]) -> dict[str, Any]:
    """Compare immutable identities and explicit human decisions without repair."""
    require(plan.get("schema_version") == PLAN_SCHEMA_VERSION
            and plan.get("plan_sha256") == plan_digest(plan), "B6K plan seal invalid")
    # Reuse the authoritative B6J structural validator. A self-resealed
    # orphan, missing action or altered source count is not a review-ready plan.
    try:
        _validate_plan(plan)
    except ProductionLinePopulationApplyError as exc:
        raise B6KReviewAlignmentError(f"B6K B6J plan structure invalid: {exc}") from exc
    # Candidate-set SHA omits human decisions, source membership counts and
    # existing physical-line identity. Recheck the *entire* B6J planner
    # roster-binding contract, rather than maintaining a partial copy.
    require(
        plan.get("candidate_set_roster_content_sha256") == roster.get("content_sha256"),
        "B6K reviewed roster decision content differs from plan; replan required",
    )
    try:
        provenance = bind_candidate_roster(
            roster,
            roster_raw_sha256=plan.get("candidate_set_roster_sha256"),
            candidate_set_sha256=plan.get("candidate_set_sha256"),
            snapshot_sha256=plan.get("legacy_snapshot_sha256"),
            canonical_state_sha256=plan.get("canonical_state_sha256"),
            candidates=plan["candidates"],
        )
    except ProductionLinePopulationPlanError as exc:
        raise B6KReviewAlignmentError(
            f"B6K B6J reviewed roster binding invalid: {exc}"
        ) from exc
    for field, value in provenance.items():
        require(
            plan.get(field) == value,
            f"B6K plan-bound {field} differs from reviewed roster",
        )
    seal = roster["content_sha256"]
    ri = {item["candidate_key"]: item for item in roster["items"]}
    pi = {candidate["candidate_key"]: candidate for candidate in plan["candidates"]}
    # B6I reviews are not implicitly authenticated by their "REVIEWED" flag.
    # Reuse the B6I decision contract to reject contradictory decision payloads.
    permitted_existing_line_ids = {
        candidate["existing_production_line_id"] for candidate in pi.values()
        if isinstance(candidate.get("existing_production_line_id"), str)
        and candidate["existing_production_line_id"]
    }
    findings = []
    for key in sorted(pi):
        c, item = pi[key], ri[key]
        classification, decision = c.get("classification"), item.get("review_decision")
        reasons = []
        try:
            validate_review_decision(item, existing_line_ids=permitted_existing_line_ids)
        except ProductionLineReviewWorkspaceError:
            reasons.append("INVALID_B6I_DECISION_PAYLOAD")
        if item.get("review_status") != "REVIEWED":
            reasons.append("REVIEW_NOT_COMPLETED")
        for field in ("review_reason", "reviewer", "reviewed_at"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                reasons.append("MISSING_" + field.upper())
        if classification == "CREATE_NEW_PRODUCTION_LINE":
            if decision != "APPROVE_NEW_PHYSICAL_LINE":
                reasons.append("NEW_LINE_NOT_APPROVED")
            if item.get("approved_display_code") != c.get("proposed_display_code"):
                reasons.append("APPROVED_DISPLAY_CODE_DIFFERS_FROM_WRITER")
        elif classification == "MAP_TO_EXISTING_PRODUCTION_LINE":
            if decision != "MAP_TO_EXISTING_PRODUCTION_LINE":
                reasons.append("EXISTING_LINE_NOT_APPROVED")
            if item.get("existing_production_line_id") != c.get("existing_production_line_id"):
                reasons.append("MAPPED_LINE_ID_DIFFERS")
        else:
            reasons.append("PLAN_CANDIDATE_BLOCKED")
        if reasons:
            findings.append({"candidate_key": key, "plan_classification": classification,
                             "review_decision": decision, "blockers": sorted(set(reasons))})
    # A reviewed candidate can still have blocked Cases/Certificates.
    # Source-level readiness is distinct from physical-identity approval.
    # Do not reclassify planner actions or infer approvals from review text.
    source_action_findings = []
    accepted_links = {"LINK_TO_NEW_LINE", "LINK_TO_EXISTING_LINE"}
    for kind, field in (("CASE", "case_links"), ("CERTIFICATE", "certificate_links")):
        for action in plan[field]:
            classification = action["classification"]
            candidate_key = action.get("candidate_key")
            reasons = []
            if isinstance(classification, str) and classification.startswith("BLOCKED_"):
                reasons.append("BLOCKED_SOURCE_ACTION")
            elif candidate_key is not None and classification == "NOT_APPLICABLE":
                if action.get("block_reason") != "ALREADY_LINKED_TO_PLANNED_LINE":
                    reasons.append("UNEXPECTED_CANDIDATE_NOOP")
                else:
                    candidate = pi[candidate_key]
                    target = (
                        candidate.get("proposed_production_line_id")
                        or candidate.get("existing_production_line_id")
                    )
                    if target is None or action.get("expected_production_line_id") != target:
                        reasons.append("NOOP_TARGET_NOT_PRELINKED")
            elif classification not in accepted_links and classification != "NOT_APPLICABLE":
                reasons.append("UNKNOWN_SOURCE_ACTION")
            if classification in accepted_links and not action.get("canonical_record_id"):
                reasons.append("LINK_MISSING_CANONICAL_OWNER")
            if reasons:
                source_action_findings.append({
                    "source_type": kind,
                    "legacy_id": action["legacy_id"],
                    "candidate_key": candidate_key,
                    "classification": classification,
                    "block_reason": action.get("block_reason"),
                    "blockers": sorted(set(reasons)),
                })
    source_action_findings.sort(key=lambda item: (item["source_type"], item["legacy_id"]))
    counts = Counter(
        reason for row in (*findings, *source_action_findings)
        for reason in row["blockers"]
    )
    return {
        "artifact_kind": "b6k_production_line_review_alignment",
        "schema_version": "b6k-production-line-review-alignment/v1",
        "status": "REVIEW_ALIGNMENT_BLOCKED" if findings or source_action_findings else "REVIEW_ALIGNMENT_PASS",
        "cutover_authorized": False,
        "plan_sha256": plan["plan_sha256"],
        "reviewed_roster_content_sha256": seal,
        "candidate_count": len(pi),
        "blocked_candidate_count": len(findings),
        "blocked_source_action_count": len(source_action_findings),
        "blocker_counts": dict(sorted(counts.items())),
        "findings": findings,
        "source_action_findings": source_action_findings,
    }
