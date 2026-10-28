"""POSIX stat/exists descriptor-anchor regression coverage."""
import os

import pytest

from backend.app.storage.local import LocalStorageService
from backend.app.storage.types import StorageConfig, StorageOperationError


@pytest.mark.skipif(os.name != "posix", reason="POSIX metadata containment")
@pytest.mark.parametrize("method", ["stat", "exists"])
def test_metadata_parent_swap_never_follows_external_symlink(tmp_path, monkeypatch, method):
    root, outside = tmp_path / "root", tmp_path / "outside"
    (root / "inner").mkdir(parents=True)
    outside.mkdir()
    (root / "inner/data.bin").write_bytes(b"trusted")
    (outside / "data.bin").write_bytes(b"foreign-larger")
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    original_open = os.open
    swapped = False

    def swap_on_open(path, *args, **kwargs):
        nonlocal swapped
        fd = original_open(path, *args, **kwargs)
        if path == "inner" and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            (root / "inner").rename(root / "retained-inner")
            (root / "inner").symlink_to(outside, target_is_directory=True)
        return fd

    monkeypatch.setattr(os, "open", swap_on_open)
    result = getattr(storage, method)("inner/data.bin")
    assert swapped
    if method == "stat":
        assert result.size == len(b"trusted")
        assert result.relative_path == "inner/data.bin"
    else:
        assert result is True
    assert (outside / "data.bin").read_bytes() == b"foreign-larger"


@pytest.mark.skipif(os.name != "posix", reason="POSIX metadata containment")
def test_metadata_symlinks_refused_even_inside_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "file.bin").write_bytes(b"data")
    (root / "alias.bin").symlink_to(root / "file.bin")
    (root / "subdir").mkdir()
    (root / "subdir-link").symlink_to(root / "subdir", target_is_directory=True)
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    for method in (storage.stat, storage.exists):
        with pytest.raises(StorageOperationError, match="symlink"):
            method("alias.bin")
        with pytest.raises(OSError):
            method("subdir-link/child")
    assert storage.exists("missing.bin") is False
    assert storage.stat("file.bin").size == 4


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor cleanup")
def test_metadata_stat_error_closes_descriptors(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "inner").mkdir(parents=True)
    (root / "inner/data.bin").write_bytes(b"trusted")
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    original_open, original_stat = os.open, os.stat
    opened = []

    def tracked_open(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def fail_stat(path, *args, **kwargs):
        if path == "data.bin" and kwargs.get("dir_fd") is not None:
            raise OSError("injected stat error")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "stat", fail_stat)
    with pytest.raises(OSError, match="injected stat error"):
        storage.stat("inner/data.bin")
    for fd in opened:
        with pytest.raises(OSError):
            os.fstat(fd)


@pytest.mark.skipif(os.name != "posix", reason="POSIX metadata containment")
def test_metadata_root_and_missing_entries(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    entry = storage.stat("")
    assert entry.relative_path == "" and entry.is_dir and entry.size is None
    assert storage.exists("") is True
    with pytest.raises(FileNotFoundError):
        storage.stat("not-found.txt")
    assert storage.exists("not-found.txt") is False
