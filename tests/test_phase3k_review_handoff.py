from tools.phase3k_review_handoff import (
    build_evidence_checklist,
    build_reviewer_prompt,
    review_batch_label,
)


def test_review_batch_label_assigns_hard_unresolved_to_batch_3():
    row = {"classification": "hard_unresolved", "candidate_count": 0}
    assert review_batch_label(row) == "B3-hard-unresolved"


def test_review_batch_label_assigns_small_candidate_rows_to_batch_1():
    row = {"classification": "needs_external_evidence", "candidate_count": 3}
    assert review_batch_label(row) == "B1-high-confidence-adjudication"


def test_build_reviewer_prompt_mentions_certificate_for_db_cc():
    row = {
        "source_sheet": "db.cc",
        "legacy_context": {
            "site_name": "Test Site",
            "certificate_number": "123/CN",
        },
    }
    prompt = build_reviewer_prompt(row)
    assert "Test Site" in prompt
    assert "123/CN" in prompt


def test_build_evidence_checklist_varies_by_source_sheet():
    cc_row = {"source_sheet": "db.cc"}
    dkkd_row = {"source_sheet": "db.dkkd"}
    assert any("certificate" in item.lower() for item in build_evidence_checklist(cc_row))
    assert any("business eligibility" in item.lower() for item in build_evidence_checklist(dkkd_row))
