"""Offline OOXML archive guard: no extraction, suspicious members or large payloads."""
from hashlib import sha256
from io import BytesIO
import stat
from zipfile import ZipFile, ZipInfo

import pytest

from backend.app.document.inspection_qd_kt_offline_package_integrity import (
    MAX_PARTS, MAX_PART_SIZE, QdKtOfflinePackageIntegrityBlocked,
    require_safe_ooxml_members,
)
from backend.app.document.inspection_qd_kt_offline_draft_package import (
    QdKtDraftPackageBlocked, build_offline_date_only_docx, DOTX_TYPE,
)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"


def _archive(*, extra=None, extra_content=b"x"):
    xml = (f'<w:document xmlns:w="{W}"><w:body><w:p>'
           '<w:r><w:t>Hà Nội, ngày    tháng    năm </w:t></w:r>'
           '<w:r><w:t>2026</w:t></w:r></w:p></w:body></w:document>')
    manifest = (f'<Types xmlns="{CT}"><Override PartName="/word/document.xml"'
                f' ContentType="{DOTX_TYPE}"/></Types>')
    buf = BytesIO()
    with ZipFile(buf, "w") as out:
        out.writestr("[Content_Types].xml", manifest)
        out.writestr("word/document.xml", xml)
        if extra is not None:
            out.writestr(extra, extra_content)
    return buf.getvalue()


@pytest.mark.parametrize("name", [
    "../escape.xml", "word/../escape.xml", "/absolute.xml",
    "word\\foreign.xml", "C:drive.xml", "word//empty.xml",
    "word/./same.xml",
])
def test_offline_draft_rejects_unsafe_part_names(name):
    raw = _archive(extra=name)
    with pytest.raises(QdKtDraftPackageBlocked, match="QDKT_PACKAGE_INVALID"):
        build_offline_date_only_docx(template=raw, expected_sha256=sha256(raw).hexdigest())


def test_rejects_symlink_without_extracting_it():
    entry = ZipInfo("word/external.xml")
    entry.create_system = 3
    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
    raw = _archive(extra=entry, extra_content=b"/etc/passwd")
    with pytest.raises(QdKtDraftPackageBlocked, match="QDKT_PACKAGE_INVALID"):
        build_offline_date_only_docx(template=raw, expected_sha256=sha256(raw).hexdigest())


def test_rejects_overlarge_single_part():
    raw = _archive(extra="word/big.bin", extra_content=b"a" * (MAX_PART_SIZE + 1))
    with pytest.raises(QdKtDraftPackageBlocked, match="QDKT_PACKAGE_INVALID"):
        build_offline_date_only_docx(template=raw, expected_sha256=sha256(raw).hexdigest())


def test_rejects_excessive_member_count():
    buf = BytesIO()
    with ZipFile(buf, "w") as out:
        for idx in range(MAX_PARTS + 1):
            out.writestr(f"word/part-{idx}.xml", "x")
    with ZipFile(BytesIO(buf.getvalue())) as source:
        with pytest.raises(QdKtOfflinePackageIntegrityBlocked, match="QDKT_PACKAGE_PART_COUNT_UNSAFE"):
            require_safe_ooxml_members(source)


def test_allows_benign_dir_entries_and_document_preservation():
    raw = _archive(extra="word/extras/", extra_content=b"")
    out = build_offline_date_only_docx(template=raw, expected_sha256=sha256(raw).hexdigest())
    with ZipFile(BytesIO(out)) as result:
        assert "word/extras/" in result.namelist()
        assert result.testzip() is None
        assert b"2026" not in result.read("word/document.xml")
