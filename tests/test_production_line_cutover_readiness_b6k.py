from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

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
        "case_count": 1, "certificate_count": 1,
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
        "candidate_set_roster_sha256": sha256(canonical_artifact_bytes(roster)).hexdigest(),
        "candidate_set_roster_content_sha256": roster["content_sha256"],
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


def replan_for_review(plan, roster):
    """Rebind a decision-bearing B6I roster, as B6J planner would."""
    plan["candidate_set_roster_sha256"] = sha256(canonical_artifact_bytes(roster)).hexdigest()
    plan["candidate_set_roster_content_sha256"] = roster["content_sha256"]
    plan["plan_sha256"] = plan_digest(plan)


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
    replan_for_review(plan, roster)
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
    replan_for_review(plan, roster)
    # Existing physical identity is immutable roster provenance. Reject
    # the contradiction before interpreting this as a review blocker.
    with pytest.raises(B6KReviewAlignmentError, match="reviewed roster binding invalid"):
        audit_b6j_review_alignment(plan, roster)
    item["existing_production_line_id"] = c["existing_production_line_id"]
    reseal(roster)
    replan_for_review(plan, roster)
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
    roster_path.write_bytes(canonical_artifact_bytes(roster))
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
    replan_for_review(plan, roster)
    plan_path, roster_path, report_path = (tmp_path / x for x in ("plan.json", "roster.json", "report.json"))
    plan_path.write_text(json.dumps(plan))
    roster_path.write_bytes(canonical_artifact_bytes(roster))
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
    replan_for_review(plan, roster)
    if field == "existing_production_line_id":
        # Never reinterpret a changed source physical identity as valid
        # review; the planner binding rejects it before the decision check.
        with pytest.raises(B6KReviewAlignmentError, match="reviewed roster binding invalid"):
            audit_b6j_review_alignment(plan, roster)
    else:
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


@pytest.mark.parametrize("overwrite", ("plan", "roster"))
def test_cli_never_overwrites_approved_input_artifact(tmp_path, capsys, overwrite):
    plan, roster = fixture()
    plan_path = tmp_path / "plan.json"
    roster_path = tmp_path / "roster.json"
    plan_path.write_text(json.dumps(plan))
    roster_path.write_bytes(canonical_artifact_bytes(roster))
    before_plan, before_roster = plan_path.read_bytes(), roster_path.read_bytes()
    report_path = plan_path if overwrite == "plan" else roster_path
    args = [
        "--plan", str(plan_path), "--reviewed-roster", str(roster_path),
        "--expected-plan-file-sha256", sha256(before_plan).hexdigest(),
        "--expected-reviewed-roster-file-sha256", sha256(before_roster).hexdigest(),
        "--output", str(report_path),
    ]
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
    assert "must differ from both immutable input artifacts" in capsys.readouterr().err
    assert plan_path.read_bytes() == before_plan
    assert roster_path.read_bytes() == before_roster


@pytest.mark.parametrize(
    ("source_classification", "block_reason", "expected"),
    [
        ("BLOCKED_SITE_MISMATCH", "CASE_CERTIFICATE_SITE_DIFFERS", "BLOCKED_SOURCE_ACTION"),
        ("NOT_APPLICABLE", "UNREVIEWED_NOOP", "UNEXPECTED_CANDIDATE_NOOP"),
        ("UNCLASSIFIED", "UNKNOWN_STATE", "UNKNOWN_SOURCE_ACTION"),
    ],
)
def test_approved_candidate_cannot_hide_blocked_source_action(
    source_classification, block_reason, expected,
):
    plan, roster = fixture()
    # Keep an eligible Case link to create the new line; the Certificate
    # still belongs to the same reviewer-approved candidate.
    action = plan["certificate_links"][0]
    action.update(classification=source_classification, block_reason=block_reason)
    plan["summary_counts"]["certificates"] = {source_classification: 1}
    plan["plan_sha256"] = plan_digest(plan)
    _validate_plan(plan)
    report = audit_b6j_review_alignment(plan, roster)
    assert report["status"] == "REVIEW_ALIGNMENT_BLOCKED"
    assert report["blocked_candidate_count"] == 0
    assert report["blocked_source_action_count"] == 1
    assert report["source_action_findings"][0]["source_type"] == "CERTIFICATE"
    assert report["source_action_findings"][0]["legacy_id"] == 20
    assert expected in report["source_action_findings"][0]["blockers"]


def test_already_linked_noop_is_not_falsely_reported_as_source_blocker():
    plan, roster = fixture()
    # In genuine B6J state, an already-linked source belongs to an
    # existing ProductionLine. Another missing Case FK can still be linked.
    candidate = plan["candidates"][0]
    target = "22222222-2222-4222-8222-222222222222"
    candidate["classification"] = "MAP_TO_EXISTING_PRODUCTION_LINE"
    candidate["proposed_production_line_id"] = None
    candidate["existing_production_line_id"] = target
    case = plan["case_links"][0]
    case["classification"] = "LINK_TO_EXISTING_LINE"
    case["planned_production_line_id"] = target
    plan["certificate_links"][0].update(
        classification="NOT_APPLICABLE",
        block_reason="ALREADY_LINKED_TO_PLANNED_LINE",
        expected_production_line_id=target,
        planned_production_line_id=target,
    )
    plan["summary_counts"]["candidates"] = {"MAP_TO_EXISTING_PRODUCTION_LINE": 1}
    plan["summary_counts"]["cases"] = {"LINK_TO_EXISTING_LINE": 1}
    plan["summary_counts"]["certificates"] = {"NOT_APPLICABLE": 1}
    plan["plan_sha256"] = plan_digest(plan)
    _validate_plan(plan)
    item = roster["items"][0]
    item.update(
        review_decision="MAP_TO_EXISTING_PRODUCTION_LINE",
        approved_display_code=None,
        existing_production_line_id=target,
    )
    reseal(roster)
    replan_for_review(plan, roster)
    report = audit_b6j_review_alignment(plan, roster)
    assert report["status"] == "REVIEW_ALIGNMENT_PASS"
    assert report["blocked_source_action_count"] == 0
    assert report["source_action_findings"] == []


def test_unbound_source_blocker_must_be_reported_without_inventing_candidate():
    plan, roster = fixture()
    plan["certificate_links"].append({
        "legacy_id": 21, "candidate_key": None,
        "classification": "BLOCKED_NO_LINE",
        "block_reason": "LINE_BLANK",
        "canonical_record_id": None,
        "canonical_line_code": None,
    })
    plan["summary_counts"]["certificates"] = {
        "LINK_TO_NEW_LINE": 1, "BLOCKED_NO_LINE": 1,
    }
    plan["plan_sha256"] = plan_digest(plan)
    _validate_plan(plan)
    report = audit_b6j_review_alignment(plan, roster)
    assert report["status"] == "REVIEW_ALIGNMENT_BLOCKED"
    assert report["source_action_findings"][0]["candidate_key"] is None
    assert report["source_action_findings"][0]["legacy_id"] == 21


def test_source_only_blocker_causes_cli_exit_three_with_preserved_report(tmp_path):
    plan, roster = fixture()
    plan["certificate_links"][0].update(
        classification="BLOCKED_SITE_MISMATCH",
        block_reason="CASE_CERTIFICATE_SITE_DIFFERS",
    )
    plan["summary_counts"]["certificates"] = {"BLOCKED_SITE_MISMATCH": 1}
    plan["plan_sha256"] = plan_digest(plan)
    plan_path = tmp_path / "plan.json"
    roster_path = tmp_path / "roster.json"
    report_path = tmp_path / "report.json"
    plan_path.write_text(json.dumps(plan))
    roster_path.write_bytes(canonical_artifact_bytes(roster))
    args = [
        "--plan", str(plan_path), "--reviewed-roster", str(roster_path),
        "--expected-plan-file-sha256", sha256(plan_path.read_bytes()).hexdigest(),
        "--expected-reviewed-roster-file-sha256", sha256(roster_path.read_bytes()).hexdigest(),
        "--output", str(report_path),
    ]
    assert main(args) == 3
    report = json.loads(report_path.read_text())
    assert report["status"] == "REVIEW_ALIGNMENT_BLOCKED"
    assert report["blocked_candidate_count"] == 0
    assert report["blocked_source_action_count"] == 1
    assert report["cutover_authorized"] is False


def test_resealed_noop_label_cannot_hide_missing_prior_production_line_fk():
    plan, roster = fixture()
    record = plan["certificate_links"][0]
    record["classification"] = "NOT_APPLICABLE"
    record["block_reason"] = "ALREADY_LINKED_TO_PLANNED_LINE"
    # expected_production_line_id is still None, unlike a true linked no-op.
    plan["summary_counts"]["certificates"] = {"NOT_APPLICABLE": 1}
    plan["plan_sha256"] = plan_digest(plan)
    _validate_plan(plan)
    report = audit_b6j_review_alignment(plan, roster)
    assert report["status"] == "REVIEW_ALIGNMENT_BLOCKED"
    assert "NOOP_TARGET_NOT_PRELINKED" in report["source_action_findings"][0]["blockers"]


def test_unknown_unbound_source_classification_is_not_silently_accepted():
    plan, roster = fixture()
    plan["certificate_links"].append({
        "legacy_id": 21, "candidate_key": None, "classification": "UNKNOWN",
        "canonical_record_id": None,
    })
    plan["summary_counts"]["certificates"] = {"LINK_TO_NEW_LINE": 1, "UNKNOWN": 1}
    plan["plan_sha256"] = plan_digest(plan)
    _validate_plan(plan)
    report = audit_b6j_review_alignment(plan, roster)
    assert report["status"] == "REVIEW_ALIGNMENT_BLOCKED"
    assert report["source_action_findings"][0]["candidate_key"] is None
    assert "UNKNOWN_SOURCE_ACTION" in report["source_action_findings"][0]["blockers"]


def test_missing_linked_canonical_owner_is_a_review_blocker():
    plan, roster = fixture()
    plan["certificate_links"][0]["canonical_record_id"] = None
    plan["plan_sha256"] = plan_digest(plan)
    _validate_plan(plan)
    report = audit_b6j_review_alignment(plan, roster)
    assert report["status"] == "REVIEW_ALIGNMENT_BLOCKED"
    assert "LINK_MISSING_CANONICAL_OWNER" in report["source_action_findings"][0]["blockers"]


def test_new_review_version_requires_replanned_b6j_artifact():
    plan, roster = fixture()
    roster["items"][0]["reviewer"] = "Second reviewer"
    reseal(roster)
    with pytest.raises(B6KReviewAlignmentError, match="replan required"):
        audit_b6j_review_alignment(plan, roster)
    replan_for_review(plan, roster)
    assert audit_b6j_review_alignment(plan, roster)["status"] == "REVIEW_ALIGNMENT_PASS"


def test_cli_refuses_identical_review_content_with_different_file_bytes(tmp_path, capsys):
    plan, roster = fixture()
    plan_path, roster_path, output_path = (tmp_path / x for x in ("plan.json", "roster.json", "audit.json"))
    plan_path.write_text(json.dumps(plan))
    roster_path.write_text(json.dumps(roster, sort_keys=True, indent=2))
    assert sha256(roster_path.read_bytes()).hexdigest() != plan["candidate_set_roster_sha256"]
    args = [
        "--plan", str(plan_path), "--reviewed-roster", str(roster_path),
        "--expected-plan-file-sha256", sha256(plan_path.read_bytes()).hexdigest(),
        "--expected-reviewed-roster-file-sha256", sha256(roster_path.read_bytes()).hexdigest(),
        "--output", str(output_path),
    ]
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
    assert "plan-bound roster" in capsys.readouterr().err
    assert not output_path.exists()


def test_audit_cli_executes_from_external_working_directory_without_pythonpath(tmp_path):
    script = Path(__file__).resolve().parents[1] / "tools" / "audit_production_line_cutover_readiness_b6k.py"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path, env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--reviewed-roster" in result.stdout


@pytest.mark.parametrize(
    ("plan_field", "wrong_value"),
    [
        ("candidate_set_roster_schema_version", "obsolete-review-schema"),
        ("candidate_set_roster_artifact_kind", "not-a-review-roster"),
        ("candidate_set_roster_planner_version", "obsolete-planner"),
        ("candidate_set_roster_item_count", 999),
    ],
)
def test_plan_cannot_reseal_inconsistent_review_roster_metadata(
    plan_field, wrong_value,
):
    plan, roster = fixture()
    plan[plan_field] = wrong_value
    plan["plan_sha256"] = plan_digest(plan)
    # These metadata fields were copied by B6J planner, but its structural
    # validator alone cannot compare them with the actual review input.
    if plan_field != "candidate_set_roster_item_count":
        _validate_plan(plan)
    with pytest.raises(B6KReviewAlignmentError, match="B6K"):
        audit_b6j_review_alignment(plan, roster)


def test_cli_prints_both_candidate_and_source_action_blocker_counts(tmp_path, capsys):
    plan, roster = fixture()
    plan["certificate_links"][0].update(
        classification="BLOCKED_SITE_MISMATCH",
        block_reason="CASE_CERTIFICATE_SITE_DIFFERS",
    )
    plan["summary_counts"]["certificates"] = {"BLOCKED_SITE_MISMATCH": 1}
    plan["plan_sha256"] = plan_digest(plan)
    plan_path = tmp_path / "plan.json"
    roster_path = tmp_path / "roster.json"
    output_path = tmp_path / "review_audit.json"
    plan_path.write_text(json.dumps(plan))
    roster_path.write_bytes(canonical_artifact_bytes(roster))
    args = [
        "--plan", str(plan_path), "--reviewed-roster", str(roster_path),
        "--expected-plan-file-sha256", sha256(plan_path.read_bytes()).hexdigest(),
        "--expected-reviewed-roster-file-sha256", sha256(roster_path.read_bytes()).hexdigest(),
        "--output", str(output_path),
    ]
    assert main(args) == 3
    message = capsys.readouterr().out
    assert "BLOCKED_CANDIDATES=0" in message
    assert "BLOCKED_SOURCE_ACTIONS=1" in message
    assert json.loads(output_path.read_text())["cutover_authorized"] is False


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("case_count", 2),
        ("certificate_count", 0),
        ("existing_production_line_id", "88888888-8888-4888-8888-888888888888"),
        ("source_case_ids", [1234]),
    ],
)
def test_b6k_reuses_complete_planner_roster_evidence_fence(field, bad_value):
    plan, roster = fixture()
    roster["items"][0][field] = bad_value
    reseal(roster)
    replan_for_review(plan, roster)
    # Self-consistent seals alone cannot override the B6J planner's
    # source membership, source counts or physical identity contract.
    with pytest.raises(B6KReviewAlignmentError, match="reviewed roster binding invalid"):
        audit_b6j_review_alignment(plan, roster)


@pytest.mark.parametrize(
    ("source_kind", "reason", "should_block"),
    [
        ("CASE", "CASE_SOURCE_NOT_ELIGIBLE", False),
        ("CASE", "NO_CANONICAL_LINE_TEXT", False),
        ("CERTIFICATE", "NO_CANONICAL_LINE_TEXT", False),
        ("CERTIFICATE", "CASE_SOURCE_NOT_ELIGIBLE", True),
        ("CASE", "CONFLICT_MARKED_AS_NOOP", True),
        ("CERTIFICATE", "CANONICAL_LINK_CONFLICT", True),
    ],
)
def test_unbound_noop_only_accepts_b6j_planner_owned_reasons(
    source_kind, reason, should_block,
):
    plan, roster = fixture()
    field = "case_links" if source_kind == "CASE" else "certificate_links"
    plan[field].append({
        "legacy_id": 99, "candidate_key": None,
        "classification": "NOT_APPLICABLE", "block_reason": reason,
        "canonical_record_id": None, "canonical_line_code": None,
    })
    summary = "cases" if source_kind == "CASE" else "certificates"
    plan["summary_counts"][summary] = {
        "LINK_TO_NEW_LINE": 1, "NOT_APPLICABLE": 1,
    }
    plan["plan_sha256"] = plan_digest(plan)
    _validate_plan(plan)
    report = audit_b6j_review_alignment(plan, roster)
    assert (report["status"] == "REVIEW_ALIGNMENT_BLOCKED") is should_block
    if should_block:
        assert report["blocked_source_action_count"] == 1
        assert "UNEXPECTED_UNBOUND_NOOP" in report["source_action_findings"][0]["blockers"]
    else:
        assert report["blocked_source_action_count"] == 0


@pytest.mark.parametrize("alias", ["previous_report", "hardlinked_plan", "hardlinked_roster"])
def test_cli_never_replaces_existing_report_or_hardlinked_artifact(tmp_path, capsys, alias):
    plan, roster = fixture()
    plan_path = tmp_path / "plan.json"
    roster_path = tmp_path / "roster.json"
    output_path = tmp_path / "report.json"
    plan_path.write_text(json.dumps(plan))
    roster_path.write_bytes(canonical_artifact_bytes(roster))
    before_plan = plan_path.read_bytes()
    before_roster = roster_path.read_bytes()
    if alias == "previous_report":
        output_path.write_text("previous independently reviewed audit report")
        previous_report = output_path.read_bytes()
    else:
        os.link(plan_path if alias == "hardlinked_plan" else roster_path, output_path)
        previous_report = output_path.read_bytes()
    args = [
        "--plan", str(plan_path), "--reviewed-roster", str(roster_path),
        "--expected-plan-file-sha256", sha256(before_plan).hexdigest(),
        "--expected-reviewed-roster-file-sha256", sha256(before_roster).hexdigest(),
        "--output", str(output_path),
    ]
    with pytest.raises(SystemExit) as result:
        main(args)
    assert result.value.code == 2
    assert "output already exists" in capsys.readouterr().err
    assert plan_path.read_bytes() == before_plan
    assert roster_path.read_bytes() == before_roster
    assert output_path.read_bytes() == previous_report


def test_b6k_report_pins_exact_checked_file_digests_without_authorization(tmp_path):
    plan, roster = fixture()
    plan_path = tmp_path / "plan.json"
    roster_path = tmp_path / "roster.json"
    output_path = tmp_path / "report.json"
    plan_path.write_text(json.dumps(plan))
    roster_path.write_bytes(canonical_artifact_bytes(roster))
    expected_plan_hash = sha256(plan_path.read_bytes()).hexdigest()
    expected_roster_hash = sha256(roster_path.read_bytes()).hexdigest()
    args = [
        "--plan", str(plan_path), "--reviewed-roster", str(roster_path),
        "--expected-plan-file-sha256", expected_plan_hash,
        "--expected-reviewed-roster-file-sha256", expected_roster_hash,
        "--output", str(output_path),
    ]
    assert main(args) == 0
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["plan_file_sha256"] == expected_plan_hash
    assert result["reviewed_roster_file_sha256"] == expected_roster_hash
    assert result["status"] == "REVIEW_ALIGNMENT_PASS"
    assert result["cutover_authorized"] is False
