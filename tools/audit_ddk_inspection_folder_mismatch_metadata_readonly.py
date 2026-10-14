"""Bounded Synology metadata-only witness for one *source-mismatched* Case folder.

The original Case owner stays fixed to the physical db.ktra Site.
A directory using another Site of the same company is NOT a valid binding.
This module enumerates exactly the known source-year root and the immediate
children of exactly ONE code+alternate-Site folder. It never reads binaries,
recurses, changes a folder, changes a Case or creates a canonical link.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from backend.app.storage.smb import SmbStorageService, smbclient, smbpath
from backend.app.storage.types import matches_inspection_identity

SCHEMA = "GXP_DDK_SINGLE_MISMATCHED_INSPECTION_FOLDER_METADATA_READONLY_V1"


class MismatchedFolderAuditBlocked(ValueError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise MismatchedFolderAuditBlocked(reason)


def classify_exact_folder_metadata_readonly(
    storage: SmbStorageService,
    *,
    source_year: int,
    source_site_legacy_id: int,
    observed_other_site_legacy_id: int,
    inspection_legacy_code: str,
    max_year_root_entries: int = 3000,
    max_direct_child_entries: int = 1000,
) -> dict[str, Any]:
    """Inspect metadata, NOT files, in the one existing code-only directory.

    Caller first verifies original queue, dual-year and marker-report
    provenance, physical workbook request hash, and distinct Site identity.
    Unexpected new matching folders or cardinality changes STOP the audit.
    No child directory is entered; follow-up evidence needs separate approval.
    """
    _require(
        isinstance(storage, SmbStorageService)
        and isinstance(storage.inspection_root, str)
        and bool(storage.inspection_root)
        and smbclient is not None and smbpath is not None,
        "Expected approved direct inspection SMB adapter",
    )
    _require(
        type(source_year) is int and 1900 <= source_year <= 2100
        and type(source_site_legacy_id) is int and source_site_legacy_id > 0
        and type(observed_other_site_legacy_id) is int and observed_other_site_legacy_id > 0
        and source_site_legacy_id != observed_other_site_legacy_id
        and isinstance(inspection_legacy_code, str)
        and bool(inspection_legacy_code.strip())
        and type(max_year_root_entries) is int and 1 <= max_year_root_entries <= 3000
        and type(max_direct_child_entries) is int and 1 <= max_direct_child_entries <= 1000,
        "Invalid source-identity/bounded-audit inputs",
    )
    root = storage._join_root(storage.inspection_root, str(source_year))
    _require(bool(smbpath.exists(root)) and bool(smbpath.isdir(root)),
             "Known source-year directory no longer accessible")
    code_token = "(" + inspection_legacy_code.strip().lower() + ")"
    source_site_token = "(id-" + str(source_site_legacy_id) + ")"
    other_site_token = "(id-" + str(observed_other_site_legacy_id) + ")"
    code_folders = []
    year_entries = 0
    for entry in smbclient.scandir(root):
        year_entries += 1
        _require(year_entries <= max_year_root_entries, "Year root budget exceeded")
        if entry.is_dir() and code_token in entry.name.lower():
            code_folders.append(entry)
            _require(len(code_folders) <= 1,
                     "Previous unique code-only folder population changed")
    _require(len(code_folders) == 1,
             "Previous unique code-only folder missing or changed")
    folder = code_folders[0]
    name = folder.name.lower()
    _require(
        source_site_token not in name
        and other_site_token in name
        and not matches_inspection_identity(
            folder.name, site_legacy_id=source_site_legacy_id,
            inspection_legacy_code=inspection_legacy_code,
        )
        and matches_inspection_identity(
            folder.name, site_legacy_id=observed_other_site_legacy_id,
            inspection_legacy_code=inspection_legacy_code,
        ),
        "Previously observed mismatched Site token changed",
    )
    _require(bool(smbpath.isdir(folder.path)),
             "Previous code-only folder no longer a directory")
    children: list[dict[str, Any]] = []
    summary = Counter()
    extension_counts = Counter()
    for entry in smbclient.scandir(folder.path):
        _require(len(children) < max_direct_child_entries,
                 "Direct child metadata budget exceeded")
        is_dir = bool(entry.is_dir())
        lower = entry.name.lower()
        site_source = source_site_token in lower
        site_other = other_site_token in lower
        code_present = code_token in lower
        suffix = ""
        if not is_dir:
            tail = entry.name.rsplit(".", 1)
            if len(tail) == 2 and len(tail[1]) <= 12:
                suffix = "." + tail[1].lower()
        if is_dir:
            summary["DIRECT_CHILD_DIRS"] += 1
        else:
            summary["DIRECT_CHILD_FILES"] += 1
            extension_counts[suffix or "(none)"] += 1
        if code_present:
            summary["CHILD_NAMES_WITH_INSPECTION_CODE"] += 1
        if site_source:
            summary["CHILD_NAMES_WITH_SOURCE_SITE_TOKEN"] += 1
        if site_other:
            summary["CHILD_NAMES_WITH_ALTERNATE_SITE_TOKEN"] += 1
        children.append({
            "name_private": entry.name,
            "is_dir": is_dir,
            "extension_private": suffix,
            "inspection_code_token_present": code_present,
            "source_site_token_present": site_source,
            "alternate_site_token_present": site_other,
        })
    _require(
        summary["DIRECT_CHILD_DIRS"] + summary["DIRECT_CHILD_FILES"] == len(children),
        "Incomplete child metadata accounting",
    )
    return {
        "schema": SCHEMA,
        "status": "SINGLE_SOURCE_MISMATCHED_FOLDER_DIRECT_METADATA_ONLY",
        "approval_status": "NOT_APPROVED",
        "source_year_roots_checked": 1,
        "source_year_root_entries_scanned": year_entries,
        "code_matching_folders_checked": 1,
        "direct_child_entries_checked": len(children),
        "counts": dict(sorted(summary.items())),
        "folder_content_ownership_verified": False,
        "file_binary_contents_read": False,
        "direct_child_subdirectories_entered": False,
        "database_connected": False,
        "database_writes": 0,
        "storage_writes": 0,
        "canonical_links_created": 0,
        "private_folder_metadata": {
            "folder_leaf": folder.name,
            "source_year": source_year,
            "source_site_legacy_id": source_site_legacy_id,
            "observed_other_site_legacy_id": observed_other_site_legacy_id,
            "inspection_legacy_code": inspection_legacy_code,
            "children": children,
            "extension_counts": dict(sorted(extension_counts.items())),
        },
    }
