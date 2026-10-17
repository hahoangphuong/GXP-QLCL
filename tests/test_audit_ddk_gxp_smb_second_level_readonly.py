"""Metadata-only direct child inventory with strict depth and budgets."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from tools.audit_ddk_gxp_smb_second_level_readonly import (
    DdkSecondLevelBlocked, summarize_second_level,
)


@dataclass
class Entry:
    name: str
    path: str = "fixture"
    folder: bool = True
    def is_dir(self):
        return self.folder


def targets():
    return [{"parent_id": str(i), "site_legacy_id": i + 10} for i in range(8)]


def test_only_immediate_subdirectories_aggregate_metadata_without_leaking_paths():
    entries = [Entry("Alpha", "secret/root/Alpha"), Entry("Beta", "secret/root/Beta"),
               Entry("readme", "secret/root/readme", False)]
    seen = []
    children = {
        "secret/root/Alpha": [
            Entry("Site X (10)", "secret/root/Alpha/Site X (10)"),
            Entry("Site Y (ID-11)", "secret/root/Alpha/Site Y (ID-11)"),
            Entry("file.pdf", "secret/root/Alpha/file.pdf", False),
        ],
        "secret/root/Beta": [
            Entry("Site X again (10)", "secret/root/Beta/Site X again (10)"),
            Entry("(12)", "secret/root/Beta/(12)"),
        ],
    }
    def scan(path):
        seen.append(path)
        return children[path]
    direct, counts = summarize_second_level(entries, targets(), scan)
    assert seen == ["secret/root/Alpha", "secret/root/Beta"]
    assert direct["direct_child_directories"] == 2
    assert direct["files_or_other_direct_entries"] == 1
    assert counts["second_level_directories"] == 4
    assert counts["second_level_files_or_other"] == 1
    assert counts["distinct_site_keys_with_multiple_second_level_name_matches"] == 1
    assert counts["distinct_site_keys_without_second_level_name_match"] == 7
    assert counts["ddk_parents_with_any_second_level_name_match"] == 1
    assert "secret/" not in str(counts)
    assert "Site X" not in str(counts)


def test_total_nested_budget_fails_closed_not_partial_inventory():
    entries = [Entry("Alpha", "secret/root/Alpha")]
    def scan(path):
        return (Entry(f"child-{i}", path + f"/child-{i}") for i in range(4))
    with pytest.raises(DdkSecondLevelBlocked, match="budget"):
        summarize_second_level(entries, targets(), scan, nested_budget=2)


def test_root_parent_budget_blocks_before_nested_scan():
    entries = [Entry("Alpha", "root/a"), Entry("Beta", "root/b")]
    with pytest.raises(DdkSecondLevelBlocked, match="parent"):
        summarize_second_level(entries, targets(),
                               lambda path: pytest.fail("Should never traverse"),
                               parent_budget=1)


def test_root_entry_budget_fails_closed():
    entries = [Entry(f"parent{i}", f"root/p{i}") for i in range(3)]
    with pytest.raises(DdkSecondLevelBlocked, match="Root"):
        summarize_second_level(entries, targets(),
                               lambda path: pytest.fail("Should never traverse"),
                               root_budget=2)
