from tools.phase3j_decision_quality_gate import (
    parse_reviewed_on,
    validate_decision_quality,
)
from tools.phase3h_external_evidence import build_queue_lookup


def test_parse_reviewed_on_accepts_iso_date():
    parsed = parse_reviewed_on("2026-08-13")
    assert parsed is not None
    assert parsed.isoformat() == "2026-08-13"


def test_validate_decision_quality_rejects_future_review_date():
    queue_rows = [
        {
            "review_key": "db.cc:67",
            "source_sheet": "db.cc",
            "legacy_row_id": "67",
            "override_field": "case_legacy_id",
            "candidate_legacy_ids": [64, 65],
            "candidate_count": 2,
        }
    ]
    queue_lookup = build_queue_lookup(queue_rows)
    decision = {
        "review_key": "db.cc:67",
        "decision": "approve_override",
        "selected_legacy_id": 64,
        "evidence_source": "synology_doc",
        "evidence_reference": r"2021\(ID-008)\(KT-2021-GMP)\110-CN-QLD.docx",
        "decision_rationale": "Reviewed chronology and matching certificate output.",
        "reviewer": "qa.lead",
        "reviewed_on": "2026-08-14",
    }
    errors = validate_decision_quality(decision, queue_lookup)
    assert any("cannot be in the future" in error for error in errors)


def test_validate_decision_quality_blocks_approve_without_candidates():
    queue_rows = [
        {
            "review_key": "db.dkkd:704",
            "source_sheet": "db.dkkd",
            "legacy_row_id": "704",
            "override_field": "site_legacy_id",
            "candidate_legacy_ids": [],
            "candidate_count": 0,
        }
    ]
    queue_lookup = build_queue_lookup(queue_rows)
    decision = {
        "review_key": "db.dkkd:704",
        "decision": "approve_override",
        "selected_legacy_id": 85,
        "evidence_source": "legacy_register",
        "evidence_reference": "legacy-register-row-704",
        "decision_rationale": "Manual registry review linked the site identity.",
        "reviewer": "qa.lead",
        "reviewed_on": "2026-08-13",
    }
    errors = validate_decision_quality(decision, queue_lookup)
    assert any("candidate_count is 0" in error for error in errors)


def test_validate_decision_quality_requires_defer_audit_fields():
    queue_rows = [
        {
            "review_key": "db.cc:98",
            "source_sheet": "db.cc",
            "legacy_row_id": "98",
            "override_field": "case_legacy_id",
            "candidate_legacy_ids": [92, 93],
            "candidate_count": 2,
        }
    ]
    queue_lookup = build_queue_lookup(queue_rows)
    decision = {
        "review_key": "db.cc:98",
        "decision": "defer",
        "selected_legacy_id": None,
        "evidence_source": "",
        "evidence_reference": "",
        "decision_rationale": "",
        "reviewer": "",
        "reviewed_on": "",
    }
    errors = validate_decision_quality(decision, queue_lookup)
    assert any("decision_rationale is required for defer" in error for error in errors)
    assert any("reviewer is required for defer" in error for error in errors)
