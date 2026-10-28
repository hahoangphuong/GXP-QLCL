"""Adversarial POSIX delete tests using disposable local directories only."""
import os

import pytest

from backend.app.storage.local import LocalStorageService
from backend.app.storage.types import StorageConfig, StorageOperationError


@pytest.mark.skipif(os.name != "posix", reason="POSIX dir_fd delete contract")
def test_delete_parent_symlink_swap_does_not_remove_external_file(tmp_path, monkeypatch):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    (root / "folder").mkdir(parents=True)
    outside.mkdir()
    (root / "folder" / "victim.bin").write_bytes(b"inside")
    (outside / "victim.bin").write_bytes(b"outside")
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    original_stat = os.stat
    swapped = False

    def swap_after_anchored_stat(path, *args, **kwargs):
        nonlocal swapped
        result = original_stat(path, *args, **kwargs)
        if not swapped and path == "victim.bin" and kwargs.get("dir_fd") is not None:
            swapped = True
            (root / "folder").rename(root / "original-folder")
            (root / "folder").symlink_to(outside, target_is_directory=True)
        return result

    monkeypatch.setattr(os, "stat", swap_after_anchored_stat)
    storage.delete("folder/victim.bin")
    assert swapped
    assert not (root / "original-folder" / "victim.bin").exists()
    assert (outside / "victim.bin").read_bytes() == b"outside"


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow delete contract")
def test_delete_refuses_symlink_parent_and_final_leaf(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "victim.bin").write_bytes(b"outside")
    (root / "alias").symlink_to(outside, target_is_directory=True)
    (root / "link.bin").symlink_to(outside / "victim.bin")
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    with pytest.raises(OSError):
        storage.delete("alias/victim.bin")
    with pytest.raises(StorageOperationError, match="not a regular file"):
        storage.delete("link.bin")
    assert (outside / "victim.bin").read_bytes() == b"outside"
    assert (root / "link.bin").is_symlink()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor cleanup contract")
def test_delete_stat_failure_closes_directory_descriptors(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "folder").mkdir(parents=True)
    (root / "folder" / "victim.bin").write_bytes(b"inside")
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    original_open = os.open
    original_stat = os.stat
    acquired = []

    def capture_open(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        acquired.append(fd)
        return fd

    def fault_stat(path, *args, **kwargs):
        if path == "victim.bin" and kwargs.get("dir_fd") is not None:
            raise OSError("synthetic stat fault")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", capture_open)
    monkeypatch.setattr(os, "stat", fault_stat)
    with pytest.raises(OSError, match="synthetic stat fault"):
        storage.delete("folder/victim.bin")
    assert len(acquired) == 2
    for fd in acquired:
        with pytest.raises(OSError):
            os.fstat(fd)
    assert (root / "folder" / "victim.bin").read_bytes() == b"inside"
