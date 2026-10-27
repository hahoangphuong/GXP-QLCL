"""UAT preparation never equals Word execution or legal-template adoption."""
from pathlib import Path

import pytest

from tools.prepare_qdkt_word_uat import prepare_package
from tools import prepare_qdkt_word_uat as tool
from test_inspection_qd_kt_dotx_binary_audit import dotx_bytes, asset
from backend.app.document.inspection_qd_kt_dotx_binary_audit import inspect_supplied_qdkt_dotx_set


def test_synthetic_package_exercises_copy_and_manifest_without_claiming_word_uat(tmp_path, monkeypatch):
    directory = tmp_path / "synthetic-templates"
    directory.mkdir()
    data = dotx_bytes(b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>')
    assets = tuple(asset(data, kind) for kind in ("GLP", "GMP", "GMPbb", "GSP"))
    for row in assets:
        (directory / row.filename).write_bytes(data)
    monkeypatch.setattr(tool, "load_inspection_qd_kt_template_assets", lambda: assets)
    monkeypatch.setattr(tool, "inspect_supplied_qdkt_dotx_set", lambda path: inspect_supplied_qdkt_dotx_set(path, assets=assets))
    manifest = prepare_package(template_directory=directory, output=tmp_path / "output")
    assert manifest["execution"] == "NOT_EXECUTED"
    assert all(row["candidate_approved"] is False for row in manifest["templates"])
    assert all(row["copy_sha256"] == row["source_sha256"] for row in manifest["templates"])
    assert all(row["candidate_sha256"] is None for row in manifest["templates"])


def test_missing_source_fails_before_output_creation(tmp_path):
    output = tmp_path / "package"
    with pytest.raises(ValueError):
        prepare_package(template_directory=tmp_path / "missing", output=output)
    assert not output.exists()


def test_real_local_templates_prepare_exact_copies_without_uat_claim(tmp_path):
    source = Path("legacy/Templates")
    if not source.is_dir():
        pytest.skip("ignored authoritative originals unavailable in checkout")
    output = tmp_path / "package"
    manifest = prepare_package(template_directory=source, output=output)
    assert manifest["execution"] == "NOT_EXECUTED"
    assert manifest["decision"] == "UNDECIDED"
    assert manifest["ready_to_render"] is False
    assert len(manifest["templates"]) == 4
    for row in manifest["templates"]:
        assert row["copy_sha256"] == row["source_sha256"]
        assert row["uat_result"] == "NOT_EXECUTED"
        assert row["candidate_approved"] is False
        assert row["source_dossier_prose_locations"]
        assert (output / row["source_filename"]).read_bytes() == (source / row["source_filename"]).read_bytes()
    with pytest.raises(FileExistsError):
        prepare_package(template_directory=source, output=output)
