"""Bounded metadata-only Inspection folder mismatch audit regression."""
from types import SimpleNamespace

import pytest

from backend.app.storage.smb import SmbStorageService
import tools.audit_ddk_inspection_folder_mismatch_metadata_readonly as owner


FOLDER = "Different site (ID-46) inspection (KT-1023-GMP)"
ROOT = "mock/year/2024"


def _fixture(monkeypatch, *, folders=None, children=None):
    def entry(name, path, is_dir=True):
        return SimpleNamespace(name=name, path=path, is_dir=lambda: is_dir)

    service = object.__new__(SmbStorageService)
    service.inspection_root = "mock/year"
    year_entries = [
        entry(name, ROOT + "/" + name)
        for name in (folders if folders is not None else [FOLDER, "unrelated"])
    ]
    child_entries = [
        entry(name, ROOT + "/" + FOLDER + "/" + name, is_dir)
        for name, is_dir in (
            children if children is not None else [
                ("inspection note (KT-1023-GMP).pdf", False),
                ("other (ID-46).docx", False),
                ("evidence", True),
                ("record without token.txt", False),
            ]
        )
    ]

    def scan(path):
        if path == ROOT:
            return iter(year_entries)
        if path == ROOT + "/" + FOLDER:
            return iter(child_entries)
        raise AssertionError("Attempted unapproved root/deep recursion")

    monkeypatch.setattr(service, "_join_root",
                        lambda root, year: ROOT if root == "mock/year" and year == "2024"
                        else (_ for _ in ()).throw(AssertionError("Unexpected source year")))
    monkeypatch.setattr(owner, "smbclient", SimpleNamespace(scandir=scan))
    monkeypatch.setattr(owner, "smbpath", SimpleNamespace(
        exists=lambda path: path == ROOT,
        isdir=lambda path: path in {ROOT, ROOT + "/" + FOLDER},
    ))
    return service


def _probe(storage, **extra):
    return owner.classify_exact_folder_metadata_readonly(
        storage,
        source_year=2024,
        source_site_legacy_id=298,
        observed_other_site_legacy_id=46,
        inspection_legacy_code="KT-1023-GMP",
        **extra,
    )


def test_direct_children_metadata_no_content_or_unapproved_link(monkeypatch):
    storage = _fixture(monkeypatch)
    result = _probe(storage)
    assert result["schema"] == owner.SCHEMA
    assert result["source_year_roots_checked"] == 1
    assert result["source_year_root_entries_scanned"] == 2
    assert result["code_matching_folders_checked"] == 1
    assert result["direct_child_entries_checked"] == 4
    assert result["counts"] == {
        "CHILD_NAMES_WITH_ALTERNATE_SITE_TOKEN": 1,
        "CHILD_NAMES_WITH_INSPECTION_CODE": 1,
        "DIRECT_CHILD_DIRS": 1,
        "DIRECT_CHILD_FILES": 3,
    }
    assert result["private_folder_metadata"]["extension_counts"] == {
        ".docx": 1, ".pdf": 1, ".txt": 1,
    }
    public = {key: val for key, val in result.items()
              if not key.startswith("private_")}
    assert "46" not in str(public)
    assert "298" not in str(public)
    assert "1023" not in str(public)
    assert "evidence" not in str(public)
    assert result["file_binary_contents_read"] is False
    assert result["direct_child_subdirectories_entered"] is False
    assert result["folder_content_ownership_verified"] is False
    assert result["database_writes"] == 0
    assert result["storage_writes"] == 0
    assert result["canonical_links_created"] == 0
    assert result["approval_status"] == "NOT_APPROVED"


@pytest.mark.parametrize("folders", [
    [],
    ["unrelated"],
    [FOLDER, "Second (ID-46) (KT-1023-GMP)"],
    ["Wrong Site (ID-298) (KT-1023-GMP)"],
    ["Two Sites (ID-46) (ID-88) (KT-1023-GMP)"],
    ["Corrupted (ID-047) (KT-1023-GMP)"],
])
def test_changed_source_folder_population_fails_closed(monkeypatch, folders):
    storage = _fixture(monkeypatch, folders=folders)
    with pytest.raises(owner.MismatchedFolderAuditBlocked):
        _probe(storage)


def test_direct_child_over_budget_rejected_without_partial_report(monkeypatch):
    storage = _fixture(monkeypatch)
    with pytest.raises(owner.MismatchedFolderAuditBlocked):
        _probe(storage, max_direct_child_entries=3)


def test_year_root_over_budget_rejected(monkeypatch):
    storage = _fixture(monkeypatch)
    with pytest.raises(owner.MismatchedFolderAuditBlocked):
        _probe(storage, max_year_root_entries=1)


def test_rejects_source_site_equal_observed_site(monkeypatch):
    storage = _fixture(monkeypatch)
    with pytest.raises(owner.MismatchedFolderAuditBlocked):
        owner.classify_exact_folder_metadata_readonly(
            storage, source_year=2024, source_site_legacy_id=46,
            observed_other_site_legacy_id=46,
            inspection_legacy_code="KT-1023-GMP",
        )


def test_no_child_directory_descent_even_when_present(monkeypatch):
    storage = _fixture(monkeypatch, children=[("deep folder", True)])
    result = _probe(storage)
    assert result["direct_child_entries_checked"] == 1
    assert result["counts"]["DIRECT_CHILD_DIRS"] == 1
    assert result["direct_child_subdirectories_entered"] is False
