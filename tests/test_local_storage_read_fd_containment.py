"""POSIX descriptor-anchored reads must not follow swapped path aliases."""
import os
from pathlib import Path

import pytest

from backend.app.storage.local import LocalStorageService
from backend.app.storage.types import StorageConfig, StorageOperationError


@pytest.mark.skipif(os.name != "posix", reason="POSIX dir_fd contract")
def test_read_stream_refuses_symlink_parent_before_open(tmp_path):
    root = tmp_path / "inspection"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "document.docx").write_bytes(b"outside")
    (root / "alias").symlink_to(outside, target_is_directory=True)
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    with pytest.raises(OSError):
        with storage.read_stream("alias/document.docx") as stream:
            stream.read()


@pytest.mark.skipif(os.name != "posix", reason="POSIX dir_fd contract")
def test_parent_replacement_after_root_descriptor_open_cannot_escape(tmp_path, monkeypatch):
    root = tmp_path / "inspection"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "folder").mkdir()
    (root / "folder" / "document.docx").write_bytes(b"inside")
    (outside / "document.docx").write_bytes(b"outside")
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    original_open = os.open
    swapped = False

    def replace_after_root_open(path, flags, *args, **kwargs):
        nonlocal swapped
        fd = original_open(path, flags, *args, **kwargs)
        if not swapped and os.fspath(path) == os.fspath(root) and flags & os.O_DIRECTORY:
            swapped = True
            (root / "folder").rename(root / "original")
            (root / "folder").symlink_to(outside, target_is_directory=True)
        return fd

    monkeypatch.setattr(os, "open", replace_after_root_open)
    with pytest.raises(OSError):
        with storage.read_stream("folder/document.docx") as stream:
            assert stream.read() != b"outside"
    assert swapped


@pytest.mark.skipif(os.name != "posix", reason="POSIX dir_fd contract")
def test_descriptor_anchored_read_accepts_normal_file(tmp_path):
    root = tmp_path / "inspection"
    (root / "folder").mkdir(parents=True)
    (root / "folder" / "document.docx").write_bytes(b"expected")
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    with storage.read_stream("folder/document.docx") as stream:
        assert stream.read() == b"expected"


@pytest.mark.skipif(os.name != "posix", reason="POSIX dir_fd contract")
def test_read_stream_rejects_fifo_without_blocking(tmp_path):
    root = tmp_path / "inspection"
    root.mkdir()
    os.mkfifo(root / "pipe")
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    with pytest.raises(StorageOperationError, match="regular file"):
        with storage.read_stream("pipe") as stream:
            stream.read()
