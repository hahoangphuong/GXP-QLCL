from __future__ import annotations

from pathlib import Path
import subprocess

from tools.check_repo_hygiene import ALLOWED_PATH_PATTERNS, FORBIDDEN_CONTENT_PATTERNS, FORBIDDEN_PATH_PATTERNS
from tools import check_repo_hygiene


def test_repo_hygiene_catches_forbidden_paths():
    assert any(pattern.search("legacy/file.xlsb") for pattern in FORBIDDEN_PATH_PATTERNS)
    assert any(pattern.search("frontend/dist/index.html") for pattern in FORBIDDEN_PATH_PATTERNS)


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
