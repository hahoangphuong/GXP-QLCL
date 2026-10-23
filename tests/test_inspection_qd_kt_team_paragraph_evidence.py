"""QĐKT physical team paragraphs: synthetic positive/negative gates."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

import pytest

from backend.app.document.inspection_qd_kt_team_paragraph_evidence import (
    inspect_qdkt_team_paragraphs,
)
from backend.app.document.inspection_qd_kt_physical_evidence import QdKtPhysicalEvidenceError

N = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _template(path, *, role2="Thành viên", controls_together=True):
    def line(id, name, text, extra=""):
        return (
            f'<w:p><w:bookmarkStart w:id="{id}" w:name="{name}"/>'
            f'<w:r><w:t>{text}</w:t></w:r>'
            f'<w:bookmarkEnd w:id="{id}"/>{extra}</w:p>'
        )
    third = '<w:bookmarkStart w:id="4" w:name="TT3Del"/><w:bookmarkEnd w:id="4"/>' if controls_together else ''
    third += '<w:bookmarkStart w:id="5" w:name="TT_ext"/><w:bookmarkEnd w:id="5"/>' if controls_together else ''
    xml = (
        f'<w:document xmlns:w="{N}"><w:body>'
        + line(1, "TT1x", "A - Trưởng đoàn;")
        + line(2, "TT2x", f"B - {role2};")
        + line(3, "TT3x", "C - Thành viên;", third)
        + ("" if controls_together else line(4, "TT3Del", "X") + line(5, "TT_ext", "Y"))
        + '</w:body></w:document>'
    )
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("gxp,role2", [
    ("GMP", "Thành viên"), ("GLP", "Thành viên"),
    ("GMPbb", "Thành viên"), ("GSP", "Thư ký"),
])
def test_template_role_labels_without_authorizing_render(gxp, role2):
    with TemporaryDirectory() as root:
        path = Path(root) / "template.dotx"
        digest = _template(path, role2=role2)
        asset = type("Asset", (), {"checksum_sha256": digest})()
        with patch(
            "backend.app.document.inspection_qd_kt_physical_evidence.get_inspection_qd_kt_template_asset",
            return_value=asset,
        ):
            original = path.read_bytes()
            result = inspect_qdkt_team_paragraphs(path, gxp_type=gxp)
            assert result.physical_role_labels_verified
            assert result.third_member_controls_share_paragraph
            assert not result.member_source_mapping_verified
            assert not result.safe_to_delete_third_member_paragraph
            assert not result.ready_to_render
            assert original == path.read_bytes()


@pytest.mark.parametrize("role2,controls,code", [
    ("Thư ký", True, "TEAM_ROLE_LABEL_MISMATCH"),
    ("Thành viên", False, "THIRD_MEMBER_CONTROL_LAYOUT_MISMATCH"),
])
def test_mismatched_template_fails_closed(role2, controls, code):
    with TemporaryDirectory() as root:
        path = Path(root) / "template.dotx"
        digest = _template(path, role2=role2, controls_together=controls)
        asset = type("Asset", (), {"checksum_sha256": digest})()
        with patch(
            "backend.app.document.inspection_qd_kt_physical_evidence.get_inspection_qd_kt_template_asset",
            return_value=asset,
        ):
            with pytest.raises(QdKtPhysicalEvidenceError, match=code):
                inspect_qdkt_team_paragraphs(path, gxp_type="GMP")
