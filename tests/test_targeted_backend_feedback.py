"""Safety and scope regression for opt-in targeted backend feedback."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import targeted_backend_feedback as feedback


def test_ci_preset_selects_real_expected_tests():
    paths = feedback.select_tests("ci")
    assert "tests/test_ci_pytest_shards.py" in paths
    assert "tests/test_rehearsal_ci_required_results.py" in paths
    assert paths == tuple(sorted(set(paths)))


def test_reassessment_preset_includes_all_three_postgres_owner_regressions():
    selected = feedback.select_tests("reassessment")
    assert "tests/test_reassessment_cached_production_line_postgres.py" in selected
    assert "tests/test_reassessment_cached_source_scope_postgres.py" in selected
    assert "tests/test_reassessment_scope_snapshot_postgres.py" in selected


def test_missing_pattern_is_not_silently_skipped(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    with pytest.raises(ValueError, match="missing"):
        feedback.select_tests("reassessment", root=tmp_path)


@pytest.mark.parametrize("url", [
    None,
    "postgresql+psycopg://postgres:postgres@cloud-db:5432/gxp_qlcl_test",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/gxp_qlcl",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/gxp_qlcl_test",
    "postgresql://postgres:postgres@localhost:5432/gxp_qlcl_test",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/gxp_legacy_rehearsal",
])
def test_targeted_runner_rejects_non_disposable_database(url):
    with pytest.raises(ValueError, match="STOP"):
        feedback.require_disposable_postgres(url)


def test_targeted_runner_allows_exact_loopback_disposable_database():
    feedback.require_disposable_postgres(
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/gxp_qlcl_test"
    )


def test_list_mode_never_executes_pytest(monkeypatch: pytest.MonkeyPatch):
    def bad_run(*args, **kwargs):
        pytest.fail("List mode must never run tests.")

    monkeypatch.setattr(feedback.subprocess, "run", bad_run)
    assert feedback.main(["--suite", "ci", "--list"]) == 0


def test_execute_mode_runs_only_selected_python_files(monkeypatch: pytest.MonkeyPatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(feedback.subprocess, "run", fake_run)
    assert feedback.main(["--suite", "ci", "--execute"]) == 7
    args, kwargs = calls[0]
    assert args[:4] == [feedback.sys.executable, "-m", "pytest", "-q"]
    assert set(args[4:]) == set(feedback.select_tests("ci"))
    assert kwargs["cwd"] == feedback.REPOSITORY_ROOT
    assert kwargs["check"] is False


def test_non_ci_execute_rejects_missing_database_before_running(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        feedback.subprocess, "run",
        lambda *args, **kwargs: pytest.fail("Unsafe execution was invoked."),
    )
    with pytest.raises(SystemExit) as error:
        feedback.main(["--suite", "reassessment", "--execute"])
    assert error.value.code == 2
