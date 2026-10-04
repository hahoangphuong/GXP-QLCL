from __future__ import annotations

from pathlib import Path

from tools.check_repo_hygiene import ALLOWED_PATH_PATTERNS, FORBIDDEN_CONTENT_PATTERNS, FORBIDDEN_PATH_PATTERNS
from tools import check_repo_hygiene


def test_repo_hygiene_catches_forbidden_paths():
    assert any(pattern.search("legacy/file.xlsb") for pattern in FORBIDDEN_PATH_PATTERNS)
    assert any(pattern.search("frontend/dist/index.html") for pattern in FORBIDDEN_PATH_PATTERNS)
    assert not any(pattern.search("artifacts/a3/case_lifecycle_sweep.json") for pattern in FORBIDDEN_PATH_PATTERNS)


def test_repo_hygiene_allows_example_env_files():
    assert any(pattern.search("backend/.env.cloudrun.example") for pattern in ALLOWED_PATH_PATTERNS)
    assert any(pattern.search(".env.example") for pattern in ALLOWED_PATH_PATTERNS)


def test_repo_hygiene_has_basic_secret_detection():
    assert any(pattern.search("-----BEGIN PRIVATE KEY-----") for pattern in FORBIDDEN_CONTENT_PATTERNS)


def test_repo_hygiene_fails_when_git_has_no_tracked_files(monkeypatch, capsys):
    monkeypatch.setattr(check_repo_hygiene, "_git_ls_files", lambda root: [])

    exit_code = check_repo_hygiene.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "no tracked files" in captured.err


def _write_allowlist(root: Path, *entries: str) -> None:
    allowlist = root / check_repo_hygiene.TRACKED_ARTIFACTS_ALLOWLIST
    allowlist.parent.mkdir(parents=True)
    allowlist.write_text("\n".join(entries) + "\n", encoding="utf-8")


def test_repo_hygiene_allows_historical_and_a3_artifacts(tmp_path):
    historical = Path("artifacts/legacy_audit/inspection_qd_kt_vba_trace.json")
    a3 = Path("artifacts/a3/case_lifecycle_sweep.json")
    _write_allowlist(tmp_path, historical.as_posix(), a3.as_posix())

    assert check_repo_hygiene.check_tracked_files(tmp_path, [historical, a3]) == []


def test_repo_hygiene_rejects_new_nonallowlisted_artifact(tmp_path):
    approved = Path("artifacts/a3/case_lifecycle_sweep.json")
    unexpected = Path("artifacts/a4/unreviewed.json")
    _write_allowlist(tmp_path, approved.as_posix())

    violations = check_repo_hygiene.check_tracked_files(tmp_path, [approved, unexpected])

    assert violations == ["tracked artifact is not allowlisted: artifacts/a4/unreviewed.json"]


def test_repo_hygiene_rejects_missing_artifact_allowlist(tmp_path):
    violations = check_repo_hygiene.check_tracked_files(
        tmp_path,
        [Path("artifacts/a3/case_lifecycle_sweep.json")],
    )

    assert violations == [
        "tracked artifact allowlist is missing: tools/repo_hygiene_tracked_artifacts_allowlist.txt",
        "tracked artifact is not allowlisted: artifacts/a3/case_lifecycle_sweep.json",
    ]


def test_repo_hygiene_preserves_non_artifact_path_rules(tmp_path):
    _write_allowlist(tmp_path)

    violations = check_repo_hygiene.check_tracked_files(tmp_path, [Path("frontend/dist/index.html")])

    assert violations == ["forbidden tracked path: frontend/dist/index.html"]


def test_repo_hygiene_rejects_malformed_duplicate_and_stale_allowlist_entries(tmp_path):
    _write_allowlist(
        tmp_path,
        "outside-artifacts.json",
        "artifacts/a3/case_lifecycle_sweep.json",
        "artifacts/a3/case_lifecycle_sweep.json",
        "artifacts/stale.json",
    )

    violations = check_repo_hygiene.check_tracked_files(
        tmp_path,
        [Path("artifacts/a3/case_lifecycle_sweep.json")],
    )

    assert "malformed tracked artifact allowlist entry at line 1: 'outside-artifacts.json'" in violations
    assert "duplicate tracked artifact allowlist entry: artifacts/a3/case_lifecycle_sweep.json" in violations
    assert "tracked artifact allowlist entry is stale: artifacts/stale.json" in violations
