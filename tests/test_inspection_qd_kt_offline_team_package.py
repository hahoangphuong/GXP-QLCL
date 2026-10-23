"""No Case ownership claim: package composition is a disposable offline fixture."""
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile
from lxml import etree as ET

import pytest

from backend.app.document.inspection_qd_kt_offline_team_package import (
    QdKtOfflineTeamPackageBlocked, build_offline_two_member_docx,
)
from backend.app.document.inspection_qd_kt_offline_draft_package import DOTX_TYPE, DOCX_TYPE


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"


def _template():
    xml = (f'<w:document xmlns:w="{W}" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
           'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" mc:Ignorable="w14"><w:body>'
           '<w:p><w:r><w:t>Hà Nội, ngày    tháng    năm </w:t></w:r><w:r><w:t>202</w:t></w:r><w:r><w:t>6</w:t></w:r></w:p>'
           '<w:p><w:r><w:t>Trưởng đoàn</w:t></w:r></w:p>'
           '<w:p><w:r><w:t>Thành viên thứ hai</w:t></w:r></w:p>'
           '<w:p><w:bookmarkStart w:id="5" w:name="TT3x"/>'
           '<w:bookmarkStart w:id="6" w:name="TT3Del"/>'
           '<w:bookmarkStart w:id="7" w:name="TT_ext"/>'
           '<w:bookmarkEnd w:id="7"/><w:r><w:t>Thành viên thứ ba</w:t></w:r>'
           '<w:bookmarkEnd w:id="5"/></w:p><w:bookmarkEnd w:id="6"/>'
           '<w:p><w:r><w:t>Điều khoản tiếp theo</w:t></w:r></w:p>'
           '</w:body></w:document>')
    types = (f'<Types xmlns="{CT}"><Override PartName="/word/document.xml" ContentType="{DOTX_TYPE}"/></Types>')
    mem = BytesIO()
    with ZipFile(mem,"w") as out:
        out.writestr("[Content_Types].xml",types)
        out.writestr("word/document.xml",xml)
        out.writestr("word/styles.xml","<unchanged/>")
    return mem.getvalue()


def test_complete_two_member_package_preserves_other_parts_and_prefixes():
    raw = _template()
    out = build_offline_two_member_docx(
        template=raw, expected_sha256=sha256(raw).hexdigest(), member_count=2,
    )
    with ZipFile(BytesIO(out)) as z:
        assert z.testzip() is None
        assert z.read("word/styles.xml") == b"<unchanged/>"
        assert DOCX_TYPE.encode() in z.read("[Content_Types].xml")
        xml = z.read("word/document.xml")
        assert b"<w:document" in xml and b'xmlns:w14=' in xml
        assert b'mc:Ignorable="w14"' in xml
        root = ET.fromstring(xml)
        paragraphs = [
            "".join(t.text or "" for t in p.iter(f"{{{W}}}t"))
            for p in root.iter(f"{{{W}}}p")
        ]
        assert paragraphs == [
            "Hà Nội, ngày    tháng    năm ",
            "Trưởng đoàn", "Thành viên thứ hai", "Điều khoản tiếp theo",
        ]
        assert sorted(b.get(f"{{{W}}}id") for b in root.iter(f"{{{W}}}bookmarkStart")) == sorted(
            b.get(f"{{{W}}}id") for b in root.iter(f"{{{W}}}bookmarkEnd")
        )


@pytest.mark.parametrize("count", [0, 1, 3, 4, True])
def test_count_other_than_two_fails_closed(count):
    template = _template()
    with pytest.raises(QdKtOfflineTeamPackageBlocked, match="QDKT_TWO_MEMBER_ONLY"):
        build_offline_two_member_docx(template=template, expected_sha256=sha256(template).hexdigest(), member_count=count)


def test_bad_checksum_fails_closed():
    with pytest.raises(QdKtOfflineTeamPackageBlocked, match="QDKT_OFFLINE_TWO_MEMBER_PACKAGE_INVALID"):
        build_offline_two_member_docx(template=_template(), expected_sha256="0" * 64, member_count=2)


def test_unproven_third_bookmark_fails_closed():
    raw = _template()
    with ZipFile(BytesIO(raw)) as src:
        target = BytesIO()
        with ZipFile(target, "w") as dst:
            for item in src.infolist():
                source = src.read(item.filename)
                if item.filename == "word/document.xml":
                    source = source.replace(b'w:name="TT3Del"', b'w:name="unknown"')
                dst.writestr(item, source)
    broken = target.getvalue()
    with pytest.raises(QdKtOfflineTeamPackageBlocked, match="QDKT_OFFLINE_TWO_MEMBER_PACKAGE_INVALID"):
        build_offline_two_member_docx(template=broken, expected_sha256=sha256(broken).hexdigest(), member_count=2)
