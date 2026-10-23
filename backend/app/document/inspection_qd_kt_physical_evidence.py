"""Read-only physical evidence check for four owner-supplied QĐKT DOTX templates.

No document mutation, renderer or authorization decision. Binaries are supplied
outside Git and their SHA-256 pins are the existing template asset contract.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree as ET
import re

from backend.app.document.inspection_qd_kt_template_asset_contract import (
    get_inspection_qd_kt_template_asset,
)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class QdKtPhysicalEvidenceError(ValueError):
    pass


def inspect_qdkt_physical_template(path: Path, *, gxp_type: str) -> dict:
    """Inspect exact binary and report only proven physical evidence.

    Absence of Fulldate is not proof of a visually blank administrative date.
    """
    asset = get_inspection_qd_kt_template_asset(gxp_type)
    raw = Path(path).read_bytes()
    digest = sha256(raw).hexdigest()
    if digest != asset.checksum_sha256:
        raise QdKtPhysicalEvidenceError("TEMPLATE_SHA256_MISMATCH")
    try:
        with ZipFile(path) as archive:
            document = ET.fromstring(archive.read("word/document.xml"))
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        raise QdKtPhysicalEvidenceError("UNREADABLE_DOCUMENT_XML") from exc

    bookmarks = {}
    for node in document.iter(W + "bookmarkStart"):
        identifier, name = node.get(W + "id"), node.get(W + "name")
        if not identifier or not name or identifier in bookmarks:
            raise QdKtPhysicalEvidenceError("BOOKMARK_START_AMBIGUOUS")
        bookmarks[identifier] = name
    end_ids = Counter(node.get(W + "id") for node in document.iter(W + "bookmarkEnd"))
    if Counter({identifier: 1 for identifier in bookmarks}) != end_ids:
        raise QdKtPhysicalEvidenceError("BOOKMARK_END_MISMATCH")
    names = sorted(name for name in bookmarks.values() if not name.startswith("_"))
    if len(names) != len(set(names)):
        raise QdKtPhysicalEvidenceError("BOOKMARK_NAME_AMBIGUOUS")

    issuance_lines = []
    for paragraph in document.iter(W + "p"):
        text = "".join(node.text or "" for node in paragraph.iter(W + "t"))
        if all(token in text.lower() for token in ("ngày", "tháng", "năm")):
            issuance_lines.append(text)
    fixed_year_lines = [line for line in issuance_lines
                        if re.search(r"\bnăm\s+(?:19|20)\d{2}\b", line)]
    return {
        "gxp_type": gxp_type,
        "verified_sha256": digest,
        "bookmark_names": names,
        "business_bookmark_count": len(names),
        "fulldate_bookmark_present": "Fulldate" in names,
        "date_line_candidates": fixed_year_lines,
        "issuance_date_policy_verified": False,
        "visual_render_verified": False,
        "ready_to_render": False,
    }
