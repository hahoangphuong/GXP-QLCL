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


@pytest.mark.skipif(os.name != "posix", reason="POSIX fd ownership contract")
def test_failed_fdopen_closes_every_descriptor(tmp_path, monkeypatch):
    root = tmp_path / "inspection"
    (root / "folder").mkdir(parents=True)
    (root / "folder" / "document.bin").write_bytes(b"safe")
    storage = LocalStorageService(StorageConfig(inspection_root=root))

    original_open = os.open
    acquired = []

    def capture_open(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        acquired.append(fd)
        return fd

    def fail_fdopen(*args, **kwargs):
        raise OSError("synthetic fdopen conversion failure")

    monkeypatch.setattr(os, "open", capture_open)
    monkeypatch.setattr(os, "fdopen", fail_fdopen)
    with pytest.raises(OSError, match="synthetic fdopen conversion failure"):
        with storage.read_stream("folder/document.bin") as stream:
            stream.read()
    assert len(acquired) == 3  # root, nested directory, regular source
    for fd in acquired:
        with pytest.raises(OSError):
            os.fstat(fd)


@pytest.mark.skipif(os.name != "posix", reason="POSIX fd ownership contract")
def test_failed_fdopen_on_top_level_file_closes_root_and_file(tmp_path, monkeypatch):
    root = tmp_path / "inspection"
    root.mkdir()
    (root / "document.bin").write_bytes(b"safe")
    storage = LocalStorageService(StorageConfig(inspection_root=root))

    original_open = os.open
    acquired = []

    def capture_open(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        acquired.append(fd)
        return fd

    monkeypatch.setattr(os, "open", capture_open)
    monkeypatch.setattr(os, "fdopen", lambda *args, **kwargs: (_ for _ in ()).throw(
        ValueError("synthetic wrapper rejected mode")
    ))
    with pytest.raises(ValueError, match="synthetic wrapper rejected mode"):
        with storage.read_stream("document.bin") as stream:
            stream.read()
    assert len(acquired) == 2
    for fd in acquired:
        with pytest.raises(OSError):
            os.fstat(fd)


@pytest.mark.skipif(os.name != "posix", reason="POSIX anchored write contract")
@pytest.mark.parametrize("overwrite", [False, True])
def test_write_parent_swap_cannot_publish_outside_root(tmp_path, overwrite):
    from io import BytesIO

    root = tmp_path / "inspection"
    outside = tmp_path / "outside"
    (root / "parent").mkdir(parents=True)
    outside.mkdir()
    (outside / "draft.docx").write_bytes(b"outside-original")
    storage = LocalStorageService(StorageConfig(inspection_root=root))

    class SwappingStream(BytesIO):
        swapped = False
        def read(self, n=-1):
            if not self.swapped:
                self.swapped = True
                (root / "parent").rename(root / "original-parent")
                (root / "parent").symlink_to(outside, target_is_directory=True)
            return super().read(n)

    # The held directory descriptor permits safe publication into the
    # original in-root directory even after its pathname is swapped.
    entry = storage.write_stream("parent/draft.docx", SwappingStream(b"new-bytes"), overwrite=overwrite)
    assert entry.relative_path == "parent/draft.docx"
    assert entry.size == len(b"new-bytes")
    assert (outside / "draft.docx").read_bytes() == b"outside-original"
    assert (root / "original-parent" / "draft.docx").read_bytes() == b"new-bytes"
    assert not list((root / "original-parent").glob(".gxp-stage-*"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX anchored write contract")
def test_write_symlink_parent_rejected_without_external_write(tmp_path):
    from io import BytesIO

    root = tmp_path / "inspection"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "alias").symlink_to(outside, target_is_directory=True)
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    with pytest.raises(OSError):
        storage.write_stream("alias/file.docx", BytesIO(b"forbidden"))
    assert not (outside / "file.docx").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-replace contract")
def test_descriptor_write_exclusive_preserves_existing_target(tmp_path):
    from io import BytesIO

    root = tmp_path / "inspection"
    root.mkdir()
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    storage.write_stream("child/draft.docx", BytesIO(b"first"), overwrite=False)
    from backend.app.storage.types import StorageTargetExistsError
    with pytest.raises(StorageTargetExistsError):
        storage.write_stream("child/draft.docx", BytesIO(b"second"), overwrite=False)
    assert (root / "child" / "draft.docx").read_bytes() == b"first"
    assert not list((root / "child").glob(".gxp-stage-*"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX fd-anchored write publication")
def test_write_result_does_not_reopen_swapped_parent_after_publish(tmp_path, monkeypatch):
    from io import BytesIO

    root = tmp_path / "inspection"
    outside = tmp_path / "outside"
    (root / "folder").mkdir(parents=True)
    outside.mkdir()
    (outside / "document.bin").write_bytes(b"outside-unchanged")
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    original_replace = os.replace
    swapped = False

    def swap_parent_after_publish(source, destination, *args, **kwargs):
        nonlocal swapped
        result = original_replace(source, destination, *args, **kwargs)
        if not swapped and kwargs.get("src_dir_fd") is not None:
            swapped = True
            (root / "folder").rename(root / "original")
            (root / "folder").symlink_to(outside, target_is_directory=True)
        return result

    monkeypatch.setattr(os, "replace", swap_parent_after_publish)
    result = storage.write_stream("folder/document.bin", BytesIO(b"verified"), overwrite=True)
    assert swapped
    assert result.relative_path == "folder/document.bin"
    assert result.name == "document.bin"
    assert result.size == len(b"verified")
    assert not result.is_dir
    assert (root / "original" / "document.bin").read_bytes() == b"verified"
    assert (outside / "document.bin").read_bytes() == b"outside-unchanged"


@pytest.mark.skipif(os.name != "posix", reason="POSIX fd-anchored write publication")
def test_write_entry_reports_actual_bytes_from_staged_descriptor(tmp_path):
    from io import BytesIO

    root = tmp_path / "inspection"
    root.mkdir()
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    for overwrite in (True, False):
        name = "overwrite.bin" if overwrite else "exclusive.bin"
        entry = storage.write_stream(name, BytesIO(b"abc" * 13), overwrite=overwrite)
        assert entry.relative_path == name
        assert entry.name == name
        assert entry.size == 39
        assert entry.is_dir is False
        assert (root / name).read_bytes() == b"abc" * 13


@pytest.mark.skipif(os.name != "posix", reason="POSIX fd-anchored staging contract")
@pytest.mark.parametrize("overwrite", [False, True])
def test_write_midstream_failure_removes_private_staging_and_preserves_target(tmp_path, overwrite):
    from io import BytesIO

    root = tmp_path / "inspection"
    (root / "folder").mkdir(parents=True)
    (root / "folder" / "document.bin").write_bytes(b"original")
    storage = LocalStorageService(StorageConfig(inspection_root=root))

    class FailingInput(BytesIO):
        reads = 0

        def read(self, size=-1):
            self.reads += 1
            if self.reads == 2:
                raise OSError("synthetic input failure")
            return super().read(size)

    with pytest.raises(OSError, match="synthetic input failure"):
        storage.write_stream("folder/document.bin", FailingInput(b"partial"), overwrite=overwrite)
    assert (root / "folder" / "document.bin").read_bytes() == b"original"
    assert list((root / "folder").glob(".gxp-stage-*")) == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory fd contract")
def test_write_midstream_parent_swap_does_not_delete_outside_staging(tmp_path):
    from io import BytesIO

    root = tmp_path / "inspection"
    outside = tmp_path / "outside"
    (root / "folder").mkdir(parents=True)
    outside.mkdir()
    (outside / ".gxp-stage-keep.tmp").write_bytes(b"outside")
    storage = LocalStorageService(StorageConfig(inspection_root=root))

    class SwapThenFail(BytesIO):
        called = False

        def read(self, size=-1):
            if not self.called:
                self.called = True
                (root / "folder").rename(root / "original")
                (root / "folder").symlink_to(outside, target_is_directory=True)
                raise OSError("synthetic swap failure")
            return super().read(size)

    with pytest.raises(OSError, match="synthetic swap failure"):
        storage.write_stream("folder/document.bin", SwapThenFail(b"irrelevant"))
    assert (outside / ".gxp-stage-keep.tmp").read_bytes() == b"outside"
    assert not (outside / "document.bin").exists()
    assert list((root / "original").glob(".gxp-stage-*")) == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX fdopen ownership")
def test_write_fdopen_failure_cleans_staging_and_closes_descriptors(tmp_path, monkeypatch):
    from io import BytesIO

    root = tmp_path / "inspection"
    (root / "folder").mkdir(parents=True)
    storage = LocalStorageService(StorageConfig(inspection_root=root))
    original_fdopen = os.fdopen
    original_open = os.open
    acquired = []

    def track_open(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        acquired.append(fd)
        return fd

    def fail_staging_fdopen(fd, mode="r", *args, **kwargs):
        if mode == "wb":
            raise OSError("synthetic staging wrapper failure")
        return original_fdopen(fd, mode, *args, **kwargs)

    monkeypatch.setattr(os, "open", track_open)
    monkeypatch.setattr(os, "fdopen", fail_staging_fdopen)
    with pytest.raises(OSError, match="synthetic staging wrapper failure"):
        storage.write_stream("folder/file.bin", BytesIO(b"content"))
    assert not (root / "folder" / "file.bin").exists()
    assert list((root / "folder").glob(".gxp-stage-*")) == []
    assert len(acquired) == 3
    for fd in acquired:
        with pytest.raises(OSError):
            os.fstat(fd)
