from __future__ import annotations

import json
from pathlib import Path

from tools import audit_storage_staging as cli

import pytest

from backend.app.storage.local import LocalStorageService
from backend.app.storage.staging import (
    audit_staging_candidates,
    classify_staging_candidate,
    new_staging_name,
)
from backend.app.storage.types import StorageConfig, StorageOperationError


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


def test_staging_audit_excludes_directories_named_like_stage_files(tmp_path: Path):
    service = _storage(tmp_path)
    dirname = new_staging_name()
    (service.inspection_root / dirname).mkdir()
    report = audit_staging_candidates(service, max_depth=0)
    assert report.candidates == ()
    assert report.truncated
    assert report.incomplete_reason == "depth_budget_exceeded"


def test_staging_audit_marks_failed_nas_read_and_preserves_previous_findings(tmp_path: Path):
    service = _storage(tmp_path)
    modern = new_staging_name()
    (service.inspection_root / modern).write_bytes(b"private bytes")
    (service.inspection_root / "2026").mkdir()

    original_iterator = service.iter_entries_for_audit
    def interrupted(relative_path="", *, root="inspection"):
        if relative_path == "2026":
            raise OSError("smb connection lost: private UNC hostname and secret marker")
        yield from original_iterator(relative_path, root=root)

    service.iter_entries_for_audit = interrupted
    report = audit_staging_candidates(service)
    assert report.truncated
    assert report.incomplete_reason == "storage_access_failed"
    assert report.failed_root == "inspection"
    assert report.failed_relative_path == "2026"
    assert report.scanned_directories == 1
    assert {candidate.relative_path for candidate in report.candidates} == {modern}
    assert "private UNC" not in repr(report)
    assert (service.inspection_root / modern).read_bytes() == b"private bytes"


def test_staging_audit_initial_root_failure_never_reports_clean(tmp_path: Path):
    service = _storage(tmp_path)
    def offline(*args, **kwargs):
        raise OSError("NAS offline with secret connection detail")
    service.iter_entries_for_audit = offline
    report = audit_staging_candidates(service)
    assert report.truncated and report.incomplete_reason == "storage_access_failed"
    assert report.scanned_directories == 0
    assert report.scanned_entries == 0
    assert report.failed_relative_path == ""
    assert report.candidates == ()


def test_staging_cli_reports_partial_inventory_and_failure_exit_status(tmp_path: Path, monkeypatch, capsys):
    service = _storage(tmp_path)
    stage = new_staging_name()
    (service.inspection_root / stage).write_bytes(b"intact")
    (service.inspection_root / "2026").mkdir()
    original = service.iter_entries_for_audit

    def disconnected(relative_path="", *, root="inspection"):
        if relative_path == "2026":
            raise OSError("NAS password leaked from exception if printed")
        yield from original(relative_path, root=root)

    service.iter_entries_for_audit = disconnected
    monkeypatch.setattr(cli, "create_storage_service_from_env", lambda: service)
    exit_status = cli.main(["--root", "inspection"])
    output = capsys.readouterr()
    parsed = json.loads(output.out)
    assert exit_status == 3
    assert parsed["truncated"] is True
    assert parsed["incomplete_reason"] == "storage_access_failed"
    assert parsed["failed_relative_path"] == "2026"
    assert parsed["candidates"][0]["relative_path"] == stage
    assert "NAS password" not in output.out + output.err
    assert (service.inspection_root / stage).read_bytes() == b"intact"


def test_staging_cli_setup_failure_emits_safe_incomplete_report(monkeypatch, capsys):
    def denied():
        raise StorageOperationError("Secret SMB connection information")
    monkeypatch.setattr(cli, "create_storage_service_from_env", denied)
    exit_status = cli.main(["--root", "inspection"])
    output = capsys.readouterr()
    data = json.loads(output.out)
    assert exit_status == 3
    assert data["incomplete_reason"] == "storage_setup_failed"
    assert data["candidates"] == []
    assert "Secret SMB" not in output.out + output.err


def test_local_staging_iterator_limits_metadata_calls_even_in_huge_folder(tmp_path: Path, monkeypatch):
    service = _storage(tmp_path)
    for i in range(200):
        (service.inspection_root / f"item-{i:04d}.txt").write_bytes(b"x")

    checked = 0
    original_entry = service._entry_for

    def bounded_entry(root, target):
        nonlocal checked
        checked += 1
        return original_entry(root, target)

    monkeypatch.setattr(service, "_entry_for", bounded_entry)
    monkeypatch.setattr(service, "list", lambda *args, **kwargs: pytest.fail("unbounded list() called"))
    report = audit_staging_candidates(service, max_entries=3)
    assert report.truncated and report.incomplete_reason == "entry_budget_exceeded"
    assert report.scanned_entries == 3
    assert checked <= 4
    assert len(list(service.inspection_root.iterdir())) == 200


def test_staging_stream_error_after_partial_entries_fails_closed(tmp_path: Path, monkeypatch):
    service = _storage(tmp_path)
    stage_name = new_staging_name()
    (service.inspection_root / stage_name).write_bytes(b"preserve")
    root = service.inspection_root
    original = service._entry_for

    def partial(relative_path="", *, root="inspection"):
        yield original(service.inspection_root, service.inspection_root / stage_name)
        raise OSError("NAS stopped while listing")

    monkeypatch.setattr(service, "iter_entries_for_audit", partial)
    report = audit_staging_candidates(service)
    assert report.truncated
    assert report.incomplete_reason == "storage_access_failed"
    assert report.scanned_directories == 0
    assert report.scanned_entries == 1
    assert report.candidates[0].relative_path == stage_name
    assert (service.inspection_root / stage_name).read_bytes() == b"preserve"
