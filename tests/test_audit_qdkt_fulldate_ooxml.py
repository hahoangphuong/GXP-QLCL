"""Synthetic OOXML fixtures for a strictly read-only Fulldate audit."""
from zipfile import ZipFile, ZIP_DEFLATED

from tools.audit_qdkt_fulldate_ooxml import inspect_qdkt_fulldate

PREFIX = ('<w:document xmlns:w="http://schemas.openxmlformats.org/'
          'wordprocessingml/2006/main"><w:body><w:p>')
SUFFIX = '</w:p></w:body></w:document>'


def make_template(tmp_path, name, body):
    path = tmp_path / name
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", PREFIX + body + SUFFIX)
    return path


def test_unique_fulldate_pair_is_structural_only_not_visual_pass(tmp_path):
    source = make_template(tmp_path, "GMP.dotx", (
        '<w:bookmarkStart w:id="7" w:name="Fulldate"/>'
        '<w:r><w:t>placeholder date</w:t></w:r>'
        '<w:bookmarkEnd w:id="7"/>'
    ))
    before = source.read_bytes()
    audit = inspect_qdkt_fulldate(source)
    assert audit["status"] == "STRUCTURAL_BOOKMARK_FOUND"
    assert audit["matches"][0]["bookmark_id"] == "7"
    assert "visual blank issuance date" in audit["limitations"][0]
    assert source.read_bytes() == before


def test_missing_fulldate_is_blocked(tmp_path):
    source = make_template(tmp_path, "GLP.dotx", '<w:r><w:t>No bookmark</w:t></w:r>')
    assert inspect_qdkt_fulldate(source)["status"] == "BOOKMARK_NOT_FOUND"


def test_duplicate_fulldate_is_ambiguous(tmp_path):
    source = make_template(tmp_path, "GSP.dotx", (
        '<w:bookmarkStart w:id="1" w:name="Fulldate"/>'
        '<w:bookmarkEnd w:id="1"/>'
        '<w:bookmarkStart w:id="2" w:name="Fulldate"/>'
        '<w:bookmarkEnd w:id="2"/>'
    ))
    assert inspect_qdkt_fulldate(source)["status"] == "BOOKMARK_AMBIGUOUS"


def test_unpaired_fulldate_is_ambiguous(tmp_path):
    source = make_template(tmp_path, "GMPbb.dotx", '<w:bookmarkStart w:id="1" w:name="Fulldate"/>')
    assert inspect_qdkt_fulldate(source)["status"] == "BOOKMARK_AMBIGUOUS"


def test_corrupt_template_fails_closed(tmp_path):
    path = tmp_path / "corrupted.dotx"
    path.write_bytes(b"not-ooxml")
    assert inspect_qdkt_fulldate(path)["status"] == "UNREADABLE_TEMPLATE"
