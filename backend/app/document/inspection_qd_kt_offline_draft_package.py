"""Offline-only QĐKT draft package proof from checksum-pinned DOTX bytes.

Not a runtime renderer. No Case input, output storage, database access or API.
Changes only the package's document XML and main content-type declaration.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile, BadZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET

from backend.app.document.inspection_qd_kt_draft_issuance_xml import (
    QdKtIssuanceDateBlocked, blank_issuance_year_xml,
)

CONTENT_TYPES = "{http://schemas.openxmlformats.org/package/2006/content-types}"
MAIN_PART = "/word/document.xml"
DOTX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"


class QdKtDraftPackageBlocked(ValueError):
    pass


def build_offline_date_only_docx(*, template: bytes, expected_sha256: str) -> bytes:
    """Produce disposable DOCX for layout QA, never an official draft."""
    if not isinstance(template, bytes) or sha256(template).hexdigest() != expected_sha256:
        raise QdKtDraftPackageBlocked("QDKT_TEMPLATE_CHECKSUM_MISMATCH")
    try:
        with ZipFile(BytesIO(template)) as source:
            members = source.infolist()
            if len({part.filename for part in members}) != len(members):
                raise QdKtDraftPackageBlocked("QDKT_PACKAGE_DUPLICATE_PART")
            if "word/document.xml" not in source.namelist() or "[Content_Types].xml" not in source.namelist():
                raise QdKtDraftPackageBlocked("QDKT_PACKAGE_PART_MISSING")
            types_root = ET.fromstring(source.read("[Content_Types].xml"))
            main = [item for item in types_root.iter(CONTENT_TYPES + "Override")
                    if item.get("PartName") == MAIN_PART]
            if len(main) != 1 or main[0].get("ContentType") != DOTX_TYPE:
                raise QdKtDraftPackageBlocked("QDKT_PACKAGE_TEMPLATE_CONTENT_TYPE_UNPROVEN")
            main[0].set("ContentType", DOCX_TYPE)
            blanked_xml, _ = blank_issuance_year_xml(source.read("word/document.xml"))
            replacements = {
                "word/document.xml": blanked_xml,
                "[Content_Types].xml": ET.tostring(types_root, encoding="utf-8", xml_declaration=True),
            }
            target = BytesIO()
            with ZipFile(target, "w") as out:
                for member in members:
                    out.writestr(member, replacements.get(member.filename, source.read(member.filename)))
            return target.getvalue()
    except (BadZipFile, ET.ParseError, OSError, QdKtIssuanceDateBlocked) as exc:
        raise QdKtDraftPackageBlocked("QDKT_PACKAGE_INVALID") from exc
