"""Read-only, bounded content-signal witness for FIVE previously selected files.

Signals are textual observations, not proof of regulatory Case ownership.
No document text, filenames, ID values, UNC paths or SHA digests go to stdout.
Never copy files, bind storage, rewrite Site, or use a name-based fallback.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from io import BytesIO
import re
from typing import Any
import zipfile
import xml.etree.ElementTree as ET

from backend.app.storage.smb import SmbStorageService, smbclient, smbpath
from tools.audit_ddk_inspection_folder_mismatch_metadata_readonly import (
    classify_exact_folder_metadata_readonly,
)
from tools.triage_ddk_inspection_private_document_candidates import (
    make_private_document_candidate_manifest,
)

SCHEMA = "GXP_DDK_INSPECTION_SELECTED_DOCUMENT_CONTENT_SIGNALS_READONLY_V1"
MAX_SINGLE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 24 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
MAX_PDF_PAGES = 8
MAX_DOCX_XML_BYTES = 2 * 1024 * 1024


class ContentSignalAuditBlocked(ValueError):
    pass


def _require(ok: bool, msg: str) -> None:
    if not ok:
        raise ContentSignalAuditBlocked(msg)


def _text_from_docx(data: bytes) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(BytesIO(data)) as z:
            files = z.infolist()
            if len(files) > 200 or any(
                info.flag_bits & 1 or info.file_size > MAX_DOCX_XML_BYTES
                for info in files if info.filename == "word/document.xml"
            ):
                return "FORMAT_LIMIT", ""
            matches = [i for i in files if i.filename == "word/document.xml"]
            if len(matches) != 1 or matches[0].file_size > MAX_DOCX_XML_BYTES:
                return "UNSUPPORTED_STRUCTURE", ""
            # Explicit max-sized read and no extraction to disk or network.
            with z.open(matches[0]) as fh:
                xml = fh.read(MAX_DOCX_XML_BYTES + 1)
            if len(xml) > MAX_DOCX_XML_BYTES:
                return "FORMAT_LIMIT", ""
            tree = ET.fromstring(xml)
            tokens = [el.text for el in tree.iter()
                      if el.tag.endswith("}t") and el.text]
            return ("TEXT_AVAILABLE" if tokens else "NO_EXTRACTABLE_TEXT",
                    " ".join(tokens)[:MAX_TEXT_CHARS])
    except (ValueError, OSError, zipfile.BadZipFile, ET.ParseError,
            RuntimeError, KeyError):
        return "PARSER_ERROR", ""


def _text_from_pdf(data: bytes) -> tuple[str, str]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "PARSER_UNAVAILABLE", ""
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            return "ENCRYPTED_UNREADABLE", ""
        pages = reader.pages
        texts: list[str] = []
        for i in range(min(len(pages), MAX_PDF_PAGES)):
            text = pages[i].extract_text() or ""
            texts.append(text)
            if sum(len(item) for item in texts) >= MAX_TEXT_CHARS:
                break
        joined = "\n".join(texts)[:MAX_TEXT_CHARS]
        return ("TEXT_AVAILABLE" if joined.strip() else "NO_EXTRACTABLE_TEXT", joined)
    except Exception:
        # A parser failure is neither a source-identity negative nor approval.
        return "PARSER_ERROR", ""


def classify_document_bytes(
    data: bytes, *, extension: str, inspection_code: str,
    source_site_id: int, alternate_site_id: int,
) -> dict[str, Any]:
    """No document bytes or extracted text leave this pure function."""
    _require(
        isinstance(data, bytes) and len(data) <= MAX_SINGLE_BYTES
        and extension in {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"}
        and isinstance(inspection_code, str) and bool(inspection_code.strip())
        and type(source_site_id) is int and source_site_id > 0
        and type(alternate_site_id) is int and alternate_site_id > 0
        and source_site_id != alternate_site_id,
        "Unsafe or unbound document-byte contract",
    )
    if extension == ".pdf":
        status, text = _text_from_pdf(data) if data.startswith(b"%PDF-") else ("FORMAT_MISMATCH", "")
    elif extension == ".docx":
        status, text = _text_from_docx(data) if data.startswith(b"PK") else ("FORMAT_MISMATCH", "")
    elif extension == ".txt":
        try:
            text = data.decode("utf-8-sig", errors="strict")[:MAX_TEXT_CHARS]
            status = "TEXT_AVAILABLE" if text.strip() else "NO_EXTRACTABLE_TEXT"
        except UnicodeDecodeError:
            status, text = "UNSUPPORTED_ENCODING", ""
    else:
        status, text = "UNSUPPORTED_FORMAT", ""
    folded = text.casefold() if status == "TEXT_AVAILABLE" else ""
    def token_seen(token: str) -> bool:
        return bool(folded) and token.casefold() in folded
    return {
        "format_status": status,
        "exact_inspection_code_in_extractable_text": bool(
            folded and re.search(
                r"(?<!\w)" + re.escape(inspection_code.strip().casefold()) + r"(?!\w)",
                folded,
            )
        ),
        "source_site_id_marker_in_extractable_text": token_seen(f"(ID-{source_site_id})"),
        "alternate_site_id_marker_in_extractable_text": token_seen(f"(ID-{alternate_site_id})"),
        "document_sha256_private": sha256(data).hexdigest(),
        "bytes_read_private": len(data),
        "content_ownership_verified": False,
    }


def inspect_selected_direct_children_readonly(
    storage: SmbStorageService, *, prior_metadata: dict[str, Any],
    sample: dict[str, Any], source_request: dict[str, Any],
) -> dict[str, Any]:
    """Exactly 5 verified direct-child files; read at most 24 MB total.

    The fresh one-folder metadata MUST be identical to the pinned
    prior direct-child population. A changed name or extra file blocks.
    The original source Site continues to own the Case.
    """
    _require(isinstance(storage, SmbStorageService)
             and smbclient is not None and smbpath is not None,
             "Unapproved SMB adapter")
    expected_sample = make_private_document_candidate_manifest(prior_metadata)
    _require(
        sample.get("schema") == expected_sample["schema"]
        and sample.get("approval_status") == "NOT_APPROVED"
        and sample.get("private_selected_document_names") ==
            expected_sample["private_selected_document_names"]
        and len(expected_sample["private_selected_document_names"]) == 5,
        "Private selected sample changed from source metadata",
    )
    m = prior_metadata.get("private_folder_metadata")
    _require(isinstance(m, dict) and isinstance(source_request, dict)
             and source_request.get("schema") ==
                 "GXP_DDK_CASE_INSPECTION_PHYSICAL_SOURCE_REQUEST_V1"
             and source_request.get("approval_status") == "NOT_APPROVED"
             and m.get("source_site_legacy_id") == source_request.get("source_site_legacy_id")
             and m.get("observed_other_site_legacy_id") ==
                 source_request.get("observed_site_legacy_id_unverified")
             and m.get("inspection_legacy_code") == source_request.get("inspection_code")
             and type(m.get("source_year")) is int,
             "Physical workbook request or Case Site drifted",
    )
    fresh = classify_exact_folder_metadata_readonly(
        storage, source_year=m["source_year"],
        source_site_legacy_id=m["source_site_legacy_id"],
        observed_other_site_legacy_id=m["observed_other_site_legacy_id"],
        inspection_legacy_code=m["inspection_legacy_code"],
    )
    _require(
        fresh["source_year_root_entries_scanned"] ==
            prior_metadata.get("source_year_root_entries_scanned")
        and fresh["counts"] == prior_metadata.get("counts")
        and fresh["private_folder_metadata"] == m,
        "Source-year or direct-child folder metadata changed",
    )
    parent = storage._join_root(storage.inspection_root, str(m["source_year"]))
    folder = storage._join_root(parent, m["folder_leaf"])
    _require(bool(smbpath.isdir(folder)), "Source-bound folder no longer exists")
    child_by_name = {
        r["name_private"]: r for r in m["children"] if not r["is_dir"]
    }
    total_read = 0
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for selected in expected_sample["private_selected_document_names"]:
        name = selected["filename_private"]
        _require(name in child_by_name and child_by_name[name]["extension_private"] ==
                 selected["extension"] and name not in {".", ".."}
                 and not any(ch in name for ch in ("/", "\\", "\x00")),
                 "Selected filename no longer a verified direct child")
        target = storage._join_root(folder, name)
        _require(bool(smbpath.isfile(target)), "Selected direct child is no longer a file")
        info = smbclient.stat(target)
        length = info.st_size
        _require(type(length) is int and length >= 0,
                 "Selected direct child size untrusted")
        if length > MAX_SINGLE_BYTES or total_read + length > MAX_TOTAL_BYTES:
            record = {
                "filename_private": name,
                "document_kind": selected["document_kind"],
                "format_status": "SKIPPED_SIZE_BUDGET",
                "document_sha256_private": None,
                "bytes_read_private": 0,
                "exact_inspection_code_in_extractable_text": False,
                "source_site_id_marker_in_extractable_text": False,
                "alternate_site_id_marker_in_extractable_text": False,
                "content_ownership_verified": False,
            }
        else:
            with smbclient.open_file(target, mode="rb") as fh:
                data = fh.read(MAX_SINGLE_BYTES + 1)
            _require(len(data) == length and len(data) <= MAX_SINGLE_BYTES,
                     "Selected file changed during bounded binary read")
            total_read += len(data)
            record = {
                "filename_private": name,
                "document_kind": selected["document_kind"],
                **classify_document_bytes(
                    data, extension=selected["extension"],
                    inspection_code=m["inspection_legacy_code"],
                    source_site_id=m["source_site_legacy_id"],
                    alternate_site_id=m["observed_other_site_legacy_id"],
                ),
            }
        counts[record["format_status"]] += 1
        if record["exact_inspection_code_in_extractable_text"]:
            counts["EXACT_INSPECTION_CODE_TEXT_PRESENT"] += 1
        records.append(record)
    _require(len(records) == 5, "Incomplete source-selected content sample")
    return {
        "schema": SCHEMA,
        "status": "FIVE_SELECTED_BINARY_CONTENT_SIGNALS_OBSERVED_NOT_APPROVED",
        "approval_status": "NOT_APPROVED",
        "source_bound_files_selected": 5,
        "file_contents_read_count": sum(r["bytes_read_private"] > 0 for r in records),
        "total_binary_bytes_read": total_read,
        "parse_status_counts": dict(sorted(counts.items())),
        "case_ownership_proven": False,
        "folder_mapping_approved": False,
        "database_connected": False,
        "database_writes": 0,
        "storage_writes": 0,
        "canonical_links_created": 0,
        "private_selected_file_evidence": records,
        "limitations": [
            "Free-text token occurrence is observational, not legal provenance",
            "No OCR; scanned/no-text PDF does not prove a negative",
            "PDF parser unavailable/failed is inconclusive",
            "Unsupported DOC/ODT/RTF or encoding is inconclusive",
            "No child directory was inspected and no storage mapping was changed",
        ],
    }


def reparse_only_previously_unavailable_pdfs_readonly(
    storage: SmbStorageService, *,
    prior_metadata: dict[str, Any],
    sample: dict[str, Any],
    source_request: dict[str, Any],
    prior_content: dict[str, Any],
) -> dict[str, Any]:
    """Read only the THREE prior PARSER_UNAVAILABLE PDFs with a pinned parser.

    Fail closed if any sampled content byte, original Case folder metadata,
    protected name, or previous parse status has drifted.  The two successfully
    parsed text documents are NOT opened again.  The full five-file report is
    preserved in the new private result, without retroactive ownership claims.
    """
    try:
        from pypdf import __version__ as pypdf_version
        from pypdf import PdfReader as _PdfReader
    except ImportError as exc:
        raise ContentSignalAuditBlocked(
            "PINNED_PDF_PARSER_UNAVAILABLE"
        ) from exc
    _require(str(pypdf_version) == "6.20.1" and _PdfReader is not None,
             "Unpinned PDF parser version")
    _require(
        isinstance(storage, SmbStorageService)
        and smbclient is not None and smbpath is not None,
        "Unapproved SMB reader",
    )
    original_sample = make_private_document_candidate_manifest(prior_metadata)
    chosen = original_sample["private_selected_document_names"]
    _require(
        sample.get("schema") == original_sample["schema"]
        and sample.get("approval_status") == "NOT_APPROVED"
        and sample.get("private_selected_document_names") == chosen
        and len(chosen) == 5 and sum(x["document_kind"] == "PDF" for x in chosen) == 3,
        "Original five-file selection drifted",
    )
    m = prior_metadata["private_folder_metadata"]
    _require(
        source_request.get("schema") ==
            "GXP_DDK_CASE_INSPECTION_PHYSICAL_SOURCE_REQUEST_V1"
        and source_request.get("approval_status") == "NOT_APPROVED"
        and m.get("source_site_legacy_id") == source_request.get("source_site_legacy_id")
        and m.get("observed_other_site_legacy_id") ==
            source_request.get("observed_site_legacy_id_unverified")
        and m.get("inspection_legacy_code") == source_request.get("inspection_code")
        and type(m.get("source_year")) is int,
        "Original physical source request changed",
    )
    old_rows = prior_content.get("private_selected_file_evidence")
    _require(
        prior_content.get("schema") == SCHEMA
        and prior_content.get("status") ==
            "FIVE_SELECTED_BINARY_CONTENT_SIGNALS_OBSERVED_NOT_APPROVED"
        and prior_content.get("approval_status") == "NOT_APPROVED"
        and prior_content.get("source_bound_files_selected") == 5
        and prior_content.get("file_contents_read_count") == 5
        and prior_content.get("total_binary_bytes_read") == 2289044
        and prior_content.get("parse_status_counts") ==
            {"PARSER_UNAVAILABLE": 3, "TEXT_AVAILABLE": 2}
        and prior_content.get("case_ownership_proven") is False
        and prior_content.get("folder_mapping_approved") is False
        and prior_content.get("database_connected") is False
        and all(prior_content.get(key) == 0 for key in
                ("database_writes", "storage_writes", "canonical_links_created"))
        and isinstance(old_rows, list) and len(old_rows) == 5,
        "Previous five-file report not exact source population",
    )
    for selected, old in zip(chosen, old_rows):
        _require(
            old.get("filename_private") == selected["filename_private"]
            and old.get("document_kind") == selected["document_kind"]
            and isinstance(old.get("document_sha256_private"), str)
            and re.fullmatch(r"[0-9a-f]{64}", old["document_sha256_private"])
            and type(old.get("bytes_read_private")) is int
            and 0 < old["bytes_read_private"] <= MAX_SINGLE_BYTES
            and old.get("content_ownership_verified") is False
            and old.get("format_status") ==
              ("PARSER_UNAVAILABLE" if selected["document_kind"] == "PDF"
               else "TEXT_AVAILABLE"),
            "Previous individual file evidence changed",
        )
    _require(
        sum(x["bytes_read_private"] for x in old_rows) == 2289044,
        "Previous read-byte accounting drifted",
    )
    # Force exact parent population recheck before any binary read.
    fresh = classify_exact_folder_metadata_readonly(
        storage, source_year=m["source_year"],
        source_site_legacy_id=m["source_site_legacy_id"],
        observed_other_site_legacy_id=m["observed_other_site_legacy_id"],
        inspection_legacy_code=m["inspection_legacy_code"],
    )
    _require(
        fresh["source_year_root_entries_scanned"] ==
            prior_metadata.get("source_year_root_entries_scanned")
        and fresh["counts"] == prior_metadata.get("counts")
        and fresh["private_folder_metadata"] == m,
        "Original single-folder population drifted",
    )
    year_path = storage._join_root(storage.inspection_root, str(m["source_year"]))
    parent = storage._join_root(year_path, m["folder_leaf"])
    _require(bool(smbpath.isdir(parent)), "Source folder unavailable")
    new_rows = []
    statuses: Counter[str] = Counter()
    reads = 0
    pdf_bytes = 0
    for selected, old in zip(chosen, old_rows):
        if selected["document_kind"] != "PDF":
            new_rows.append(dict(old))
            statuses[old["format_status"]] += 1
            continue
        name = selected["filename_private"]
        _require(
            selected["extension"] == ".pdf"
            and len(name) > 0 and name not in {".", ".."}
            and not any(x in name for x in ("/", "\\", "\x00")),
            "Untrusted previously selected PDF name",
        )
        target = storage._join_root(parent, name)
        _require(bool(smbpath.isfile(target)), "Selected PDF missing")
        info = smbclient.stat(target)
        expected_size = old["bytes_read_private"]
        _require(
            type(info.st_size) is int and info.st_size == expected_size
            and expected_size <= MAX_SINGLE_BYTES
            and pdf_bytes + expected_size <= MAX_TOTAL_BYTES,
            "PDF changed or reading would exceed original budget",
        )
        with smbclient.open_file(target, mode="rb") as fh:
            data = fh.read(expected_size + 1)
        _require(
            len(data) == expected_size
            and sha256(data).hexdigest() == old["document_sha256_private"],
            "Selected PDF byte SHA drifted",
        )
        record = classify_document_bytes(
            data, extension=".pdf",
            inspection_code=m["inspection_legacy_code"],
            source_site_id=m["source_site_legacy_id"],
            alternate_site_id=m["observed_other_site_legacy_id"],
        )
        _require(record["format_status"] != "PARSER_UNAVAILABLE",
                 "Pinned PDF parser did not load")
        new_rows.append({
            "filename_private": name,
            "document_kind": selected["document_kind"],
            **record,
        })
        pdf_bytes += expected_size
        reads += 1
        statuses[record["format_status"]] += 1
    _require(len(new_rows) == 5 and reads == 3,
             "Incorrect PDF-only replay population")
    for row in new_rows:
        if row["exact_inspection_code_in_extractable_text"]:
            statuses["EXACT_INSPECTION_CODE_TEXT_PRESENT"] += 1
    return {
        "schema": "GXP_DDK_THREE_PDF_PARSER_REPLAY_CONTENT_SIGNALS_READONLY_V1",
        "status": "PINNED_PDF_REPLAY_SOURCE_BOUND_NO_OWNERSHIP_APPROVAL",
        "approval_status": "NOT_APPROVED",
        "source_bound_files_selected": 5,
        "pdf_files_reparsed": 3,
        "previous_text_documents_reused": 2,
        "total_pdf_bytes_replayed": pdf_bytes,
        "pypdf_version": str(pypdf_version),
        "parse_status_counts": dict(sorted(statuses.items())),
        "case_ownership_proven": False,
        "folder_mapping_approved": False,
        "database_connected": False,
        "database_writes": 0,
        "storage_writes": 0,
        "canonical_links_created": 0,
        "private_selected_file_evidence": new_rows,
        "limitations": [
            "Text signal and source Site marker are NOT legal content ownership evidence",
            "Two earlier readable text-document records were not re-opened",
            "Scanned PDFs with no text layer remain inconclusive, not negative",
            "The unmatched Site folder continues to have NO canonical Case binding",
            "Other PDF files, other year roots and the child directory were not accessed",
        ],
    }
