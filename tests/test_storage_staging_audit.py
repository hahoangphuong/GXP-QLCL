from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from backend.app.storage.local import LocalStorageService
from backend.app.storage.staging import (
    audit_staging_candidates,
    classify_staging_candidate,
    new_staging_name,
)
from backend.app.storage.types import StorageConfig


def _storage(tmp_path: Path) -> LocalStorageService:
    root = tmp_path / "inspection"
    root.mkdir()
    return LocalStorageService(StorageConfig(inspection_root=root))


def test_staging_names_detect_managed_and_historical_smb_candidates():
    name = new_staging_name()
    assert name.startswith(".gxp-stage-") and name.endswith(".tmp")
    assert classify_staging_candidate(name) == "managed_candidate"
    assert classify_staging_candidate("document.docx.tmp-" + "a" * 32) == "legacy_smb_candidate"
    for ordinary in ["document.docx", "tmpabc123", "document.tmp-deadbeef", "../stage", ".gxp-stage-not-uuid"]:
        assert classify_staging_candidate(ordinary) is None


def test_audit_finds_candidates_without_mutating_files(tmp_path: Path):
    service = _storage(tmp_path)
    root = service.inspection_root
    (root / "2026").mkdir()
    modern = root / "2026" / new_staging_name()
    legacy = root / "2026" / ("doc.pdf.tmp-" + "b" * 32)
    ordinary = root / "2026" / "normal.pdf"
    for path, content in [(modern, b"not-published"), (legacy, b"older"), (ordinary, b"real")]:
        path.write_bytes(content)

    report = audit_staging_candidates(service, roots=("inspection",))
    assert report.truncated is False
    assert report.scanned_directories == 2
    assert {item.relative_path for item in report.candidates} == {
        f"2026/{modern.name}", f"2026/{legacy.name}",
    }
    assert sorted(p.read_bytes() for p in (modern, legacy, ordinary)) == [b"not-published", b"older", b"real"]


def test_audit_marks_depth_and_entry_limit_incomplete(tmp_path: Path):
    service = _storage(tmp_path)
    (service.inspection_root / "2026").mkdir()
    (service.inspection_root / "2026" / new_staging_name()).write_bytes(b"x")
    deep = audit_staging_candidates(service, max_depth=0)
    assert deep.truncated and deep.incomplete_reason == "depth_budget_exceeded"
    assert deep.candidates == ()

    entries = audit_staging_candidates(service, max_entries=1)
    assert entries.truncated and entries.incomplete_reason == "entry_budget_exceeded"


def test_audit_directory_budget_never_claims_completeness(tmp_path: Path):
    service = _storage(tmp_path)
    (service.inspection_root / "2026").mkdir()
    report = audit_staging_candidates(service, max_directories=1)
    assert report.truncated and report.incomplete_reason == "directory_budget_exceeded"


def test_audit_rejects_invalid_scope_and_budgets(tmp_path: Path):
    service = _storage(tmp_path)
    with pytest.raises(ValueError):
        audit_staging_candidates(service, roots=("unrecognized",))
    with pytest.raises(ValueError):
        audit_staging_candidates(service, max_entries=0)
