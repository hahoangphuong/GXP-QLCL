"""Private candidate manifest for independent document evidence review.

Purpose: choose a small, deterministic set of *existing* direct-child
file names from a previously verified one-folder SMB metadata report.
NO NAS/DB connections or PDF/Office reads. Names/positions remain private.
This is sampling guidance, never a Case/Certificate association or approval.
"""
from __future__ import annotations

from collections import Counter
import re
import unicodedata
from typing import Any

SCHEMA = "GXP_DDK_INSPECTION_DOCUMENT_EVIDENCE_SAMPLE_MANIFEST_V1"
PRIOR_SCHEMA = "GXP_DDK_SINGLE_MISMATCHED_INSPECTION_FOLDER_METADATA_READONLY_V1"


class DocumentCandidateManifestBlocked(ValueError):
    pass


def _require(value: bool, reason: str) -> None:
    if not value:
        raise DocumentCandidateManifestBlocked(reason)


def _ascii_tokens(value: str) -> str:
    chars = unicodedata.normalize("NFKD", value)
    chars = "".join(c for c in chars if not unicodedata.combining(c))
    chars = chars.replace("đ", "d").replace("Đ", "D")
    return re.sub(r"[^a-z0-9]+", " ", chars.lower()).strip()


# Descriptive filename hints only. Never used to construct/repair legal IDs.
_HINTS = (
    ("INSPECTION_RECORD_HINT", ("bien ban", "kiem tra", "inspection", "bbkt", "audit report")),
    ("DECISION_HINT", ("quyet dinh", "decision", "phe duyet")),
    ("REPORT_HINT", ("bao cao", "report", "ket luan")),
    ("DOSSIER_HINT", ("ho so", "dossier", "application")),
)


def _role(name: str) -> tuple[int, str]:
    normalized = " " + _ascii_tokens(name) + " "
    for priority, (label, words) in enumerate(_HINTS):
        if any(" " + phrase + " " in normalized for phrase in words):
            return priority, label
    return len(_HINTS), "FILENAME_ROLE_UNKNOWN"


def make_private_document_candidate_manifest(
    report: dict[str, Any],
    *,
    max_pdf: int = 3,
    max_word: int = 2,
) -> dict[str, Any]:
    """Validate full 41-child evidence and select <=5 filename-only candidates.

    This returns PRIVATE names. Caller must verify report's immutable SHA,
    trusted path/mode/uid and previously source-bound fields, then create
    output via an exclusive private mode-0600 writer. No binary files read.
    """
    _require(
        report.get("schema") == PRIOR_SCHEMA
        and report.get("status") == "SINGLE_SOURCE_MISMATCHED_FOLDER_DIRECT_METADATA_ONLY"
        and report.get("approval_status") == "NOT_APPROVED"
        and report.get("source_year_roots_checked") == 1
        and report.get("code_matching_folders_checked") == 1
        and report.get("source_year_root_entries_scanned") == 130
        and report.get("direct_child_entries_checked") == 41
        and report.get("counts", {}).get("DIRECT_CHILD_FILES") == 40
        and report.get("counts", {}).get("DIRECT_CHILD_DIRS") == 1
        and report.get("file_binary_contents_read") is False
        and report.get("direct_child_subdirectories_entered") is False
        and report.get("folder_content_ownership_verified") is False
        and report.get("database_connected") is False
        and all(report.get(key) == 0 for key in
                ("database_writes", "storage_writes", "canonical_links_created")),
        "Prior evidence population/contract drifted",
    )
    _require(
        type(max_pdf) is int and 1 <= max_pdf <= 3
        and type(max_word) is int and 1 <= max_word <= 2,
        "Unsafe candidate sample budget",
    )
    m = report.get("private_folder_metadata")
    _require(
        isinstance(m, dict) and isinstance(m.get("children"), list)
        and len(m["children"]) == 41 and isinstance(m.get("folder_leaf"), str)
        and bool(m["folder_leaf"]),
        "Missing private direct-child manifest",
    )
    distinct: set[str] = set()
    all_extensions = Counter()
    candidates: list[dict[str, Any]] = []
    file_count = 0
    dir_count = 0
    for index, child in enumerate(m["children"]):
        _require(
            isinstance(child, dict)
            and isinstance(child.get("name_private"), str)
            and bool(child["name_private"])
            and isinstance(child.get("is_dir"), bool)
            and isinstance(child.get("extension_private"), str)
            and not any(child.get(k) for k in (
                "inspection_code_token_present",
                "source_site_token_present",
                "alternate_site_token_present",
            )),
            "Malformed or newly named child",
        )
        name = child["name_private"]
        _require(
            name not in {".", ".."}
            and "/" not in name and "\\" not in name and "\0" not in name
            and name.casefold() not in distinct,
            "Nonunique or unsafe private direct child name",
        )
        distinct.add(name.casefold())
        if child["is_dir"]:
            dir_count += 1
            continue
        file_count += 1
        suffix = child["extension_private"].lower()
        _require(
            suffix == (("." + name.rsplit(".", 1)[-1].lower())
                       if "." in name and len(name.rsplit(".", 1)[-1]) <= 12
                       else ""),
            "Untrusted extension provenance",
        )
        all_extensions[suffix or "(none)"] += 1
        file_kind = ("PDF" if suffix == ".pdf"
                     else "TEXT_DOCUMENT" if suffix in {".doc", ".docx", ".rtf", ".odt", ".txt"}
                     else "OTHER")
        if file_kind == "OTHER":
            continue
        priority, hint = _role(name)
        candidates.append({
            "direct_child_index_private": index,
            "filename_private": name,
            "extension": suffix,
            "document_kind": file_kind,
            "filename_hint": hint,
            "priority": priority,
            "format_priority": {".pdf": 0, ".docx": 0, ".doc": 1,
                                ".rtf": 2, ".odt": 2, ".txt": 3}.get(suffix, 4),
        })
    _require(
        file_count == 40 and dir_count == 1
        and dict(sorted(all_extensions.items())) == m.get("extension_counts")
        and all(report.get("counts", {}).get(k, 0) == 0 for k in (
            "CHILD_NAMES_WITH_INSPECTION_CODE",
            "CHILD_NAMES_WITH_SOURCE_SITE_TOKEN",
            "CHILD_NAMES_WITH_ALTERNATE_SITE_TOKEN",
        )),
        "Conflicting private child population",
    )
    chosen = []
    counts = Counter()
    for candidate in sorted(candidates, key=lambda row: (
        row["priority"], row["format_priority"], row["filename_private"].casefold(),
        row["direct_child_index_private"],
    )):
        kind = candidate["document_kind"]
        limit = max_pdf if kind == "PDF" else max_word
        if counts[kind] >= limit:
            continue
        chosen.append(candidate)
        counts[kind] += 1
    _require(counts["PDF"] > 0 and counts["TEXT_DOCUMENT"] > 0,
             "No balanced file candidates for bounded inspection")
    return {
        "schema": SCHEMA,
        "status": "FILENAME_ONLY_PRIVATE_CONTENT_REVIEW_CANDIDATES",
        "approval_status": "NOT_APPROVED",
        "source_direct_children": 41,
        "total_direct_files": 40,
        "total_direct_subdirectories": 1,
        "available_pdf_or_word_candidates": len(candidates),
        "selected_pdf": counts["PDF"],
        "selected_text_document": counts["TEXT_DOCUMENT"],
        "selected_with_role_hint": sum(c["priority"] < len(_HINTS) for c in chosen),
        "document_contents_read": False,
        "folder_content_ownership_verified": False,
        "storage_connected": False,
        "database_connected": False,
        "database_writes": 0,
        "storage_writes": 0,
        "canonical_links_created": 0,
        "private_selected_document_names": chosen,
        "limitations": [
            "Filename priority is a sample-selection heuristic only, not Case identity",
            "No selected document is proven to belong to the source Inspection Case",
            "The one subdirectory is explicitly not entered",
            "Only separate source-attested content/custody evidence may establish Case ownership",
        ],
    }
