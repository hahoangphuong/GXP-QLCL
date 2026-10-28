"""Fail closed when a matching legacy folder vanishes during enumeration."""
import os
import pytest

from backend.app.storage.local import LocalStorageService
from backend.app.storage.types import StorageConfig, StorageOperationError
from backend.app.db.enums import StorageResolutionStatus


@pytest.mark.skipif(os.name != "posix", reason="POSIX resolver descriptor semantics")
@pytest.mark.parametrize("kind", ["inspection", "dkkd"])
def test_matching_candidate_disappears_during_resolution(tmp_path, monkeypatch, kind):
    inspection = tmp_path / "inspection"
    dkkd = tmp_path / "dkkd"
    inspection.mkdir()
    dkkd.mkdir()
    service = LocalStorageService(StorageConfig(inspection_root=inspection, dkkd_root=dkkd))
    if kind == "inspection":
        parent = inspection / "2026"
        parent.mkdir()
        first, vanishing = "A (ID-103) (1376-GMP)", "B (ID-103) (1376-GMP)"
        resolve = lambda: service.resolve_inspection_folder(year=2026, site_legacy_id=103, inspection_legacy_code="1376-GMP")
    else:
        parent = dkkd
        first, vanishing = "A (103)", "B (103)"
        resolve = lambda: service.resolve_dkkd_folder(site_legacy_id=103)
    (parent / first).mkdir()
    (parent / vanishing).mkdir()
    original_stat = os.stat
    injected = False

    def stat_with_missing_candidate(path, *args, **kwargs):
        nonlocal injected
        if path == vanishing and kwargs.get("dir_fd") is not None:
            injected = True
            raise FileNotFoundError(2, "injected candidate removal", path)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", stat_with_missing_candidate)
    with pytest.raises(StorageOperationError, match="candidate changed during enumeration"):
        resolve()
    assert injected
    assert (parent / vanishing).is_dir()


@pytest.mark.skipif(os.name != "posix", reason="POSIX resolver descriptor semantics")
def test_missing_year_directory_still_not_found(tmp_path):
    root = tmp_path / "inspection"
    root.mkdir()
    service = LocalStorageService(StorageConfig(inspection_root=root))
    result = service.resolve_inspection_folder(year=2026, site_legacy_id=103, inspection_legacy_code="1376-GMP")
    assert result.status == StorageResolutionStatus.NOT_FOUND
    assert result.candidate_count == 0
