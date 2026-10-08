from __future__ import annotations

from hashlib import sha256
import json

import pytest

from backend.app.domain.production_line_population import canonical_artifact_bytes
from backend.app.domain.production_line_population_b6j import PLAN_SCHEMA_VERSION, plan_digest
from backend.app.domain.production_line_population_writer_b6j import _validate_plan
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
    candidate["existing_production_line_id"] = None
    candidate["proposed_production_line_id"] = "33333333-3333-4333-8333-333333333333"
    roster["planner_version"] = "b6h-production-line-population/v2"
    reseal(roster)
    def link(identity, owner):
        return {
            "legacy_id": identity, "candidate_key": key,
            "canonical_record_id": owner, "classification": "LINK_TO_NEW_LINE",
            "canonical_line_code": "A", "expected_site_id": site,
            "expected_production_line_id": None,
            "planned_production_line_id": candidate["proposed_production_line_id"],
        }
    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "planner_version": roster["planner_version"],
        "source_alembic_revision": "20260929_0017",
        "source_database_identity": {"database_name": "fixture"},
        "legacy_snapshot_sha256": "a" * 64, "canonical_state_sha256": "b" * 64,
        "candidate_set_sha256": roster["candidate_set_sha256"],
        "candidate_set_roster_sha256": "c" * 64,
        "candidate_set_roster_content_sha256": "d" * 64,
        "candidate_set_roster_schema_version": REVIEW_SCHEMA_VERSION,
        "candidate_set_roster_artifact_kind": roster["artifact_kind"],
        "candidate_set_roster_planner_version": roster["planner_version"],
        "candidate_set_roster_content_sha256_verified": True,
        "candidate_set_roster_item_count": 1,
        "candidates": [candidate],
        "case_links": [link(10, "case-10")],
        "certificate_links": [link(20, "certificate-20")],
        "summary_counts": {
            "candidates": {"CREATE_NEW_PRODUCTION_LINE": 1},
            "cases": {"LINK_TO_NEW_LINE": 1},
            "certificates": {"LINK_TO_NEW_LINE": 1},
        },
        "transformation_actions": [], "scope_actions": [],
        "certificate_relationship_actions": [],
    }
    plan["plan_sha256"] = plan_digest(plan)
    _validate_plan(plan)
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
    plan["candidates"][0]["proposed_production_line_id"] = None
    for group in ("case_links", "certificate_links"):
        for action in plan[group]:
            action["classification"] = "BLOCKED_STALE_STATE"
            action["planned_production_line_id"] = None
        plan["summary_counts"]["cases" if group == "case_links" else "certificates"] = {"BLOCKED_STALE_STATE": 1}
    plan["summary_counts"]["candidates"] = {"BLOCKED_NO_ELIGIBLE_LINK_TARGET": 1}
    plan["plan_sha256"] = plan_digest(plan)
    _validate_plan(plan)
    result = audit_b6j_review_alignment(plan, roster)
    assert "PLAN_CANDIDATE_BLOCKED" in result["findings"][0]["blockers"]


def test_map_existing_requires_exact_reviewed_line_uuid():
    plan, roster = fixture()
    c, item = plan["candidates"][0], roster["items"][0]
    c["classification"] = "MAP_TO_EXISTING_PRODUCTION_LINE"
    c["existing_production_line_id"] = "22222222-2222-4222-8222-222222222222"
    c["proposed_production_line_id"] = None
    for group in ("case_links", "certificate_links"):
        for action in plan[group]:
            action["classification"] = "LINK_TO_EXISTING_LINE"
            action["planned_production_line_id"] = c["existing_production_line_id"]
        plan["summary_counts"]["cases" if group == "case_links" else "certificates"] = {"LINK_TO_EXISTING_LINE": 1}
    plan["summary_counts"]["candidates"] = {"MAP_TO_EXISTING_PRODUCTION_LINE": 1}
    plan["plan_sha256"] = plan_digest(plan)
    _validate_plan(plan)
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


def test_cli_writes_blocker_report_and_returns_nonzero(tmp_path):
    plan, roster = fixture()
    roster["items"][0]["review_decision"] = "DEFER_INSUFFICIENT_EVIDENCE"
    reseal(roster)
    plan_path, roster_path, report_path = (tmp_path / x for x in ("plan.json", "roster.json", "report.json"))
    plan_path.write_text(json.dumps(plan))
    roster_path.write_text(json.dumps(roster))
    args = [
        "--plan", str(plan_path), "--reviewed-roster", str(roster_path),
        "--expected-plan-file-sha256", sha256(plan_path.read_bytes()).hexdigest(),
        "--expected-reviewed-roster-file-sha256", sha256(roster_path.read_bytes()).hexdigest(),
        "--output", str(report_path),
    ]
    assert main(args) == 3
    report = json.loads(report_path.read_text())
    assert report["status"] == "REVIEW_ALIGNMENT_BLOCKED"
    assert report["cutover_authorized"] is False
    assert "NEW_LINE_NOT_APPROVED" in report["findings"][0]["blockers"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("existing_production_line_id", "44444444-4444-4444-8444-444444444444"),
        ("approved_display_code", None),
    ],
)
def test_review_approval_with_contradictory_payload_does_not_pass(field, value):
    plan, roster = fixture()
    roster["items"][0][field] = value
    if field == "approved_display_code":
        plan["candidates"][0]["proposed_display_code"] = None
        plan["plan_sha256"] = plan_digest(plan)
        _validate_plan(plan)
    reseal(roster)
    report = audit_b6j_review_alignment(plan, roster)
    assert report["status"] == "REVIEW_ALIGNMENT_BLOCKED"
    assert "INVALID_B6I_DECISION_PAYLOAD" in report["findings"][0]["blockers"]


@pytest.mark.parametrize("change", ["roster_claim", "planner", "plan_roster_count", "plan_source_omission"])
def test_invalid_b6i_b6j_provenance_cannot_be_reported_as_review_pass(change):
    plan, roster = fixture()
    if change == "roster_claim":
        roster["candidate_set_sha256"] = "f" * 64
        reseal(roster)
    elif change == "planner":
        roster["planner_version"] = "other"
        reseal(roster)
    elif change == "plan_roster_count":
        plan["candidate_set_roster_item_count"] = 2
        plan["plan_sha256"] = plan_digest(plan)
    else:
        plan["case_links"] = []
        plan["summary_counts"]["cases"] = {}
        plan["plan_sha256"] = plan_digest(plan)
    with pytest.raises(B6KReviewAlignmentError):
        audit_b6j_review_alignment(plan, roster)
