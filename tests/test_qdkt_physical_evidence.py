"""Adversarial offline QĐKT physical evidence checks; no real DOTX in Git."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

import pytest

from backend.app.document.inspection_qd_kt_physical_evidence import (
    QdKtPhysicalEvidenceError,
    inspect_qdkt_physical_template,
)

NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _fixture(path: Path, *, year: int, end: bool = True) -> str:
    xml = (
        f'<w:document xmlns:w="{NS}"><w:body>'
        f'<w:p><w:r><w:t>Hà Nội, ngày    tháng    năm {year}</w:t></w:r></w:p>'
        '<w:bookmarkStart w:id="3" w:name="Tencoso1"/>'
        + ('<w:bookmarkEnd w:id="3"/>' if end else '')
        + '</w:body></w:document>'
    )
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return sha256(path.read_bytes()).hexdigest()


def test_valid_template_is_read_only_and_not_render_ready():
    with TemporaryDirectory() as temp:
        path = Path(temp) / "sample.dotx"
        digest = _fixture(path, year=2026)
        asset = type("Asset", (), {"checksum_sha256": digest})()
        with patch(
            "backend.app.document.inspection_qd_kt_physical_evidence.get_inspection_qd_kt_template_asset",
            return_value=asset,
        ):
            before = path.read_bytes()
            result = inspect_qdkt_physical_template(path, gxp_type="GMP")
            assert path.read_bytes() == before
            assert result["bookmark_names"] == ["Tencoso1"]
            assert result["fulldate_bookmark_present"] is False
            assert result["date_line_candidates"] == ["Hà Nội, ngày    tháng    năm 2026"]
            assert result["ready_to_render"] is False
            assert result["visual_render_verified"] is False


def test_checksum_drift_fails_closed():
    with TemporaryDirectory() as temp:
        path = Path(temp) / "sample.dotx"
        _fixture(path, year=2026)
        asset = type("Asset", (), {"checksum_sha256": "0" * 64})()
        with patch(
            "backend.app.document.inspection_qd_kt_physical_evidence.get_inspection_qd_kt_template_asset",
            return_value=asset,
        ):
            with pytest.raises(QdKtPhysicalEvidenceError, match="TEMPLATE_SHA256_MISMATCH"):
                inspect_qdkt_physical_template(path, gxp_type="GLP")


def test_orphaned_bookmark_end_fails_closed():
    with TemporaryDirectory() as temp:
        path = Path(temp) / "sample.dotx"
        digest = _fixture(path, year=2021, end=False)
        asset = type("Asset", (), {"checksum_sha256": digest})()
        with patch(
            "backend.app.document.inspection_qd_kt_physical_evidence.get_inspection_qd_kt_template_asset",
            return_value=asset,
        ):
            with pytest.raises(QdKtPhysicalEvidenceError, match="BOOKMARK_END_MISMATCH"):
                inspect_qdkt_physical_template(path, gxp_type="GMPbb")
