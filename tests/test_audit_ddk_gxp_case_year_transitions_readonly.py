"""Original and dual-year source-key transitions are read-only, identity guarded."""
from __future__ import annotations

from copy import deepcopy

import pytest

from tools.audit_ddk_gxp_case_year_transitions_readonly import (
    CaseTransitionBlocked, compare_private_case_observations,
)
import tools.audit_ddk_gxp_case_year_transitions_readonly as owner


def records():
    cases = [{"parent_id": f"case-{i}", "site_legacy_id": i + 100,
              "inspection_legacy_code": f"KT-{i}", "year": 2023}
             for i in range(6)]
    def original(i):
        status = "resolved" if i < 2 else "not_found"
        return {
            "parent_type": "ORIGINATING_CASE", "parent_id": f"case-{i}",
            "status": status, "candidate_count": int(i < 2),
            "relative_path_private_unverified": f"2023/Match-{i}" if i < 2 else None,
            "lookup_input": {
                "site_legacy_id": i + 100,
                "inspection_legacy_code": f"KT-{i}",
                "source_year": 2023,
            },
            "legal_approval": "NOT_APPROVED",
        }
    old_rows = [original(i) for i in range(6)]
    new_rows = []
    for i, row in enumerate(old_rows):
        dual_observations = [{
            "source_year": 2023, "status": row["status"],
            "candidate_count": row["candidate_count"],
            "relative_path_private_unverified": row["relative_path_private_unverified"],
            "provenance": ["submission"],
        }]
        if i in (0, 2, 4):
            dual_observations.append({
                "source_year": 2026,
                "status": "resolved" if i == 2 else "not_found",
                "candidate_count": 1 if i == 2 else 0,
                "relative_path_private_unverified": "2026/Found" if i == 2 else None,
                "provenance": ["inspection"],
            })
        new_rows.append({
            "originating_case_id": row["parent_id"],
            "final_status": "RESOLVED" if i in (0, 1, 2) else "NOT_FOUND",
            "legal_approval": "NOT_APPROVED",
            "year_specific_observations": dual_observations,
        })
    old = {
        "schema": "GXP_DDK_SMB_READONLY_FOLDER_IDENTITY_PILOT_V1",
        "status": "SMB_FOLDER_IDENTITY_OBSERVATIONS_UNVERIFIED",
        "approval_status": "NOT_APPROVED", "adapter_class": "synology_smb",
        "case_lookups_attempted": 6, "case_not_probed": 0,
        "total_case_targets": 6,
        "database_connected": False, "database_writes": 0,
        "storage_writes": 0, "storage_file_contents_accessed": False,
        "canonical_links_created": 0,
        "counts": {"DDK_NOT_FOUND": 8, "CASE_RESOLVED": 2, "CASE_NOT_FOUND": 4},
        "private_folder_observations": old_rows,
    }
    dual = {
        "schema": "GXP_DDK_CASE_DUAL_SOURCE_YEAR_SMB_READONLY_V1",
        "status": "BOTH_ORIGINAL_SOURCE_YEARS_CHECKED_NO_APPROVAL",
        "approval_status": "NOT_APPROVED",
        "storage_adapter": "synology_smb", "case_parents_checked": 6,
        "year_specific_lookups": 9, "database_access": "REHEARSAL_READ_ONLY",
        "database_writes": 0, "storage_writes": 0, "storage_binaries_read": False,
        "canonical_links_created": 0,
        "readiness_sha256": "abc", "counts": {
            "CASE_RESOLVED": 3, "CASE_NOT_FOUND": 3,
            "CASE_WITH_TWO_DISTINCT_SOURCE_YEARS": 3,
        },
        "private_case_observations": new_rows,
    }
    return cases, old, dual


def compare(monkeypatch, old=None, dual=None):
    cases, original, updated = records()
    monkeypatch.setattr(owner, "verified_lookup_targets",
                        lambda queue, readiness: (
                            [{"parent_id": str(i), "site_legacy_id": i} for i in range(8)],
                            cases,
                        ))
    return compare_private_case_observations(
        original if old is None else old,
        updated if dual is None else dual,
        {}, {}, "abc",
    )


def test_transition_exact_3_2_1_and_no_private_identifiers(monkeypatch):
    report = compare(monkeypatch)
    assert report["transitions"] == {
        "NOT_FOUND_TO_NOT_FOUND": 3,
        "NOT_FOUND_TO_RESOLVED": 1,
        "RESOLVED_TO_RESOLVED": 2,
    }
    assert report["year_specific_observations_checked"] == 9
    assert report["case_parents_compared"] == 6
    assert "case-" not in str(report) and "2026/Found" not in str(report)


def test_private_original_year_evidence_drift_blocks(monkeypatch):
    _, _, dual = records()
    dual["private_case_observations"][0]["year_specific_observations"][0]["candidate_count"] = 2
    with pytest.raises(CaseTransitionBlocked, match="drifted"):
        compare(monkeypatch, dual=dual)


def test_previous_resolved_case_regression_blocks(monkeypatch):
    _, _, dual = records()
    dual["private_case_observations"][0]["year_specific_observations"][0]["status"] = "not_found"
    dual["private_case_observations"][0]["year_specific_observations"][0]["candidate_count"] = 0
    dual["private_case_observations"][0]["year_specific_observations"][0]["relative_path_private_unverified"] = None
    dual["private_case_observations"][0]["final_status"] = "NOT_FOUND"
    with pytest.raises(CaseTransitionBlocked):
        compare(monkeypatch, dual=dual)


def test_private_input_missing_console_only_readiness_hash_is_acceptable(monkeypatch):
    _, old, dual = records()
    assert "readiness_report_sha256" not in old
    report = compare(monkeypatch, old=old, dual=dual)
    assert report["original_year_observation_drift"] == 0


def test_wrong_readiness_digest_blocks(monkeypatch):
    _, old, dual = records()
    dual["readiness_sha256"] = "other"
    with pytest.raises(CaseTransitionBlocked, match="sourced"):
        compare(monkeypatch, old=old, dual=dual)
