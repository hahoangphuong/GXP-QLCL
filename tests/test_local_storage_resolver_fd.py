"""Adversarial POSIX legacy folder resolution containment."""
import os
import pytest

from backend.app.db.enums import StorageResolutionStatus
from backend.app.storage.local import LocalStorageService
from backend.app.storage.types import StorageConfig, StorageOperationError


@pytest.mark.skipif(os.name != "posix", reason="POSIX dirfd resolution")
@pytest.mark.parametrize("kind", ["inspection", "dkkd"])
def test_legacy_resolver_parent_swap_never_reads_external_entries(tmp_path, monkeypatch, kind):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    if kind == "inspection":
        (root / "2026").mkdir()
        inside = root / "2026"
        external = outside
        (inside / "A (ID-103) (KT-1376-GMP)").mkdir()
        (external / "B (ID-103) (KT-1376-GMP)").mkdir()
        kwargs = {"year": 2026, "site_legacy_id": 103, "inspection_legacy_code": "KT-1376-GMP"}
        method = "resolve_inspection_folder"
    else:
        inside = root
        external = outside
        (inside / "A (ID-91)").mkdir()
        (external / "B (ID-91)").mkdir()
        kwargs = {"site_legacy_id": 91}
        method = "resolve_dkkd_folder"
    svc = LocalStorageService(StorageConfig(inspection_root=root, dkkd_root=root))
    original_scandir = os.scandir
    swapped = False

    def raced_scandir(fd):
        nonlocal swapped
        if isinstance(fd, int) and not swapped:
            swapped = True
            if kind == "inspection":
                inside.rename(root / "retained-2026")
                (root / "2026").symlink_to(external, target_is_directory=True)
            else:
                # Root itself is only a locator; held directory fd is still safe.
                root.rename(tmp_path / "retained-root")
                root.symlink_to(external, target_is_directory=True)
        return original_scandir(fd)

    monkeypatch.setattr(os, "scandir", raced_scandir)
    result = getattr(svc, method)(**kwargs)
    assert swapped
    assert result.status == StorageResolutionStatus.RESOLVED
    assert result.relative_path.endswith("A (ID-103) (KT-1376-GMP)" if kind == "inspection" else "A (ID-91)")


@pytest.mark.skipif(os.name != "posix", reason="POSIX dirfd resolution")
@pytest.mark.parametrize("kind", ["inspection", "dkkd"])
def test_legacy_resolver_rejects_matching_symlink_without_outside_read(tmp_path, kind):
    root, outside = tmp_path / "root", tmp_path / "outside"
    (root / "2026").mkdir(parents=True)
    outside.mkdir()
    svc = LocalStorageService(StorageConfig(inspection_root=root, dkkd_root=root))
    if kind == "inspection":
        (root / "2026/A (ID-103) (KT-1376-GMP)").symlink_to(outside, target_is_directory=True)
        with pytest.raises(StorageOperationError, match="escapes configured storage root"):
            svc.resolve_inspection_folder(year=2026, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP")
    else:
        (root / "A (ID-91)").symlink_to(outside, target_is_directory=True)
        with pytest.raises(StorageOperationError, match="escapes configured storage root"):
            svc.resolve_dkkd_folder(site_legacy_id=91)


@pytest.mark.skipif(os.name != "posix", reason="POSIX dirfd resolution")
def test_inspection_resolver_missing_year_and_symlink_year(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    svc = LocalStorageService(StorageConfig(inspection_root=root))
    kwargs = {"year": 2026, "site_legacy_id": 103, "inspection_legacy_code": "KT-1376-GMP"}
    assert svc.resolve_inspection_folder(**kwargs).status == StorageResolutionStatus.NOT_FOUND
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "2026").symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        svc.resolve_inspection_folder(**kwargs)
