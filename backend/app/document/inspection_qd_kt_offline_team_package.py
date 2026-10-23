"""Offline-only two-member QĐKT layout package composition.

Composes the already verified checksum-pinned DOTX conversion, blank
issuance date, and complete TT3Del paragraph removal. This is a disposable
structure/layout QA tool, NOT a business renderer or a Case endpoint.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile, BadZipFile

from lxml import etree as ET

from backend.app.document.inspection_qd_kt_offline_draft_package import (
    QdKtDraftPackageBlocked, build_offline_date_only_docx,
)
from backend.app.document.inspection_qd_kt_third_member_span import (
    QdKtThirdMemberSpanBlocked, remove_third_member_span_xml,
)


class QdKtOfflineTeamPackageBlocked(ValueError):
    pass


def build_offline_two_member_docx(
    *, template: bytes, expected_sha256: str, member_count: int,
) -> bytes:
    """Construct a nonissuable, template-only 2-member DOCX for visual QA.

    Does not insert names, infer modern TeamMember-to-TTVdd equivalence,
    or prove business formatting. Requires exact count 2 and a pinned DOTX.
    """
    if type(member_count) is not int or member_count != 2:
        raise QdKtOfflineTeamPackageBlocked("QDKT_TWO_MEMBER_ONLY")
    try:
        blanked = build_offline_date_only_docx(
            template=template, expected_sha256=expected_sha256,
        )
        with ZipFile(BytesIO(blanked)) as src:
            members = src.infolist()
            original_xml = src.read("word/document.xml")
            changed_xml = remove_third_member_span_xml(original_xml)
            if changed_xml == original_xml:
                raise QdKtOfflineTeamPackageBlocked("QDKT_TEAM_SPAN_UNCHANGED")
            dst = BytesIO()
            with ZipFile(dst, "w") as out:
                for info in members:
                    out.writestr(
                        info,
                        changed_xml if info.filename == "word/document.xml" else src.read(info.filename),
                    )
        result = dst.getvalue()
        with ZipFile(BytesIO(result)) as verified:
            if verified.testzip() is not None:
                raise QdKtOfflineTeamPackageBlocked("QDKT_PACKAGE_CRC_INVALID")
            if sha256(template).hexdigest() != expected_sha256:
                raise QdKtOfflineTeamPackageBlocked("QDKT_SOURCE_HASH_CHANGED")
        return result
    except (QdKtDraftPackageBlocked, QdKtThirdMemberSpanBlocked,
            BadZipFile, ET.ParseError, OSError) as exc:
        raise QdKtOfflineTeamPackageBlocked("QDKT_OFFLINE_TWO_MEMBER_PACKAGE_INVALID") from exc
