"""Synthetic DOTX bytes: evidence collection, not legacy template parity."""
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile

import pytest

from backend.app.document.inspection_qd_kt_dotx_binary_audit import (
    QdKtDotxAuditBlocked,
    inspect_qdkt_dotx_binary,
    inspect_supplied_qdkt_dotx_set,
)
from backend.app.document.inspection_qd_kt_template_asset_contract import (
    InspectionQdKtTemplateAsset,
)

BOOKMARK_XML = (b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                b'<w:body><w:bookmarkStart w:id="1" w:name="Fulldate"/>'
                b'<w:bookmarkEnd w:id="1"/></w:body></w:document>')


def dotx_bytes(xml=BOOKMARK_XML):
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return stream.getvalue()


def asset(content, gxp="GMP"):
    return InspectionQdKtTemplateAsset(
        gxp_type=gxp, filename=f"2. QD KT - {gxp}.dotx",
        storage_root="template", storage_relative_path=f"2. QD KT - {gxp}.dotx",
        checksum_sha256=sha256(content).hexdigest(),
    )


def test_actual_supplied_bytes_are_measured_without_render_or_owner_promotion(tmp_path):
    data = dotx_bytes()
    path = tmp_path / "source.dotx"
    path.write_bytes(data)
    result = inspect_qdkt_dotx_binary(path, asset=asset(data))
    assert result.actual_sha256 == sha256(data).hexdigest()
    assert result.bookmark_names == ("Fulldate",)
    assert result.bookmark_count == 1
    assert result.binary_checksum_verified is True
    assert result.bookmark_owner_parity_verified is False
    assert result.ready_to_render is False


def test_modified_binary_is_rejected_before_xml_inspection(tmp_path):
    original = dotx_bytes()
    path = tmp_path / "source.dotx"
    path.write_bytes(dotx_bytes(b"<invalid/>"))
    with pytest.raises(QdKtDotxAuditBlocked, match="QDKT_DOTX_CHECKSUM_MISMATCH"):
        inspect_qdkt_dotx_binary(path, asset=asset(original))


@pytest.mark.parametrize("bad_xml", [
    b"<invalid",
    b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    b'<w:bookmarkStart w:id="1" w:name="x"/></w:document>',
    b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    b'<w:bookmarkStart w:id="1" w:name="x"/><w:bookmarkStart w:id="1" w:name="y"/>'
    b'<w:bookmarkEnd w:id="1"/></w:document>',
])
def test_malformed_word_bookmark_structure_fails_closed(tmp_path, bad_xml):
    data = dotx_bytes(bad_xml)
    path = tmp_path / "source.dotx"
    path.write_bytes(data)
    with pytest.raises(QdKtDotxAuditBlocked):
        inspect_qdkt_dotx_binary(path, asset=asset(data))


def test_non_zip_with_matching_checksum_cannot_be_accepted(tmp_path):
    data = b"not a Word template"
    path = tmp_path / "bad.dotx"
    path.write_bytes(data)
    with pytest.raises(QdKtDotxAuditBlocked, match="QDKT_DOTX_WORD_XML_UNVERIFIED"):
        inspect_qdkt_dotx_binary(path, asset=asset(data))


def test_missing_binary_fails_closed(tmp_path):
    with pytest.raises(QdKtDotxAuditBlocked, match="QDKT_DOTX_BINARY_UNAVAILABLE"):
        inspect_qdkt_dotx_binary(tmp_path / "missing.dotx", asset=asset(dotx_bytes()))


def test_four_gxp_set_is_atomic_and_reports_each_actual_binary(tmp_path):
    data = dotx_bytes()
    assets = tuple(asset(data, gxp) for gxp in ("GLP", "GMP", "GMPbb", "GSP"))
    for entry in assets:
        (tmp_path / entry.filename).write_bytes(data)
    result = inspect_supplied_qdkt_dotx_set(tmp_path, assets=assets)
    assert {row.gxp_type for row in result} == {"GLP", "GMP", "GMPbb", "GSP"}
    (tmp_path / assets[0].filename).unlink()
    with pytest.raises(QdKtDotxAuditBlocked, match="QDKT_DOTX_BINARY_UNAVAILABLE"):
        inspect_supplied_qdkt_dotx_set(tmp_path, assets=assets)


def test_unknown_gxp_set_is_rejected(tmp_path):
    data = dotx_bytes()
    assets = tuple(asset(data, gxp) for gxp in ("GLP", "GMP", "GSP"))
    with pytest.raises(QdKtDotxAuditBlocked, match="QDKT_DOTX_GXP_SET_UNVERIFIED"):
        inspect_supplied_qdkt_dotx_set(tmp_path, assets=assets)
