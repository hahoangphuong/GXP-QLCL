"""Fail-closed root shape diagnosis is metadata-only and source-identity bound."""
from __future__ import annotations

from dataclasses import dataclass
import pytest

from tools.audit_ddk_gxp_smb_readonly_root_shape import (
    RootShapeBlocked, summarize_root_direct_children,
    validate_source_and_full_report,
)


@dataclass
class FakeEntry:
    name: str
    directory: bool = True
    def is_dir(self):
        return self.directory


def test_aggregate_root_shape_without_leaking_names_or_ids():
    ids = list(range(20, 28))
    summary = summarize_root_direct_children([
        FakeEntry("Alpha (20)"),
        FakeEntry("Legacy(ID-21)"),
        FakeEntry("Other(999)"),
        FakeEntry("random archive"),
        FakeEntry("original.pdf", False),
    ], ids)
    assert summary == {
        "direct_child_directories": 4,
        "direct_entries": 5,
        "files_or_other_direct_entries": 1,
        "folders_with_legacy_numeric_token_shape": 1,
        "folders_with_numeric_parentheses_but_no_legacy_space_token": 1,
        "folders_without_numeric_parenthesis_token": 2,
        "target_sites_with_multiple_name_matches": 0,
        "target_sites_with_one_name_match": 1,
        "target_sites_with_zero_name_matches": 7,
    }
    assert "Alpha" not in str(summary)
    assert "original.pdf" not in str(summary)


def test_budget_blocks_before_reporting_partial_absence():
    entries = (FakeEntry("any") for _ in range(4))
    with pytest.raises(RootShapeBlocked):
        summarize_root_direct_children(entries, list(range(1, 9)), max_entries=2)


def test_source_original_report_must_match_all_distinct_dkk_targets():
    ddks = [{"parent_id": str(n), "site_legacy_id": n + 100} for n in range(8)]
    queue = {
        "source_token_reviews": [],
        "ddk_company_reviews": [],
    }
    readiness = {}
    full = {
        "schema": "GXP_DDK_SMB_READONLY_FOLDER_IDENTITY_PILOT_V1",
        "status": "SMB_FOLDER_IDENTITY_OBSERVATIONS_UNVERIFIED",
        "approval_status": "NOT_APPROVED",
        "adapter_class": "synology_smb",
        "total_ddk_targets": 8, "total_case_targets": 6,
        "ddk_lookups_attempted": 8, "case_lookups_attempted": 6,
        "ddk_not_probed": 0, "case_not_probed": 0,
        "database_connected": False, "database_writes": 0,
        "storage_writes": 0, "storage_file_contents_accessed": False,
        "canonical_links_created": 0,
        "counts": {"DDK_NOT_FOUND": 8, "CASE_RESOLVED": 2, "CASE_NOT_FOUND": 4},
        "private_folder_observations": [],
    }
    with pytest.raises((RootShapeBlocked, KeyError, TypeError)):
        validate_source_and_full_report(queue, readiness, full)
