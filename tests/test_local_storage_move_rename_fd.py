"""POSIX move/rename containment regression tests, disposable tmp_path only."""
import os
import stat
import sys

import pytest

from backend.app.storage.local import LocalStorageService
from backend.app.storage.types import StorageConfig, StorageOperationError, StorageTargetExistsError


@pytest.mark.skipif(os.name != "posix" or not sys.platform.startswith("linux"), reason="Linux renameat2")
@pytest.mark.parametrize("operation", ["move", "rename"])
def test_relocate_parent_swap_does_not_modify_external_tree(tmp_path, monkeypatch, operation):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    (root / "folder").mkdir(parents=True)
    outside.mkdir()
    (root / "folder" / "src.bin").write_bytes(b"trusted")
    (outside / "src.bin").write_bytes(b"foreign")
    (outside / "dst.bin").write_bytes(b"outside-dst")
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    original_stat = os.stat
    swapped = False

    def swap_after_source_stat(path, *args, **kwargs):
        nonlocal swapped
        result = original_stat(path, *args, **kwargs)
        if path == "src.bin" and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            (root / "folder").rename(root / "original-folder")
            (root / "folder").symlink_to(outside, target_is_directory=True)
        return result

    monkeypatch.setattr(os, "stat", swap_after_source_stat)
    if operation == "move":
        # Destination does not traverse the swapped component: publication
        # succeeds from the held source parent into the safe root directory.
        entry = storage.move("folder/src.bin", "dst.bin")
        assert entry.relative_path == "dst.bin"
        assert (root / "dst.bin").read_bytes() == b"trusted"
        assert not (root / "original-folder/src.bin").exists()
    else:
        # Rename needs to reopen the swapped parent as its destination.
        # Refuse the symlink rather than redirect publication outside root.
        with pytest.raises(NotADirectoryError):
            storage.rename("folder/src.bin", "dst.bin")
        assert (root / "original-folder/src.bin").read_bytes() == b"trusted"
    assert swapped
    assert (outside / "src.bin").read_bytes() == b"foreign"
    assert (outside / "dst.bin").read_bytes() == b"outside-dst"


@pytest.mark.skipif(os.name != "posix" or not sys.platform.startswith("linux"), reason="Linux renameat2")
@pytest.mark.parametrize("operation", ["move", "rename"])
def test_relocate_rejects_symlink_source_and_destination_conflict(tmp_path, operation):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "src.bin").write_bytes(b"trusted")
    (outside / "foreign.bin").write_bytes(b"foreign")
    (root / "alias").symlink_to(outside, target_is_directory=True)
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    with pytest.raises(OSError):
        storage.move("src.bin", "alias/dst.bin")
    (root / "src-link.bin").symlink_to(outside / "foreign.bin")
    with pytest.raises(StorageOperationError, match="regular file or directory"):
        storage.move("src-link.bin", "other.bin")
    with pytest.raises(StorageOperationError, match="regular file or directory"):
        storage.rename("src-link.bin", "renamed.bin")
    (root / "dst.bin").write_bytes(b"competitor")
    with pytest.raises(StorageTargetExistsError):
        if operation == "move":
            storage.move("src.bin", "dst.bin")
        else:
            storage.rename("src.bin", "dst.bin")
    assert (root / "src.bin").read_bytes() == b"trusted"
    assert (root / "dst.bin").read_bytes() == b"competitor"
    assert (outside / "foreign.bin").read_bytes() == b"foreign"


@pytest.mark.skipif(os.name != "posix" or not sys.platform.startswith("linux"), reason="Linux renameat2")
def test_move_file_into_new_parent_and_rename_directory(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.bin").write_bytes(b"a")
    (root / "dir").mkdir()
    (root / "dir/child.bin").write_bytes(b"child")
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    moved = storage.move("a.bin", "nested/deep/a.bin")
    assert moved.size == 1 and not moved.is_dir
    assert (root / "nested/deep/a.bin").read_bytes() == b"a"
    renamed = storage.rename("dir", "renamed")
    assert renamed.is_dir and renamed.size is None
    assert (root / "renamed/child.bin").read_bytes() == b"child"


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor cleanup")
def test_move_stat_error_closes_parent_fds(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "folder").mkdir(parents=True)
    (root / "folder/src.bin").write_bytes(b"source")
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    opened = []
    original_open = os.open
    original_stat = os.stat

    def tracked_open(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def failing_stat(path, *args, **kwargs):
        if path == "src.bin" and kwargs.get("dir_fd") is not None:
            raise OSError("injected source stat failure")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "stat", failing_stat)
    with pytest.raises(OSError, match="injected source stat failure"):
        storage.move("folder/src.bin", "dst.bin")
    for fd in opened:
        with pytest.raises(OSError):
            os.fstat(fd)
    assert (root / "folder/src.bin").read_bytes() == b"source"


@pytest.mark.skipif(os.name != "posix" or not sys.platform.startswith("linux"), reason="Linux renameat2")
def test_move_destination_parent_swap_is_contained(tmp_path, monkeypatch):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    (root / "dest").mkdir(parents=True)
    outside.mkdir()
    (root / "src.bin").write_bytes(b"trusted")
    (outside / "moved.bin").write_bytes(b"foreign")
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    original_open = os.open
    swapped = False

    def swap_after_target_parent_open(path, *args, **kwargs):
        nonlocal swapped
        fd = original_open(path, *args, **kwargs)
        if path == "dest" and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            (root / "dest").rename(root / "original-dest")
            (root / "dest").symlink_to(outside, target_is_directory=True)
        return fd

    monkeypatch.setattr(os, "open", swap_after_target_parent_open)
    entry = storage.move("src.bin", "dest/moved.bin")
    assert swapped and entry.relative_path == "dest/moved.bin"
    assert (root / "original-dest/moved.bin").read_bytes() == b"trusted"
    assert (outside / "moved.bin").read_bytes() == b"foreign"
    assert not (root / "src.bin").exists()
