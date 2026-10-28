"""Checksum equality is never a safe permission to unlink a mutable pathname."""
from hashlib import sha256

import pytest

from backend.app.document.output_version import cleanup_output_target_if_owned


class RacingStorage:
    def __init__(self, *, present=True):
        self.present = present
        self.deleted = False
        self.checksummed = False

    def exists(self, path, *, root):
        return self.present

    def checksum(self, path, *, root):
        self.checksummed = True
        return sha256(b"matching-bytes").hexdigest()

    def delete(self, path, *, root):
        self.deleted = True
        raise AssertionError("unsafe unversioned delete was called")


@pytest.mark.parametrize("present", [True, False])
def test_cleanup_never_unlinks_without_atomic_generation_guard(present):
    storage = RacingStorage(present=present)
    error = cleanup_output_target_if_owned(
        storage, storage_root="inspection",
        storage_relative_path="2026/example.docx",
        expected_checksum=sha256(b"matching-bytes").hexdigest(),
    )
    if present:
        assert error is not None
        assert "atomic generation-conditional delete" in error
    else:
        assert error is None
    assert storage.deleted is False
    assert storage.checksummed is False


def test_cleanup_missing_checksum_is_not_authorization():
    storage = RacingStorage()
    message = cleanup_output_target_if_owned(
        storage, storage_root="inspection",
        storage_relative_path="2026/example.docx",
        expected_checksum="",
    )
    assert "checksum is unavailable" in message
    assert not storage.deleted
