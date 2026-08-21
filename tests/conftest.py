from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"
FIXTURE_ARTIFACTS_ROOT = FIXTURE_ROOT / "artifacts"
FIXTURE_LEGACY_ROOT = FIXTURE_ROOT / "legacy"


@pytest.fixture(autouse=True)
def _configure_sanitized_fixture_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GXP_ARTIFACTS_ROOT", str(FIXTURE_ARTIFACTS_ROOT))
    monkeypatch.setenv("GXP_LEGACY_ROOT", str(FIXTURE_LEGACY_ROOT))


@pytest.fixture
def fixture_root() -> Path:
    return FIXTURE_ROOT


@pytest.fixture
def fixture_artifacts_root() -> Path:
    return FIXTURE_ARTIFACTS_ROOT


@pytest.fixture
def materialized_phase2_db(tmp_path: Path, fixture_artifacts_root: Path) -> Path:
    database_path = tmp_path / "staging_readonly.db"
    schema_path = fixture_artifacts_root / "phase2" / "staging_readonly.sql"
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()
    return database_path
