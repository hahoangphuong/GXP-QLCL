"""Read-only physical QĐKT team paragraph contract; never renders or deletes rows.

The bookmark positions are template evidence only, not proof that a persisted
InspectionTeamMember role maps to a given physical bookmark.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile

from backend.app.document.inspection_qd_kt_physical_evidence import (
    QdKtPhysicalEvidenceError, inspect_qdkt_physical_template, W,
)

_TEAM_BOOKMARKS = frozenset({"TT1x", "TT2x", "TT3x", "TT3Del", "TT_ext"})
_EXPECTED_ROLE_LABELS = {
    "GMP": ("Trưởng đoàn", "Thành viên", "Thành viên"),
    "GLP": ("Trưởng đoàn", "Thành viên", "Thành viên"),
    "GMPbb": ("Trưởng đoàn", "Thành viên", "Thành viên"),
    "GSP": ("Trưởng đoàn", "Thư ký", "Thành viên"),
}


@dataclass(frozen=True)
class QdKtTeamParagraphEvidence:
    gxp_type: str
    team_bookmark_names: tuple[str, ...]
    third_member_controls_share_paragraph: bool
    physical_role_labels_verified: bool
    member_source_mapping_verified: bool = False
    safe_to_delete_third_member_paragraph: bool = False
    ready_to_render: bool = False


def inspect_qdkt_team_paragraphs(path: Path, *, gxp_type: str) -> QdKtTeamParagraphEvidence:
    """Verify all five bookmarks and the three static role labels in one DOTX.

    The SHA256 and general pairing gate is enforced first. Read-only inspection
    intentionally does not infer conditional deletion or member overflow rules.
    """
    if gxp_type not in _EXPECTED_ROLE_LABELS:
        raise QdKtPhysicalEvidenceError("UNSUPPORTED_QDKT_GXP")
    inspect_qdkt_physical_template(path, gxp_type=gxp_type)
    try:
        with ZipFile(path) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        raise QdKtPhysicalEvidenceError("UNREADABLE_DOCUMENT_XML") from exc
    by_name: dict[str, tuple[int, str]] = {}
    for index, para in enumerate(root.iter(W + "p")):
        names = [node.get(W + "name") for node in para.iter(W + "bookmarkStart")]
        text = "".join(node.text or "" for node in para.iter(W + "t"))
        for name in names:
            if name in _TEAM_BOOKMARKS:
                if name in by_name:
                    raise QdKtPhysicalEvidenceError("DUPLICATE_TEAM_BOOKMARK")
                by_name[name] = (index, text)
    if set(by_name) != _TEAM_BOOKMARKS:
        raise QdKtPhysicalEvidenceError("TEAM_BOOKMARK_CONTRACT_MISSING")
    first, second, third = (by_name[name] for name in ("TT1x", "TT2x", "TT3x"))
    if len({first[0], second[0], third[0]}) != 3:
        raise QdKtPhysicalEvidenceError("TEAM_ROLE_PARAGRAPHS_AMBIGUOUS")
    expected = _EXPECTED_ROLE_LABELS[gxp_type]
    if any(label not in row[1] for label, row in zip(expected, (first, second, third))):
        raise QdKtPhysicalEvidenceError("TEAM_ROLE_LABEL_MISMATCH")
    third_controls_co_located = (
        third[0] == by_name["TT3Del"][0] == by_name["TT_ext"][0]
    )
    if not third_controls_co_located:
        raise QdKtPhysicalEvidenceError("THIRD_MEMBER_CONTROL_LAYOUT_MISMATCH")
    return QdKtTeamParagraphEvidence(
        gxp_type=gxp_type,
        team_bookmark_names=tuple(sorted(by_name)),
        third_member_controls_share_paragraph=True,
        physical_role_labels_verified=True,
    )
