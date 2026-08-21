from tools.phase3h_external_evidence import (
    build_approved_overrides,
    build_queue_lookup,
    infer_override_field,
    merge_overrides,
    validate_decision,
)


def test_infer_override_field_maps_missing_case_fk():
    row = {"reason": "missing_case_fk"}
    assert infer_override_field(row) == "case_legacy_id"


def test_validate_decision_rejects_candidate_outside_queue():
    queue_rows = [
        {
            "review_key": "db.cc:67",
            "source_sheet": "db.cc",
            "legacy_row_id": "67",
            "override_field": "case_legacy_id",
            "candidate_legacy_ids": [64, 65, 66],
        }
    ]
    queue_lookup = build_queue_lookup(queue_rows)
    decision = {
        "review_key": "db.cc:67",
        "decision": "approve_override",
        "selected_legacy_id": 99,
        "evidence_source": "synology_doc",
        "evidence_reference": r"2021\(ID-008)\(KT-2021-GMP)\110-CN-QLD.docx",
        "decision_rationale": "Certificate chronology reviewed.",
        "reviewer": "qa.lead",
        "reviewed_on": "2026-08-13",
    }
    errors = validate_decision(decision, queue_lookup)
    assert any("not in candidate_legacy_ids" in error for error in errors)


def test_validate_decision_requires_evidence_for_non_defer_actions():
    queue_rows = [
        {
            "review_key": "db.dkkd:704",
            "source_sheet": "db.dkkd",
            "legacy_row_id": "704",
            "override_field": "site_legacy_id",
            "candidate_legacy_ids": [],
        }
    ]
    queue_lookup = build_queue_lookup(queue_rows)
    decision = {
        "review_key": "db.dkkd:704",
        "decision": "exclude_legacy_row",
        "selected_legacy_id": None,
        "evidence_source": "",
        "evidence_reference": "",
        "decision_rationale": "",
        "reviewer": "",
        "reviewed_on": "",
    }
    errors = validate_decision(decision, queue_lookup)
    assert len(errors) == 5


def test_build_approved_overrides_and_merge_with_baseline():
    queue_rows = [
        {
            "review_key": "db.cc:67",
            "source_sheet": "db.cc",
            "legacy_row_id": "67",
            "override_field": "case_legacy_id",
            "candidate_legacy_ids": [64, 65, 66],
        }
    ]
    queue_lookup = build_queue_lookup(queue_rows)
    decisions = [
        {
            "review_key": "db.cc:67",
            "decision": "approve_override",
            "selected_legacy_id": 65,
        }
    ]
    approved = build_approved_overrides(decisions, queue_lookup)
    merged = merge_overrides({"db.Tdoi": {"187": {"site_legacy_id": 85}}}, approved)
    assert approved == {"db.cc": {"67": {"case_legacy_id": 65}}}
    assert merged["db.cc"]["67"]["case_legacy_id"] == 65
    assert merged["db.Tdoi"]["187"]["site_legacy_id"] == 85
