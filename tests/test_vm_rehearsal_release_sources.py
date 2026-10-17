"""Rehearsal candidate may combine only reviewed backend and frontend trees.

Entire suite uses local disposable Git fixtures; it never connects to VM,
provider, NAS, rehearsal or any database.
"""

from pathlib import Path
import subprocess

import pytest

from tools.verify_rehearsal_release_sources import (
    RehearsalReleaseSourceError,
    verify_rehearsal_release_sources,
)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, text=True, capture_output=True,
    ).stdout.strip()


def fixture_commits(tmp_path: Path) -> tuple[Path, str, str, str, str]:
    repo = tmp_path / "synthetic-release"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Synthetic Review")
    git(repo, "config", "user.email", "ci@example.invalid")
    (repo / "backend").mkdir()
    (repo / "frontend").mkdir()
    (repo / "backend" / "app.py").write_text("backend-v1\n", encoding="utf-8")
    (repo / "frontend" / "App.tsx").write_text("old-ui\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "reviewed backend baseline")
    backend = git(repo, "rev-parse", "HEAD")

    git(repo, "checkout", "-qb", "codex-approved")
    (repo / "frontend" / "App.tsx").write_text("approved-ui\n", encoding="utf-8")
    (repo / "frontend" / "More.tsx").write_text("new-ui\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "reviewed frontend")
    frontend = git(repo, "rev-parse", "HEAD")

    git(repo, "checkout", "-qb", "integrated", backend)
    git(repo, "restore", "--source", frontend, "--", "frontend")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "integrate reviewed frontend without backend mutation")
    integrated = git(repo, "rev-parse", "HEAD")

    (repo / "backend" / "app.py").write_text("unauthorized-backend-change\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "tamper with reviewed backend")
    tampered = git(repo, "rev-parse", "HEAD")
    return repo, backend, frontend, integrated, tampered


def test_accepts_exact_reviewed_backend_and_frontend_as_single_commit(tmp_path: Path):
    repo, backend, frontend, integrated, _ = fixture_commits(tmp_path)
    before = git(repo, "status", "--porcelain")
    result = verify_rehearsal_release_sources(
        repo, target_sha=integrated, approved_backend_sha=backend,
        approved_frontend_sha=frontend,
    )
    assert result["status"] == "REHEARSAL_SOURCE_EXACT_MATCH"
    assert result["target_commit"] == integrated
    assert result["approved_backend_commit"] == backend
    assert result["approved_frontend_commit"] == frontend
    assert result["non_frontend_changed_paths"] == 0
    assert result["frontend_tree"] == git(repo, "rev-parse", f"{frontend}:frontend")
    assert git(repo, "status", "--porcelain") == before


def test_rejects_unreviewed_backend_change_even_with_correct_frontend(tmp_path: Path):
    repo, backend, frontend, _, tampered = fixture_commits(tmp_path)
    with pytest.raises(RehearsalReleaseSourceError, match="non-frontend"):
        verify_rehearsal_release_sources(
            repo, target_sha=tampered, approved_backend_sha=backend,
            approved_frontend_sha=frontend,
        )


def test_rejects_unintegrated_frontend(tmp_path: Path):
    repo, backend, frontend, _, _ = fixture_commits(tmp_path)
    with pytest.raises(RehearsalReleaseSourceError, match="frontend"):
        verify_rehearsal_release_sources(
            repo, target_sha=backend, approved_backend_sha=backend,
            approved_frontend_sha=frontend,
        )


def test_rejects_wrong_backend_ancestry(tmp_path: Path):
    repo, backend, frontend, _, _ = fixture_commits(tmp_path)
    # A reviewed frontend commit is not itself a descendant of a fake
    # unrelated backend SHA; fail before claiming a clean release lineage.
    with pytest.raises(RehearsalReleaseSourceError, match="ancestor"):
        verify_rehearsal_release_sources(
            repo, target_sha=backend, approved_backend_sha=frontend,
            approved_frontend_sha=backend,
        )


@pytest.mark.parametrize("bad", ["", "main", "1234567", "z" * 40, "0" * 40])
def test_rejects_missing_invalid_or_unavailable_source_ids(tmp_path: Path, bad: str):
    repo, backend, frontend, integrated, _ = fixture_commits(tmp_path)
    for approved_backend, approved_frontend, target in (
        (bad, frontend, integrated),
        (backend, bad, integrated),
        (backend, frontend, bad),
    ):
        with pytest.raises(RehearsalReleaseSourceError):
            verify_rehearsal_release_sources(
                repo, target_sha=target, approved_backend_sha=approved_backend,
                approved_frontend_sha=approved_frontend,
            )


def test_rehearsal_release_requires_both_approvals_before_mutating_vm():
    root = Path(__file__).resolve().parents[1]
    wrapper = (root / "infra/vm/deploy_rehearsal.sh").read_text(encoding="utf-8")
    deploy = (root / "infra/vm/deploy_prod.sh").read_text(encoding="utf-8")
    assert "REHEARSAL_APPROVED_BACKEND_SHA" in wrapper
    assert "REHEARSAL_APPROVED_FRONTEND_SHA" in wrapper
    assert 'readonly REHEARSAL_BACKEND_OPERATOR_SHA=' in wrapper
    assert wrapper.index('readonly REHEARSAL_BACKEND_OPERATOR_SHA=') < wrapper.index(
        'load_runtime_env "${CANONICAL_RUNTIME_ENV_FILE}"'
    )
    assert 'export VM_APPROVED_BACKEND_SOURCE_SHA="${REHEARSAL_BACKEND_OPERATOR_SHA}"' in wrapper
    assert 'readonly REHEARSAL_BACKEND_GATE_SHA=' in deploy
    assert deploy.index('readonly REHEARSAL_BACKEND_GATE_SHA=') < deploy.index(
        'load_runtime_env "${RUNTIME_ENV_FILE}"'
    )
    assert "tools/verify_rehearsal_release_sources.py" in deploy
    assert '--approved-backend-sha "${REHEARSAL_BACKEND_GATE_SHA}"' in deploy
    assert '--approved-frontend-sha "${REHEARSAL_FRONTEND_GATE_SHA}"' in deploy
    assert deploy.index("tools/verify_rehearsal_release_sources.py") < deploy.index(
        'CURRENT_STAGE="release_directories"'
    )
    assert deploy.index('CURRENT_STAGE="release_directories"') < deploy.index(
        'CURRENT_STAGE="database_backup"'
    )
