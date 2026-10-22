"""Synthetic, offline regression for active release attestation."""
import json
from pathlib import Path

import pytest

from tools.audit_active_release_baseline_readonly import BaselineBlocked, audit_active_release

SHA = "a" * 40


def _baseline(tmp_path: Path) -> Path:
    root = tmp_path / "gxp"
    root.mkdir()
    payload = {"current_sha": SHA, "current_short_sha": SHA[:7], "branch": "main"}
    for key, link, family, artifact in (
        ("backend_release_dir", "current-backend", "backend-releases", None),
        ("backend_venv_dir", "current-venv", "backend-venvs", "bin/python"),
        ("frontend_release_dir", "frontend-dist", "frontend-releases", "index.html"),
    ):
        release = root / family / SHA
        release.mkdir(parents=True)
        if artifact:
            path = release / artifact
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("test", encoding="utf-8")
        (root / link).symlink_to(release, target_is_directory=True)
        payload[key] = str(release)
    (root / "current-release.json").write_text(json.dumps(payload), encoding="utf-8")
    return root


def test_valid_active_release_is_attested_without_mutation(tmp_path):
    root = _baseline(tmp_path)
    before = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
    report = audit_active_release(root, expected_sha=SHA)
    assert report["status"] == "ACTIVE_RELEASE_BASELINE_MATCH"
    assert report["rollback_restore_verified"] is False
    assert report["database_mutation_authorized"] is False
    assert sorted(str(p.relative_to(root)) for p in root.rglob("*")) == before


@pytest.mark.parametrize("defect", [
    "wrong_expected_sha", "wrong_metadata_sha", "wrong_short_sha",
    "wrong_metadata_path", "wrong_active_symlink", "missing_link",
    "missing_frontend_index", "missing_venv_python", "broken_symlink",
    "missing_metadata", "metadata_symlink", "invalid_metadata",
])
def test_mismatches_fail_closed(tmp_path, defect):
    root = _baseline(tmp_path)
    metadata = root / "current-release.json"
    data = json.loads(metadata.read_text())
    if defect == "wrong_expected_sha":
        expected_sha = "b" * 40
    else:
        expected_sha = SHA
    if defect == "wrong_metadata_sha":
        data["current_sha"] = "b" * 40
    elif defect == "wrong_short_sha":
        data["current_short_sha"] = "abcdefg"
    elif defect == "wrong_metadata_path":
        data["frontend_release_dir"] = "/unrelated"
    if defect in {"wrong_metadata_sha", "wrong_short_sha", "wrong_metadata_path"}:
        metadata.write_text(json.dumps(data))
    if defect in {"wrong_active_symlink", "missing_link", "broken_symlink"}:
        link = root / "frontend-dist"
        link.unlink()
        if defect == "wrong_active_symlink":
            other = root / "frontend-releases" / ("b" * 40)
            other.mkdir()
            link.symlink_to(other, target_is_directory=True)
        elif defect == "broken_symlink":
            link.symlink_to(root / "missing", target_is_directory=True)
    if defect == "missing_frontend_index":
        (root / "frontend-releases" / SHA / "index.html").unlink()
    if defect == "missing_venv_python":
        (root / "backend-venvs" / SHA / "bin/python").unlink()
    if defect == "missing_metadata":
        metadata.unlink()
    if defect == "metadata_symlink":
        metadata.unlink()
        src = root / "other.json"
        src.write_text(json.dumps(data))
        metadata.symlink_to(src)
    if defect == "invalid_metadata":
        metadata.write_text("{invalid")
    with pytest.raises(BaselineBlocked):
        audit_active_release(root, expected_sha=expected_sha)


@pytest.mark.parametrize("bad", ["main", "../foo", "", "A" * 40])
def test_non_exact_sha_rejected(tmp_path, bad):
    root = _baseline(tmp_path)
    with pytest.raises(BaselineBlocked, match="INVALID_EXPECTED_SHA"):
        audit_active_release(root, expected_sha=bad)
