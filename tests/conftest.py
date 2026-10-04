from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"
FIXTURE_ARTIFACTS_ROOT = FIXTURE_ROOT / "artifacts"
FIXTURE_LEGACY_ROOT = FIXTURE_ROOT / "legacy"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


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


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_external_evidence(*paths): test needs non-versioned legacy or audit evidence",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        marker = item.get_closest_marker("requires_external_evidence")
        if marker is None:
            continue
        missing = [str(path) for path in marker.args if not (REPOSITORY_ROOT / str(path)).is_file()]
        if missing:
            item.add_marker(pytest.mark.skip(reason=f"external legacy evidence is unavailable: {', '.join(missing)}"))
