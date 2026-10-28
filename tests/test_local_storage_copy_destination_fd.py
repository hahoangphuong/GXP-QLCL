"""Adversarial POSIX copy destination tests on disposable tmp_path trees."""
import os
import stat

import pytest

from backend.app.storage.local import LocalStorageService
from backend.app.storage.types import StorageConfig, StorageTargetExistsError


@pytest.mark.skipif(os.name != "posix", reason="POSIX dir_fd contract")
def test_copy_parent_swap_during_bytes_does_not_publish_external(tmp_path, monkeypatch):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    (root / "dest").mkdir(parents=True)
    outside.mkdir()
    (root / "source.bin").write_bytes(b"trusted")
    (outside / "copy.bin").write_bytes(b"external")
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    original_copy = __import__("shutil").copyfileobj
    swapped = False

    def swap_while_copying(src, dst, *args, **kwargs):
        nonlocal swapped
        if not swapped:
            swapped = True
            (root / "dest").rename(root / "original-dest")
            (root / "dest").symlink_to(outside, target_is_directory=True)
        return original_copy(src, dst, *args, **kwargs)

    monkeypatch.setattr("backend.app.storage.local.shutil.copyfileobj", swap_while_copying)
    entry = storage.copy("source.bin", "dest/copy.bin")
    assert swapped
    assert entry.relative_path == "dest/copy.bin"
    assert entry.size == 7
    assert (root / "original-dest" / "copy.bin").read_bytes() == b"trusted"
    assert (outside / "copy.bin").read_bytes() == b"external"
    assert not list((root / "original-dest").glob(".gxp-stage-*"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow contract")
def test_copy_refuses_symlink_destination_parent(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "source.bin").write_bytes(b"inside")
    (root / "alias").symlink_to(outside, target_is_directory=True)
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    with pytest.raises(OSError):
        storage.copy("source.bin", "alias/copy.bin")
    assert not (outside / "copy.bin").exists()


@pytest.mark.skipif(os.name != "posix", reason="Linux renameat2 no-replace contract")
def test_copy_conflict_after_staging_preserves_concurrent_writer(tmp_path, monkeypatch):
    if not __import__("sys").platform.startswith("linux"):
        pytest.skip("renameat2 contract on Linux")
    root = tmp_path / "root"
    root.mkdir()
    (root / "source.bin").write_bytes(b"source")
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    original_copy = __import__("shutil").copyfileobj

    def concurrent_write(src, dst, *args, **kwargs):
        result = original_copy(src, dst, *args, **kwargs)
        (root / "copy.bin").write_bytes(b"other-writer")
        return result

    monkeypatch.setattr("backend.app.storage.local.shutil.copyfileobj", concurrent_write)
    with pytest.raises(StorageTargetExistsError):
        storage.copy("source.bin", "copy.bin")
    assert (root / "copy.bin").read_bytes() == b"other-writer"
    assert not list(root.glob(".gxp-stage-*"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX fd cleanup contract")
def test_copy_failure_after_parent_swap_cleans_only_original_directory(tmp_path, monkeypatch):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    (root / "dest").mkdir(parents=True)
    outside.mkdir()
    (root / "source.bin").write_bytes(b"trusted")
    (outside / ".gxp-stage-never-touch.tmp").write_bytes(b"foreign")
    storage = LocalStorageService(StorageConfig(inspection_root=root))

    def fail_during_copy(src, dst, *args, **kwargs):
        (root / "dest").rename(root / "original-dest")
        (root / "dest").symlink_to(outside, target_is_directory=True)
        raise OSError("synthetic copy fault")

    monkeypatch.setattr("backend.app.storage.local.shutil.copyfileobj", fail_during_copy)
    with pytest.raises(OSError, match="synthetic copy fault"):
        storage.copy("source.bin", "dest/copy.bin")
    assert not list((root / "original-dest").glob(".gxp-stage-*"))
    assert (outside / ".gxp-stage-never-touch.tmp").read_bytes() == b"foreign"
    assert not (outside / "copy.bin").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX metadata contract")
def test_copy_preserves_mode_and_timestamp_without_destination_path_stat(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    source = root / "source.bin"
    source.write_bytes(b"contents")
    source.chmod(0o640)
    os.utime(source, ns=(1_600_000_000_000_000_000,) * 2)
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    entry = storage.copy("source.bin", "nested/result.bin")
    published = root / "nested/result.bin"
    assert entry.size == 8
    assert published.read_bytes() == b"contents"
    assert stat.S_IMODE(published.stat().st_mode) == 0o640
    assert published.stat().st_mtime_ns == 1_600_000_000_000_000_000
