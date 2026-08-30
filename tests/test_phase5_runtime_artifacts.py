import json
from pathlib import Path
import shutil
import subprocess

from backend.app.document.runtime_artifacts import (
    PHASE5_RUNTIME_ARTIFACTS,
    assert_required_phase5_runtime_artifacts_exist,
)
from tools import build_phase5_template_registry as template_registry


ROOT = Path(__file__).resolve().parents[1]


def _extract_git_archive(export_root: Path) -> Path:
    export_root.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    for relative_path in completed.stdout.splitlines():
        if not relative_path:
            continue
        source = ROOT / relative_path
        target = export_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return export_root


def test_phase5_runtime_artifacts_are_packaged_in_clean_git_archive(tmp_path: Path) -> None:
    export_root = _extract_git_archive(tmp_path / "release")

    assert_required_phase5_runtime_artifacts_exist(export_root / "artifacts")
    for relative_path in PHASE5_RUNTIME_ARTIFACTS:
        assert export_root.joinpath("artifacts", relative_path).is_file(), relative_path
    assert not export_root.joinpath("artifacts", "phase5", "template_seed.db").exists()


def test_build_phase5_template_registry_regenerates_from_tracked_document_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    raw_contract = ROOT / "artifacts" / "phase5" / "document_contract.json"
    output_json = tmp_path / "template_registry.curated.json"
    output_md = tmp_path / "template_registry.curated.md"
    monkeypatch.setattr(template_registry, "RAW_CONTRACT_PATH", raw_contract)
    monkeypatch.setattr(template_registry, "OUTPUT_JSON", output_json)
    monkeypatch.setattr(template_registry, "OUTPUT_MD", output_md)

    template_registry.main()

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert len(payload["entries"]) == len(template_registry.ENTRY_DEFINITIONS)
    assert any(entry["family_code"] == "CERTIFICATE_ISSUANCE_WORD" for entry in payload["entries"])
    assert output_md.is_file()


def test_phase5_runtime_artifact_helper_fails_closed_when_export_is_incomplete(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    phase5_root = artifacts_root / "phase5"
    phase5_root.mkdir(parents=True, exist_ok=True)
    for relative_path in PHASE5_RUNTIME_ARTIFACTS:
        target = artifacts_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")
    missing_path = phase5_root / "template_registry.curated.json"
    missing_path.unlink()

    try:
        assert_required_phase5_runtime_artifacts_exist(artifacts_root)
    except FileNotFoundError as exc:
        assert "template_registry.curated.json" in str(exc)
    else:
        raise AssertionError("Expected FileNotFoundError for missing phase5 runtime artifact")
