"""POSIX enumeration survives parent swaps without following external paths."""
import os

import pytest

from backend.app.storage.local import LocalStorageService
from backend.app.storage.types import StorageConfig, StorageOperationError


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor enumeration")
@pytest.mark.parametrize("operation", ["list", "iter_entries_for_audit"])
def test_enumeration_parent_swap_is_contained(tmp_path, monkeypatch, operation):
    root, external = tmp_path / "root", tmp_path / "external"
    (root / "sub").mkdir(parents=True)
    external.mkdir()
    (root / "sub/inside.txt").write_bytes(b"inside")
    (external / "secret.txt").write_bytes(b"secret")
    service = LocalStorageService(StorageConfig(inspection_root=root))
    original_open = os.open
    swapped = False

    def swap_after_directory_open(path, *args, **kwargs):
        nonlocal swapped
        fd = original_open(path, *args, **kwargs)
        if path == "sub" and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            (root / "sub").rename(root / "retained-sub")
            (root / "sub").symlink_to(external, target_is_directory=True)
        return fd

    monkeypatch.setattr(os, "open", swap_after_directory_open)
    found = list(getattr(service, operation)("sub"))
    assert swapped
    assert [(e.relative_path, e.size) for e in found] == [("sub/inside.txt", 6)]
    assert (external / "secret.txt").read_bytes() == b"secret"


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor enumeration")
@pytest.mark.parametrize("operation", ["list", "iter_entries_for_audit"])
def test_enumeration_rejects_symlink_children_and_parents(tmp_path, operation):
    root = tmp_path / "root"
    root.mkdir()
    (root / "folder").mkdir()
    (root / "file.txt").write_bytes(b"safe")
    (root / "alias").symlink_to(root / "file.txt")
    (root / "folder-alias").symlink_to(root / "folder", target_is_directory=True)
    service = LocalStorageService(StorageConfig(inspection_root=root))
    with pytest.raises(StorageOperationError, match="symlink"):
        list(getattr(service, operation)(""))
    with pytest.raises(OSError):
        list(getattr(service, operation)("folder-alias"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor enumeration")
@pytest.mark.parametrize("operation", ["list", "iter_entries_for_audit"])
def test_enumeration_closes_directory_fds_on_error(tmp_path, monkeypatch, operation):
    root = tmp_path / "root"
    (root / "folder").mkdir(parents=True)
    (root / "folder/file.txt").write_bytes(b"safe")
    service = LocalStorageService(StorageConfig(inspection_root=root))
    original_open, original_stat = os.open, os.stat
    opened = []

    def tracked_open(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def fail_stat(path, *args, **kwargs):
        if path == "file.txt" and kwargs.get("dir_fd") is not None:
            raise OSError("injected enumeration stat failure")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "stat", fail_stat)
    with pytest.raises(OSError, match="injected enumeration stat failure"):
        list(getattr(service, operation)("folder"))
    for fd in opened:
        with pytest.raises(OSError):
            os.fstat(fd)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor enumeration")
def test_list_sort_order_and_streaming_audit_metadata(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "Zoo").mkdir()
    (root / "alpha").mkdir()
    (root / "b.txt").write_bytes(b"bb")
    (root / "a.txt").write_bytes(b"a")
    service = LocalStorageService(StorageConfig(inspection_root=root))
    entries = service.list("")
    assert [e.name for e in entries] == ["alpha", "Zoo", "a.txt", "b.txt"]
    assert [e.size for e in entries] == [None, None, 1, 2]
    assert {e.name for e in service.iter_entries_for_audit("")} == {"alpha", "Zoo", "a.txt", "b.txt"}
