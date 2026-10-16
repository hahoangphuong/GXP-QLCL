"""Rehearsal release must ship the actually approved tracked frontend tree."""

from pathlib import Path
import subprocess

import pytest

from tools.verify_rehearsal_frontend_source import (
    FrontendReleaseSourceError, verify_frontend_source_equivalence,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _three_commits(tmp_path: Path) -> tuple[Path, str, str, str]:
    repo = tmp_path / "synthetic"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Synthetic CI")
    _git(repo, "config", "user.email", "ci@example.invalid")
    frontend = repo / "frontend" / "src"
    frontend.mkdir(parents=True)
    (frontend / "App.tsx").write_text("export const revision = 'approved';\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "approved frontend")
    approved = _git(repo, "rev-parse", "HEAD")

    (repo / "backend.txt").write_text("backend-only change\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "change backend only")
    matching = _git(repo, "rev-parse", "HEAD")

    (frontend / "App.tsx").write_text("export const revision = 'stale-or-different';\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "change frontend")
    differing = _git(repo, "rev-parse", "HEAD")
    assert len({approved, matching, differing}) == 3
    return repo, approved, matching, differing


def test_gate_accepts_exact_frontend_tree_despite_backend_changes(tmp_path: Path):
    repo, approved, matching, _ = _three_commits(tmp_path)
    before = _git(repo, "status", "--porcelain")
    result = verify_frontend_source_equivalence(
        repo, target_sha=matching, approved_frontend_sha=approved
    )
    assert result["status"] == "FRONTEND_TREE_EXACT_MATCH"
    assert result["target_commit"] == matching
    assert result["approved_frontend_commit"] == approved
    assert len(result["frontend_tree"]) == 40
    assert _git(repo, "status", "--porcelain") == before


def test_gate_rejects_stale_or_different_target_frontend(tmp_path: Path):
    repo, approved, _, differing = _three_commits(tmp_path)
    with pytest.raises(FrontendReleaseSourceError, match="CI runner overlay is not deployable"):
        verify_frontend_source_equivalence(
            repo, target_sha=differing, approved_frontend_sha=approved
        )


@pytest.mark.parametrize("bad_sha", ["", "main", "deadbeef", "../approved", "z" * 40])
def test_gate_fails_closed_without_exact_approved_commit(tmp_path: Path, bad_sha: str):
    repo, approved, matching, _ = _three_commits(tmp_path)
    for target, source in ((matching, bad_sha), (bad_sha, approved)):
        with pytest.raises(FrontendReleaseSourceError):
            verify_frontend_source_equivalence(
                repo, target_sha=target, approved_frontend_sha=source
            )


def test_vm_rehearsal_invokes_mandatory_gate_before_any_release_stage():
    root = Path(__file__).resolve().parents[1]
    wrapper = (root / "infra/vm/deploy_rehearsal.sh").read_text(encoding="utf-8")
    deployment = (root / "infra/vm/deploy_prod.sh").read_text(encoding="utf-8")
    assert 'REHEARSAL_APPROVED_FRONTEND_SHA' in wrapper
    assert 'export VM_REQUIRE_APPROVED_FRONTEND_TREE=1' in wrapper
    assert 'export VM_APPROVED_FRONTEND_SOURCE_SHA=' in wrapper
    assert 'VM_RUNTIME_ENV_FILE="${REHEARSAL_RUNTIME_ENV_FILE}" "${SCRIPT_DIR}/deploy_prod.sh"' in wrapper
    assert 'tools/verify_rehearsal_frontend_source.py' in deployment
    assert 'VM_REQUIRE_APPROVED_FRONTEND_TREE' in deployment
    assert deployment.index('tools/verify_rehearsal_frontend_source.py') < deployment.index('CURRENT_STAGE="release_directories"')
    assert deployment.index('CURRENT_STAGE="release_directories"') < deployment.index('CURRENT_STAGE="database_backup"')
