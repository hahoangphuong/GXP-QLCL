"""Fault-injection tests for POSIX staged write publication durability ordering."""
import os
import sys
from io import BytesIO

import pytest

from backend.app.storage.local import LocalStorageService
from backend.app.storage.types import StorageConfig


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory descriptor semantics")
@pytest.mark.parametrize("overwrite", [True, False])
def test_posix_write_fsyncs_stage_before_publication_and_parent_after(tmp_path, monkeypatch, overwrite):
    if not overwrite and not sys.platform.startswith("linux"):
        pytest.skip("atomic no-replace publication requires Linux")
    root = tmp_path / "root"
    root.mkdir()
    service = LocalStorageService(StorageConfig(inspection_root=root))
    calls = []
    actual_fsync = os.fsync

    def traced(fd):
        mode = os.fstat(fd).st_mode
        import stat
        calls.append("directory" if stat.S_ISDIR(mode) else "file")
        return actual_fsync(fd)

    monkeypatch.setattr(os, "fsync", traced)
    result = service.write_stream("folder/durable.txt", BytesIO(b"payload"), overwrite=overwrite)
    assert result.size == 7
    assert (root / "folder" / "durable.txt").read_bytes() == b"payload"
    assert calls == ["file", "directory"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor semantics")
def test_stage_fsync_failure_preserves_existing_destination_and_cleans_stage(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    existing = root / "old.txt"
    existing.write_bytes(b"old")
    service = LocalStorageService(StorageConfig(inspection_root=root))
    real_fsync = os.fsync

    def fail_file(fd):
        import stat
        if stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("injected staging fsync failure")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_file)
    with pytest.raises(OSError, match="injected staging fsync"):
        service.write_stream("old.txt", BytesIO(b"new"), overwrite=True)
    assert existing.read_bytes() == b"old"
    assert not any(x.name.startswith(".gxp-stage-") for x in root.iterdir())


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor semantics")
def test_directory_fsync_failure_does_not_unlink_published_destination(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    service = LocalStorageService(StorageConfig(inspection_root=root))
    real_fsync = os.fsync

    def fail_directory(fd):
        import stat
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("injected directory fsync failure")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_directory)
    with pytest.raises(OSError, match="injected directory fsync"):
        service.write_stream("new.txt", BytesIO(b"published"), overwrite=True)
    assert (root / "new.txt").read_bytes() == b"published"
    assert not any(x.name.startswith(".gxp-stage-") for x in root.iterdir())
