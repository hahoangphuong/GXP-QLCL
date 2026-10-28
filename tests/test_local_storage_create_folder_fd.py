"""POSIX mkdir containment tests on temporary synthetic directories."""
import os

import pytest

from backend.app.storage.local import LocalStorageService
from backend.app.storage.types import StorageConfig


@pytest.mark.skipif(os.name != "posix", reason="POSIX dirfd contract")
def test_create_folder_parent_replacement_does_not_create_outside_root(tmp_path, monkeypatch):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    (root / "parent").mkdir(parents=True)
    outside.mkdir()
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    original_mkdir = os.mkdir
    swapped = False

    def swap_after_nested_mkdir(path, *args, **kwargs):
        nonlocal swapped
        if path == "newchild" and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            (root / "parent").rename(root / "original-parent")
            (root / "parent").symlink_to(outside, target_is_directory=True)
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(os, "mkdir", swap_after_nested_mkdir)
    entry = storage.create_folder("parent/newchild/deep")
    assert swapped
    assert entry.relative_path == "parent/newchild/deep"
    assert entry.is_dir
    assert entry.size is None
    assert (root / "original-parent/newchild/deep").is_dir()
    assert not (outside / "newchild").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow contract")
def test_create_folder_refuses_symlink_component(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "alias").symlink_to(outside, target_is_directory=True)
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    with pytest.raises(OSError):
        storage.create_folder("alias/forbidden")
    assert not (outside / "forbidden").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX dirfd contract")
def test_create_folder_existing_directory_and_root_are_idempotent(tmp_path):
    root = tmp_path / "root"
    (root / "existing").mkdir(parents=True)
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    entry = storage.create_folder("existing/nested")
    again = storage.create_folder("existing/nested")
    root_entry = storage.create_folder("")
    assert entry == again
    assert (root / "existing/nested").is_dir()
    assert root_entry.relative_path == ""
    assert root_entry.is_dir
    assert root_entry.size is None


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor cleanup")
def test_create_folder_error_closes_every_directory_descriptor(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "parent").mkdir(parents=True)
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    original_open = os.open
    original_mkdir = os.mkdir
    acquired = []

    def capture_open(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        acquired.append(fd)
        return fd

    def fault_mkdir(path, *args, **kwargs):
        if path == "newchild" and kwargs.get("dir_fd") is not None:
            raise OSError("synthetic mkdir fault")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", capture_open)
    monkeypatch.setattr(os, "mkdir", fault_mkdir)
    with pytest.raises(OSError, match="synthetic mkdir fault"):
        storage.create_folder("parent/newchild")
    assert len(acquired) == 2
    for fd in acquired:
        with pytest.raises(OSError):
            os.fstat(fd)
    assert not (root / "parent/newchild").exists()
