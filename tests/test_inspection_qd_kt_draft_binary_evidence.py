"""Real byte-level QĐKT draft audit: synthetic fixtures, never Word UAT."""
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile

import pytest

from backend.app.document.inspection_qd_kt_draft_binary_evidence import (
    QdKtDraftBinaryBlocked, verify_supplied_qdkt_draft_docx,
)
from backend.app.document.inspection_qd_kt_draft_provenance import QdKtDraftProvenance

CT = "http://schemas.openxmlformats.org/package/2006/content-types"
WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
DOTX = "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml"


def package(*, kind=DOCX, document=None, include_main=True, extra=None):
    xml = document if document is not None else (
        f'<w:document xmlns:w="{WORD}"><w:body><w:p><w:r>'
        '<w:t>Offline synthetic QDKT</w:t></w:r></w:p></w:body></w:document>'
    )
    types = (
        f'<Types xmlns="{CT}"><Override PartName="/word/document.xml"'
        f' ContentType="{kind}"/></Types>'
    )
    dst = BytesIO()
    with ZipFile(dst, "w") as archive:
        archive.writestr("[Content_Types].xml", types)
        if include_main:
            archive.writestr("word/document.xml", xml)
        if extra:
            archive.writestr(*extra)
    return dst.getvalue()


def provenance(payload):
    return QdKtDraftProvenance(
        "case-1", "draft-1", "version-1", "doc-1",
        sha256(payload).hexdigest(), "team-1", 2, ("member-1",),
    )


def test_verified_real_bytes_still_do_not_authorize_word_roster_or_issuance():
    payload = package()
    evidence = verify_supplied_qdkt_draft_docx(provenance=provenance(payload), payload=payload)
    assert evidence.verified_sha256 == sha256(payload).hexdigest()
    assert evidence.actual_docx_bytes_verified
    assert evidence.docx_package_structure_verified
    assert evidence.case_id == "case-1"
    assert evidence.roster_in_document_verified is False
    assert evidence.bookmark_owner_parity_verified is False
    assert evidence.visual_word_uat_verified is False
    assert evidence.ready_to_render is False


def test_tampered_bytes_fail_even_with_well_formed_docx():
    good = package()
    changed = package(document=f'<w:document xmlns:w="{WORD}"><w:body/></w:document>')
    with pytest.raises(QdKtDraftBinaryBlocked, match="CHECKSUM_MISMATCH"):
        verify_supplied_qdkt_draft_docx(provenance=provenance(good), payload=changed)


@pytest.mark.parametrize("bad", [
    package(kind=DOTX),
    package(include_main=False),
    package(document="<other/>"),
    package(document='<!DOCTYPE document [<!ENTITY x "bad">]><document/>'),
    package(extra=("../unsafe.txt", "bad")),
    b"not a ZIP",
])
def test_invalid_package_fails_even_when_checksum_is_correct(bad):
    with pytest.raises(QdKtDraftBinaryBlocked):
        verify_supplied_qdkt_draft_docx(provenance=provenance(bad), payload=bad)


def test_forged_ready_to_render_or_approval_rejected_without_reading():
    payload = package()
    for field in ("ready_to_render", "issuance_approved", "binary_content_verified"):
        with pytest.raises(QdKtDraftBinaryBlocked, match="PROVENANCE_UNPROVEN"):
            verify_supplied_qdkt_draft_docx(
                provenance=replace(provenance(payload), **{field: True}), payload=payload,
            )


def test_size_and_missing_bytes_rejected():
    checked = provenance(package())
    for payload in (b"", "string-not-bytes", b"x" * (32 * 1024 * 1024 + 1)):
        with pytest.raises(QdKtDraftBinaryBlocked, match="SIZE_UNSAFE"):
            verify_supplied_qdkt_draft_docx(provenance=checked, payload=payload)
