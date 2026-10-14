"""Manual review queue must never produce a canonical Certificate approval."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tools.build_ddk_gxp_manual_review_queue import build_review_queue, main, QueueBlocked


def _private_dossier():
    def token(ref, ddk, row, legacy, flags):
        return {
            "source_reference_id": ref, "legacy_dkkd_id": ddk,
            "source_row_number": row, "source_group": "GMP",
            "id_cc_excel_column": 15, "token_index": 1,
            "parsed_legacy_certificate_id": legacy,
            "flags": flags,
            "link_approval": "NOT_APPROVED",
            "review_status": "REQUIRES_INDEPENDENT_ADJUDICATION",
            "original_source": {
                "id_cc_raw": str(legacy),
                "certificate_scope_raw": "Sensitive original source",
            },
            "ddk_site_id": "site-a", "certificate_site_id": "site-b",
            "certificate_case_id": "case-1",
            "case_site_id": "site-a",
            "certificate_versions": [{
                "certificate_version_id": "v1", "scope_evidence": [
                    {"scope_text_sha256": "f" * 64}
                ], "lifecycle_state": None,
            }],
        }
    return {
        "schema": "GXP_DDK_IDCC_EXCEPTION_EVIDENCE_DOSSIER_V1",
        "status": "READ_ONLY_EXCEPTION_EVIDENCE_NOT_APPROVED",
        "approval_status": "NOT_APPROVED",
        "source_workbook_sha256": "a" * 64,
        "source_tokens_checked": 3,
        "distinct_observed_certificate_legacy_ids": 2,
        "candidate_repeated_id_count": 1,
        "repeated_candidate_extra_occurrences": 1,
        "within_one_source_cell_repeat_extras": 0,
        "candidate_ids_observed_in_multiple_ddk": 1,
        "cross_site_occurrences": 1,
        "ddk_site_company_mismatches": 1,
        "recorded_canonical_link_rows_before": 0,
        "database_writes": 0,
        "canonical_links_created": 0,
        "other_case_site_or_type_observations": {
            "CERTIFICATE_CASE_SITE_DIFFERENT": 1,
        },
        "exception_token_details": [
            token("t-1", 10, 100, 20,
                  ["CERTIFICATE_SITE_DIFFERENT", "CERTIFICATE_CASE_SITE_DIFFERENT"]),
            token("t-2", 11, 101, 20, ["DDK_SITE_COMPANY_MISMATCH"]),
        ],
        "ddk_company_exception_details": [{
            "legacy_dkkd_id": 11, "source_row_numbers": [101],
            "ddk_site_id": "site-x", "ddk_company_id": "company-a",
            "site_owning_company_id": "company-b", "link_approval": "NOT_APPROVED",
        }],
        "repeated_candidate_id_details": [{
            "parsed_legacy_certificate_id": 20, "link_approval": "NOT_APPROVED",
            "occurrence_count": 2,
            "distinct_source_ddk_count": 2, "observed_in_multiple_ddk": True,
            "observations": [
                {"source_reference_id": "t-1", "legacy_dkkd_id": 10,
                 "parsed_legacy_certificate_id": 20, "source_row_number": 100,
                 "source_group": "GMP", "id_cc_excel_column": 15},
                {"source_reference_id": "t-2", "legacy_dkkd_id": 11,
                 "parsed_legacy_certificate_id": 20, "source_row_number": 101,
                 "source_group": "GMP", "id_cc_excel_column": 15},
            ],
        }],
    }


def test_queue_stays_source_only_dedups_overlapping_flags_not_token_positions():
    dossier = _private_dossier()
    queue = build_review_queue(dossier)
    assert queue["status"] == "PRIVATE_REVIEW_ONLY_NOT_APPROVED"
    assert queue["source_tokens_checked"] == 3
    assert queue["source_exception_token_records"] == 2
    assert queue["site_or_case_exception_token_records"] == 1
    assert queue["ddk_company_review_records"] == 1
    assert queue["cross_site_only"] == 0
    assert queue["case_site_only"] == 0
    assert queue["both_site_and_case_flags"] == 1
    assert [r["review_key"] for r in queue["source_token_reviews"]] == [
        "SOURCE_TOKEN:t-1", "SOURCE_TOKEN:t-2",
    ]
    assert len(queue["source_token_reviews"][0]["required_independent_evidence_checks"]) == 2
    assert queue["source_token_reviews"][1]["original_exception_evidence"]["original_source"]["certificate_scope_raw"] == "Sensitive original source"
    assert queue["source_token_reviews"][0]["observed_reference_frequency"]["distinct_source_ddk_count"] == 2
    assert queue["source_token_reviews"][0]["original_exception_evidence"]["certificate_versions"][0]["lifecycle_state"] is None
    assert all(x["link_approval"] == "NOT_APPROVED" for x in queue["source_token_reviews"])
    assert queue["canonical_links_created"] == queue["database_writes"] == 0
    assert "Sensitive original source" in json.dumps(queue)
    assert queue["link_approval"] == "NOT_APPROVED"


def test_cli_writes_only_to_same_private_folder_mode_0600(tmp_path, capsys):
    source = tmp_path / "dossier.json"
    out = tmp_path / "manual-queue.json"
    source.write_text(json.dumps(_private_dossier()), encoding="utf-8")
    source.chmod(0o600)
    assert main(["--dossier-json", str(source), "--queue-json", str(out)]) == 0
    assert out.stat().st_mode & 0o777 == 0o600
    assert json.loads(out.read_text(encoding="utf-8"))["source_exception_token_records"] == 2
    console = capsys.readouterr().out
    assert "Sensitive original source" not in console
    assert "legacy_dkkd_id" not in console
    assert "t-1" not in console
    assert "input_dossier_sha256" in console
    assert main(["--dossier-json", str(source), "--queue-json", str(out)]) == 2


@pytest.mark.parametrize("corruption", ["approved", "lost_ref", "changed_cross", "repeats", "duplicate"])
def test_fails_closed_on_dossier_tamper(corruption):
    dossier = _private_dossier()
    if corruption == "approved":
        dossier["approval_status"] = "APPROVED"
    elif corruption == "lost_ref":
        dossier["exception_token_details"].pop(0)  # must conserve reported Site flag
    elif corruption == "changed_cross":
        dossier["cross_site_occurrences"] = 2
    elif corruption == "repeats":
        dossier["repeated_candidate_extra_occurrences"] = 2
    else:
        dossier["exception_token_details"][1]["source_reference_id"] = "t-1"
    with pytest.raises(ValueError):
        build_review_queue(dossier)
