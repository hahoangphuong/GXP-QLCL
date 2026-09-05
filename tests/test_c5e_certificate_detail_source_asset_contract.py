from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from backend.app.document.c5e_certificate_detail_source_asset_contract import (
    CertificateDetailSourceAsset,
    CertificateDetailSourceAssetContractError,
    load_source_asset_registry,
    resolve_source_asset,
    verify_source_asset_bytes,
)


def test_default_registry_is_exact_six_asset_matrix():
    assets = load_source_asset_registry()
    assert len(assets) == 6
    assert {(a.source_variant, a.gxp_type) for a in assets} == {
        ("certificate_9", "GMP"),
        ("certificate_9", "GLP"),
        ("certificate_9", "GSP"),
        ("appendix_z3", "GMP"),
        ("appendix_z3", "GLP"),
        ("appendix_z3", "GSP"),
    }
    assert all(a.gxp_type != "GDP" for a in assets)


def test_resolve_exact_gmp_glp_gsp_assets():
    assert resolve_source_asset(source_variant="certificate_9", gxp_type="GMP").filename == "9. PhamviGMP.docx"
    assert resolve_source_asset(source_variant="certificate_9", gxp_type="GLP").filename == "9. PhamviGLP.docx"
    assert resolve_source_asset(source_variant="certificate_9", gxp_type="GSP").filename == "9. PhamviGSP.docx"
    assert resolve_source_asset(source_variant="appendix_z3", gxp_type="GMP").filename == "z3. PhamviGMP.docx"


def test_gdp_is_explicitly_rejected():
    with pytest.raises(CertificateDetailSourceAssetContractError, match="GDP"):
        resolve_source_asset(source_variant="certificate_9", gxp_type="GDP")


def test_registry_with_gdp_fails_closed(tmp_path):
    source = json.loads(
        Path("backend/app/document/c5e_certificate_detail_source_assets.json").read_text(encoding="utf-8")
    )
    source["assets"].append({
        "source_variant": "certificate_9",
        "gxp_type": "GDP",
        "filename": "9. PhamviGDP.docx",
        "sha256": "0" * 64,
    })
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(CertificateDetailSourceAssetContractError):
        load_source_asset_registry(path)


def test_source_asset_bytes_are_checksum_guarded():
    payload = b"source asset"
    asset = CertificateDetailSourceAsset(
        source_variant="certificate_9",
        gxp_type="GMP",
        filename="9. PhamviGMP.docx",
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    verify_source_asset_bytes(asset, payload)
    with pytest.raises(CertificateDetailSourceAssetContractError, match="checksum mismatch"):
        verify_source_asset_bytes(asset, b"changed")
