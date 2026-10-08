"""Read-only B6K evidence alignment; never authorizes a B6J apply."""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from typing import Any, Mapping

from backend.app.domain.production_line_population import canonical_artifact_bytes
from backend.app.domain.production_line_population_b6j import PLAN_SCHEMA_VERSION, plan_digest
from backend.app.domain.production_line_review_workspace import REVIEW_SCHEMA_VERSION, candidate_set_digest


class B6KReviewAlignmentError(ValueError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise B6KReviewAlignmentError(reason)


def audit_b6j_review_alignment(plan: Mapping[str, Any], roster: Mapping[str, Any]) -> dict[str, Any]:
    """Compare immutable identities and explicit human decisions without repair."""
    require(plan.get("schema_version") == PLAN_SCHEMA_VERSION
            and plan.get("plan_sha256") == plan_digest(plan), "B6K plan seal invalid")
    require(roster.get("schema_version") == REVIEW_SCHEMA_VERSION
            and roster.get("artifact_kind") == "production_line_physical_identity_review_roster",
            "B6K requires a B6I review roster")
    seal = roster.get("content_sha256")
    unsealed = dict(roster)
    unsealed.pop("content_sha256", None)
    require(isinstance(seal, str)
            and seal == sha256(canonical_artifact_bytes(unsealed)).hexdigest(),
            "B6K reviewed roster content SHA256 invalid")
    for field in ("legacy_snapshot_sha256", "canonical_state_sha256"):
        require(roster.get(field) == plan.get(field), f"B6K source {field} changed")
    items, candidates = roster.get("items"), plan.get("candidates")
    require(isinstance(items, list) and isinstance(candidates, list)
            and all(isinstance(x, Mapping) for x in (*items, *candidates)),
            "B6K candidates must be mappings")
    require(candidate_set_digest(items) == plan.get("candidate_set_sha256"),
            "B6K candidate-set evidence differs")
    ri = {x.get("candidate_key"): x for x in items}
    pi = {x.get("candidate_key"): x for x in candidates}
    require(len(ri) == len(items) == len(pi) == len(candidates)
            and None not in ri and set(ri) == set(pi), "B6K candidate roster universe changed")
    for key, item in ri.items():
        c = pi[key]
        for rfield, pfield in (("source_site_legacy_id", "legacy_site_id"),
                               ("canonical_site_id", "canonical_site_id"),
                               ("canonical_line_text", "canonical_line_code")):
            require(item.get(rfield) == c.get(pfield), f"B6K {key} identity drift")
        for field in ("source_case_ids", "source_certificate_ids"):
            require(isinstance(item.get(field), list) and isinstance(c.get(field), list)
                    and sorted(item[field]) == sorted(c[field]), f"B6K {key} source drift")
    findings = []
    for key in sorted(pi):
        c, item = pi[key], ri[key]
        classification, decision = c.get("classification"), item.get("review_decision")
        reasons = []
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
    counts = Counter(reason for row in findings for reason in row["blockers"])
    return {
        "artifact_kind": "b6k_production_line_review_alignment",
        "schema_version": "b6k-production-line-review-alignment/v1",
        "status": "REVIEW_ALIGNMENT_BLOCKED" if findings else "REVIEW_ALIGNMENT_PASS",
        "cutover_authorized": False,
        "plan_sha256": plan["plan_sha256"],
        "reviewed_roster_content_sha256": seal,
        "candidate_count": len(candidates),
        "blocked_candidate_count": len(findings),
        "blocker_counts": dict(sorted(counts.items())),
        "findings": findings,
    }
