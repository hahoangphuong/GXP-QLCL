"""Guard that the cross-head fixture cannot run without CI-only opt-in.

Never connects to PostgreSQL, NAS, or staging while these tests execute.
"""
from __future__ import annotations

import os
import subprocess
import sys


def _import_fixture_with_env(*, enable: bool, url: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("GXP_CROSS_HEAD_DISPOSABLE_GATE", None)
    env["DATABASE_URL"] = url
    env["GXP_CROSS_HEAD_FIXTURE_JSON"] = "/tmp/cross-head-guard-test.json"
    if enable:
        env["GXP_CROSS_HEAD_DISPOSABLE_GATE"] = "1"
    return subprocess.run(
        [sys.executable, "-c", "import tools.cross_head_fixture_app"],
        env=env, capture_output=True, text=True, check=False, timeout=12,
    )


def test_cross_head_fixture_refuses_unopted_in_execution():
    result = _import_fixture_with_env(
        enable=False,
        url="postgresql+psycopg://postgres:secret@127.0.0.1:5432/gxp_qlcl_test",
    )
    assert result.returncode != 0
    assert "explicit disposable CI gate" in result.stderr
    assert "secret" not in result.stderr


def test_cross_head_fixture_refuses_remote_database_before_app_import():
    result = _import_fixture_with_env(
        enable=True,
        url="postgresql+psycopg://reader:secret@production.example:5432/gxp_qlcl_test",
    )
    assert result.returncode != 0
    assert "only local disposable" in result.stderr
    assert "secret" not in result.stderr


def test_cross_head_fixture_refuses_non_disposable_database_before_app_import():
    result = _import_fixture_with_env(
        enable=True,
        url="postgresql+psycopg://reader:secret@127.0.0.1:5432/gxp_qlcl",
    )
    assert result.returncode != 0
    assert "only local disposable" in result.stderr
    assert "secret" not in result.stderr
