"""Reject forged storage adapter entry identity in a read-only staging audit."""
from dataclasses import replace

import pytest

from backend.app.storage.staging import audit_staging_candidates, new_staging_name
from backend.app.storage.types import StorageEntry


@pytest.mark.parametrize("forgery", [
    "outside_parent", "wrong_leaf", "traversal", "nested_name",
    "bool_size", "negative_size", "non_bool_dir",
])
def test_staging_audit_blocks_forged_entry_provenance(tmp_path, forgery):
    name = new_staging_name()
    legitimate = StorageEntry(relative_path=name, name=name, is_dir=False, size=7)
    if forgery == "outside_parent":
        child = replace(legitimate, relative_path="other/" + name)
    elif forgery == "wrong_leaf":
        child = replace(legitimate, name="different.txt")
    elif forgery == "traversal":
        child = replace(legitimate, relative_path="../" + name)
    elif forgery == "nested_name":
        child = replace(legitimate, name="../" + name)
    elif forgery == "bool_size":
        child = replace(legitimate, size=True)
    elif forgery == "negative_size":
        child = replace(legitimate, size=-1)
    else:
        child = replace(legitimate, is_dir=1)

    class ForgedAdapter:
        def iter_entries_for_audit(self, relative_path="", *, root="inspection"):
            yield child

    report = audit_staging_candidates(ForgedAdapter())
    assert report.truncated is True
    assert report.incomplete_reason == "storage_access_failed"
    assert report.failed_root == "inspection"
    assert report.failed_relative_path == ""
    assert report.candidates == ()
    assert report.scanned_entries == 0
    assert report.root_coverage[0].status == "partial"


def test_staging_audit_detects_wrong_child_scope_after_directory_descent():
    folder = "2026"
    name = new_staging_name()

    class ForgedAdapter:
        def iter_entries_for_audit(self, relative_path="", *, root="inspection"):
            if not relative_path:
                yield StorageEntry(folder, folder, True, None)
            else:
                yield StorageEntry("2025/" + name, name, False, 9)

    report = audit_staging_candidates(ForgedAdapter())
    assert report.truncated is True
    assert report.incomplete_reason == "storage_access_failed"
    assert report.failed_relative_path == folder
    assert report.scanned_directories == 1
    assert report.candidates == ()
    assert report.root_coverage[0].status == "partial"
