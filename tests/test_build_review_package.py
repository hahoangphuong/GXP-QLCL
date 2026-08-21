from __future__ import annotations

import subprocess
from pathlib import Path
from zipfile import ZipFile

from tools.build_review_package import build_review_package, collect_review_package_members


def test_collect_review_package_members_excludes_sensitive_and_generated_paths(monkeypatch, tmp_path: Path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "legacy").mkdir()
    (tmp_path / "legacy" / "secret.xlsb").write_text("legacy\n", encoding="utf-8")
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "run.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("SECRET=\n", encoding="utf-8")

    monkeypatch.setattr(
        "tools.build_review_package._git_ls_files",
        lambda root: [
            Path("backend/app.py"),
            Path("legacy/secret.xlsb"),
            Path("artifacts/run.json"),
            Path(".env"),
            Path(".env.example"),
        ],
    )

    members = collect_review_package_members(tmp_path)

    assert [item.as_posix() for item in members] == [".env.example", "backend/app.py"]


def test_build_review_package_writes_deterministic_zip(monkeypatch, tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "note.md").write_bytes(b"hello\n")

    monkeypatch.setattr(
        "tools.build_review_package._git_ls_files",
        lambda root: [Path("docs/note.md")],
    )

    output_path = tmp_path / "dist" / "review.zip"
    build_review_package(tmp_path, output_path)

    with ZipFile(output_path) as archive:
        names = archive.namelist()
        assert names == ["docs/note.md"]
        info = archive.getinfo("docs/note.md")
        assert info.date_time == (2026, 8, 20, 0, 0, 0)
        assert archive.read("docs/note.md") == b"hello\n"


def test_collect_review_package_members_falls_back_when_git_ls_files_fails(monkeypatch, tmp_path: Path):
    (tmp_path / "README.md").write_text("readme\n", encoding="utf-8")

    def _raise(root: Path) -> list[Path]:
        raise subprocess.CalledProcessError(returncode=1, cmd=["git", "ls-files"])

    monkeypatch.setattr("tools.build_review_package._git_ls_files", _raise)

    members = collect_review_package_members(tmp_path)

    assert [item.as_posix() for item in members] == ["README.md"]


def test_collect_review_package_members_falls_back_when_git_ls_files_is_empty(monkeypatch, tmp_path: Path):
    (tmp_path / "README.md").write_text("readme\n", encoding="utf-8")

    monkeypatch.setattr("tools.build_review_package._git_ls_files", lambda root: [])

    members = collect_review_package_members(tmp_path)

    assert [item.as_posix() for item in members] == ["README.md"]
