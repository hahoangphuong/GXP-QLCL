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


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow contract")
def test_checksum_does_not_follow_symlink_parent(tmp_path):
    root = tmp_path / "inspection"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "data.bin").write_bytes(b"untrusted")
    (root / "link").symlink_to(outside, target_is_directory=True)
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    with pytest.raises(OSError):
        storage.checksum("link/data.bin")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor contract")
def test_checksum_rejects_parent_swap_after_root_open(tmp_path, monkeypatch):
    root = tmp_path / "inspection"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "folder").mkdir()
    (root / "folder" / "data.bin").write_bytes(b"inside")
    (outside / "data.bin").write_bytes(b"outside")
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    original_open = os.open
    swapped = False

    def swap_after_root_open(path, flags, *args, **kwargs):
        nonlocal swapped
        fd = original_open(path, flags, *args, **kwargs)
        if not swapped and os.fspath(path) == os.fspath(root) and flags & os.O_DIRECTORY:
            swapped = True
            (root / "folder").rename(root / "original")
            (root / "folder").symlink_to(outside, target_is_directory=True)
        return fd

    monkeypatch.setattr(os, "open", swap_after_root_open)
    with pytest.raises(OSError):
        storage.checksum("folder/data.bin")
    assert swapped


def test_checksum_of_regular_file_uses_stream_contract(tmp_path):
    from hashlib import sha256

    root = tmp_path / "inspection"
    (root / "folder").mkdir(parents=True)
    binary = b"same bytes as read_stream"
    (root / "folder" / "data.bin").write_bytes(binary)
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    assert storage.checksum("folder/data.bin") == sha256(binary).hexdigest()


@pytest.mark.skipif(os.name != "posix", reason="POSIX regular file requirement")
def test_checksum_rejects_fifo_without_blocking(tmp_path):
    root = tmp_path / "inspection"
    root.mkdir()
    os.mkfifo(root / "pipe")
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    with pytest.raises(StorageOperationError, match="regular file"):
        storage.checksum("pipe")


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow copy contract")
def test_copy_rejects_symlink_source_and_leaves_no_destination(tmp_path):
    root = tmp_path / "inspection"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.bin").write_bytes(b"outside")
    (root / "alias").symlink_to(outside, target_is_directory=True)
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    with pytest.raises((OSError, StorageOperationError)):
        storage.copy("alias/secret.bin", "result.bin")
    assert not (root / "result.bin").exists()
    assert not list(root.glob(".gxp-stage-*.tmp"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor copy contract")
def test_copy_rejects_parent_symlink_swap_before_source_open(tmp_path, monkeypatch):
    root = tmp_path / "inspection"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "folder").mkdir()
    (root / "folder" / "source.bin").write_bytes(b"inside")
    (outside / "source.bin").write_bytes(b"outside")
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    original_open = os.open
    swapped = False

    def swap_after_root_open(path, flags, *args, **kwargs):
        nonlocal swapped
        fd = original_open(path, flags, *args, **kwargs)
        if not swapped and os.fspath(path) == os.fspath(root) and flags & os.O_DIRECTORY:
            swapped = True
            (root / "folder").rename(root / "original")
            (root / "folder").symlink_to(outside, target_is_directory=True)
        return fd

    monkeypatch.setattr(os, "open", swap_after_root_open)
    with pytest.raises(OSError):
        storage.copy("folder/source.bin", "result.bin")
    assert swapped
    assert not (root / "result.bin").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor metadata contract")
def test_copy_preserves_source_mode_and_mtime_without_reopening_source(tmp_path):
    import stat

    root = tmp_path / "inspection"
    root.mkdir()
    source = root / "source.bin"
    source.write_bytes(b"trusted")
    source.chmod(0o640)
    timestamp = 1_600_000_000_000_000_000
    os.utime(source, ns=(timestamp, timestamp))
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    storage.copy("source.bin", "copy.bin")
    dest = root / "copy.bin"
    assert dest.read_bytes() == b"trusted"
    assert stat.S_IMODE(dest.stat().st_mode) == 0o640
    assert dest.stat().st_mtime_ns == timestamp
