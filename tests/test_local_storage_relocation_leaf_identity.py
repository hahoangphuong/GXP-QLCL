"""Detect source leaf replacement while POSIX relocation prepares destination."""
import os
import sys

import pytest

from backend.app.storage.local import LocalStorageService
from backend.app.storage.types import StorageConfig, StorageOperationError


@pytest.mark.skipif(os.name != "posix" or not sys.platform.startswith("linux"), reason="Linux dirfd relocation")
@pytest.mark.parametrize("operation", ["move", "rename"])
@pytest.mark.parametrize("replacement", ["file", "symlink", "missing"])
def test_relocation_rejects_changed_source_leaf_before_publish(tmp_path, monkeypatch, operation, replacement):
    root = tmp_path / "root"
    (root / "target_parent").mkdir(parents=True)
    (root / "source.bin").write_bytes(b"original")
    (root / "replacement.bin").write_bytes(b"replacement")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    service = LocalStorageService(StorageConfig(inspection_root=root))
    original_open = os.open
    swapped = False

    def race_on_destination_root(path, *args, **kwargs):
        nonlocal swapped
        fd = original_open(path, *args, **kwargs)
        # Two root opens: the first is source; the second is destination.
        if path == root and len(root_opens) == 1 and not swapped:
            swapped = True
            (root / "source.bin").rename(root / "retained-original.bin")
            if replacement == "file":
                (root / "replacement.bin").rename(root / "source.bin")
            elif replacement == "symlink":
                (root / "source.bin").symlink_to(outside)
        if path == root:
            root_opens.append(fd)
        return fd

    root_opens = []
    monkeypatch.setattr(os, "open", race_on_destination_root)
    with pytest.raises(StorageOperationError, match="source changed before publication"):
        if operation == "move":
            service.move("source.bin", "target_parent/renamed.bin")
        else:
            service.rename("source.bin", "renamed.bin")
    assert swapped
    assert (root / "retained-original.bin").read_bytes() == b"original"
    assert not (root / "target_parent/renamed.bin").exists()
    assert not (root / "renamed.bin").exists()
    assert outside.read_bytes() == b"outside"


@pytest.mark.skipif(os.name != "posix" or not sys.platform.startswith("linux"), reason="Linux dirfd relocation")
def test_relocation_no_false_positive_on_unchanged_source(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "source.bin").write_bytes(b"trusted")
    service = LocalStorageService(StorageConfig(inspection_root=root))
    result = service.move("source.bin", "nested/target.bin")
    assert result.size == len(b"trusted")
    assert (root / "nested/target.bin").read_bytes() == b"trusted"
