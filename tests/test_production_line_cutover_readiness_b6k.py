from __future__ import annotations

from hashlib import sha256
import json

import pytest

from backend.app.domain.production_line_population import canonical_artifact_bytes
from backend.app.domain.production_line_population_b6j import PLAN_SCHEMA_VERSION, plan_digest
from backend.app.domain.production_line_review_workspace import REVIEW_SCHEMA_VERSION, candidate_set_digest
from backend.app.domain.production_line_cutover_readiness_b6k import B6KReviewAlignmentError, audit_b6j_review_alignment
from tools.audit_production_line_cutover_readiness_b6k import main


def fixture():
    key, site = "legacy-line:sample", "11111111-1111-4111-8111-111111111111"
    row = {
        "candidate_key": key, "source_site_legacy_id": 7,
        "canonical_site_id": site, "canonical_line_text": "A",
        "source_case_ids": [10], "source_certificate_ids": [20],
        "review_tags": [], "review_status": "REVIEWED",
        "review_decision": "APPROVE_NEW_PHYSICAL_LINE", "review_reason": "Evidence",
        "approved_display_code": "A", "existing_production_line_id": None,
        "reviewer": "Reviewer", "reviewed_at": "2026-10-09",
    }
    roster = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "artifact_kind": "production_line_physical_identity_review_roster",
        "legacy_snapshot_sha256": "a" * 64, "canonical_state_sha256": "b" * 64,
        "candidate_set_sha256": candidate_set_digest([row]), "items": [row],
    }
    reseal(roster)
    candidate = {
        "candidate_key": key, "legacy_site_id": 7,
        "canonical_site_id": site, "canonical_line_code": "A",
        "source_case_ids": [10], "source_certificate_ids": [20],
        "classification": "CREATE_NEW_PRODUCTION_LINE",
        "proposed_display_code": "A",
    }
    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "legacy_snapshot_sha256": "a" * 64, "canonical_state_sha256": "b" * 64,
        "candidate_set_sha256": roster["candidate_set_sha256"],
        "candidates": [candidate],
    }
    plan["plan_sha256"] = plan_digest(plan)
    return plan, roster


def reseal(roster):
    payload = dict(roster)
    payload.pop("content_sha256", None)
    roster["content_sha256"] = sha256(canonical_artifact_bytes(payload)).hexdigest()


def test_review_aligned_does_not_authorize_apply():
    plan, roster = fixture()
    result = audit_b6j_review_alignment(plan, roster)
    assert result["status"] == "REVIEW_ALIGNMENT_PASS"
    assert result["cutover_authorized"] is False


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("review_decision", "PENDING_HUMAN_REVIEW", "NEW_LINE_NOT_APPROVED"),
        ("review_decision", "REJECT_NOT_PHYSICAL_LINE", "NEW_LINE_NOT_APPROVED"),
        ("review_decision", "DEFER_INSUFFICIENT_EVIDENCE", "NEW_LINE_NOT_APPROVED"),
        ("review_status", "PENDING_HUMAN_REVIEW", "REVIEW_NOT_COMPLETED"),
        ("reviewer", "", "MISSING_REVIEWER"),
        ("reviewed_at", None, "MISSING_REVIEWED_AT"),
        ("approved_display_code", "B", "APPROVED_DISPLAY_CODE_DIFFERS_FROM_WRITER"),
    ],
)
def test_incomplete_review_creates_blocker(field, value, reason):
    plan, roster = fixture()
    roster["items"][0][field] = value
    reseal(roster)
    result = audit_b6j_review_alignment(plan, roster)
    assert result["status"] == "REVIEW_ALIGNMENT_BLOCKED"
    assert reason in result["findings"][0]["blockers"]


def test_blocked_plan_candidate_is_not_ready():
    plan, roster = fixture()
    plan["candidates"][0]["classification"] = "BLOCKED_NO_ELIGIBLE_LINK_TARGET"
    plan["plan_sha256"] = plan_digest(plan)
    result = audit_b6j_review_alignment(plan, roster)
    assert "PLAN_CANDIDATE_BLOCKED" in result["findings"][0]["blockers"]


def test_map_existing_requires_exact_reviewed_line_uuid():
    plan, roster = fixture()
    c, item = plan["candidates"][0], roster["items"][0]
    c["classification"] = "MAP_TO_EXISTING_PRODUCTION_LINE"
    c["existing_production_line_id"] = "22222222-2222-4222-8222-222222222222"
    plan["plan_sha256"] = plan_digest(plan)
    item["review_decision"] = "MAP_TO_EXISTING_PRODUCTION_LINE"
    item["approved_display_code"] = None
    item["existing_production_line_id"] = "33333333-3333-4333-8333-333333333333"
    reseal(roster)
    assert "MAPPED_LINE_ID_DIFFERS" in audit_b6j_review_alignment(plan, roster)["findings"][0]["blockers"]
    item["existing_production_line_id"] = c["existing_production_line_id"]
    reseal(roster)
    assert audit_b6j_review_alignment(plan, roster)["status"] == "REVIEW_ALIGNMENT_PASS"


@pytest.mark.parametrize("field", ("canonical_line_text", "source_case_ids"))
def test_source_identity_drift_is_not_a_review_blocker_but_an_error(field):
    plan, roster = fixture()
    roster["items"][0][field] = "OTHER" if field == "canonical_line_text" else [999]
    reseal(roster)
    with pytest.raises(B6KReviewAlignmentError):
        audit_b6j_review_alignment(plan, roster)


def test_roster_seal_and_plan_sha_are_checked():
    plan, roster = fixture()
    roster["items"][0]["reviewer"] = "changed"
    with pytest.raises(B6KReviewAlignmentError, match="content SHA256"):
        audit_b6j_review_alignment(plan, roster)
    plan, roster = fixture()
    plan["candidates"][0]["canonical_line_code"] = "OTHER"
    with pytest.raises(B6KReviewAlignmentError, match="plan seal"):
        audit_b6j_review_alignment(plan, roster)


def test_cli_requires_independent_file_sha_before_any_output(tmp_path, capsys):
    plan, roster = fixture()
    plan_path, roster_path, report_path = (tmp_path / x for x in ("plan.json", "roster.json", "report.json"))
    plan_path.write_text(json.dumps(plan))
    roster_path.write_text(json.dumps(roster))
    args = [
        "--plan", str(plan_path), "--reviewed-roster", str(roster_path),
        "--expected-plan-file-sha256", sha256(plan_path.read_bytes()).hexdigest(),
        "--expected-reviewed-roster-file-sha256", "0" * 64,
        "--output", str(report_path),
    ]
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
    assert "independently approved" in capsys.readouterr().err
    assert not report_path.exists()
    args[args.index("0" * 64)] = sha256(roster_path.read_bytes()).hexdigest()
    assert main(args) == 0
    assert json.loads(report_path.read_text())["cutover_authorized"] is False
