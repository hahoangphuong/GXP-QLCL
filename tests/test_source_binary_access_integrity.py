from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

from backend.app.document.source_binary_access import (
    SourceBinaryAccessError,
    open_source_binary_stream,
)
from backend.app.document.source_binary_contract import SourceBinaryRequirement
from backend.app.storage.filesystem import FilesystemStorageService
from backend.app.storage.types import StorageConfig


def _requirement(checksum: str | None) -> SourceBinaryRequirement:
    return SourceBinaryRequirement(
        source_document_id="source",
        source_document_version_id="version-1",
        source_family_code="INSPECTION_PT_PCT",
        storage_binding_id="binding",
        storage_root="inspection",
        folder_relative_path="2026/source",
        exact_storage_root="inspection",
        exact_storage_relative_path="2026/source/document.docx",
        original_filename="document.docx",
        required_bookmarks=("Noidung",),
        legacy_filename_prefix_hints=(),
        readiness_status="direct_stream_ready",
        detail="Registered source binary",
        checksum_sha256=checksum,
    )


def test_source_binary_access_yields_only_checksum_verified_snapshot(tmp_path):
    source = tmp_path / "2026" / "source" / "document.docx"
    source.parent.mkdir(parents=True)
    payload = b"verified source bytes"
    source.write_bytes(payload)
    storage = FilesystemStorageService(StorageConfig(inspection_root=tmp_path))
    requirement = _requirement(sha256(payload).hexdigest())

    with open_source_binary_stream(storage, requirement) as stream:
        # Mutating the physical file after verification must not change the
        # bytes already yielded for copy-forward.
        source.write_bytes(b"replaced after verification")
        assert stream.read() == payload

    with pytest.raises(SourceBinaryAccessError, match="checksum does not match"):
        with open_source_binary_stream(storage, requirement) as stream:
            pytest.fail("Unverified source bytes must never be yielded")


def test_source_binary_access_retains_legacy_unchecksummed_sources(tmp_path):
    source = tmp_path / "2026" / "source" / "document.docx"
    source.parent.mkdir(parents=True)
    payload = b"legacy source has no persisted checksum"
    source.write_bytes(payload)
    storage = FilesystemStorageService(StorageConfig(inspection_root=tmp_path))

    with open_source_binary_stream(storage, _requirement(None)) as stream:
        assert stream.read() == payload


def test_source_binary_access_rejects_not_ready_before_storage_io(tmp_path):
    storage = FilesystemStorageService(StorageConfig(inspection_root=tmp_path))
    requirement = replace(
        _requirement(sha256(b"source").hexdigest()),
        readiness_status="source_variant_inactive",
    )

    with pytest.raises(SourceBinaryAccessError, match="source_variant_inactive"):
        with open_source_binary_stream(storage, requirement):
            pytest.fail("A blocked source must not open storage")


@pytest.mark.parametrize(
    "invalid_checksum",
    ("", " ", "0" * 63, "z" * 64, "0" * 65),
)
def test_source_binary_access_rejects_invalid_registered_checksum_before_io(
    tmp_path, invalid_checksum
):
    storage = FilesystemStorageService(StorageConfig(inspection_root=tmp_path))
    # The locator intentionally does not exist. An invalid checksum must be
    # rejected before StorageService is accessed, not treated as SQL NULL.
    with pytest.raises(
        SourceBinaryAccessError, match="not a valid SHA-256 hex digest"
    ):
        with open_source_binary_stream(storage, _requirement(invalid_checksum)):
            pytest.fail("Invalid persisted checksum must not yield source bytes")


def test_source_binary_access_accepts_uppercase_sha256_hex(tmp_path):
    source = tmp_path / "2026" / "source" / "document.docx"
    source.parent.mkdir(parents=True)
    payload = b"uppercase digest is still a valid SHA-256 representation"
    source.write_bytes(payload)
    storage = FilesystemStorageService(StorageConfig(inspection_root=tmp_path))

    with open_source_binary_stream(
        storage, _requirement(sha256(payload).hexdigest().upper())
    ) as stream:
        assert stream.read() == payload


def test_checksum_source_snapshot_accepts_exact_cap_and_rejects_oversized_input(
    tmp_path, monkeypatch,
):
    import backend.app.document.source_binary_access as source_access

    source = tmp_path / "2026" / "source" / "document.docx"
    source.parent.mkdir(parents=True)
    payload = b"exactly-at-boundary"
    source.write_bytes(payload)
    storage = FilesystemStorageService(StorageConfig(inspection_root=tmp_path))
    requirement = _requirement(sha256(payload).hexdigest())

    monkeypatch.setattr(source_access, "MAX_SOURCE_BINARY_BYTES", len(payload))
    with open_source_binary_stream(storage, requirement) as stream:
        assert stream.read() == payload

    monkeypatch.setattr(source_access, "MAX_SOURCE_BINARY_BYTES", len(payload) - 1)
    with pytest.raises(SourceBinaryAccessError, match="size limit"):
        with open_source_binary_stream(storage, requirement) as stream:
            pytest.fail("Over-limit bytes must never reach the copy-forward consumer")


@pytest.mark.parametrize("bad_chunk", [
    "not-bytes", memoryview(b"byte-view"), b"x" * (1024 * 1024 + 1),
])
def test_checksum_source_snapshot_rejects_nonbytes_or_overlong_storage_chunks(
    bad_chunk,
):
    from contextlib import contextmanager

    closed = []

    class UntrustedStorage:
        @contextmanager
        def read_stream(self, path, *, root):
            assert (root, path) == ("inspection", "2026/source/document.docx")

            class Stream:
                def read(self, size):
                    assert size == 1024 * 1024
                    return bad_chunk

            try:
                yield Stream()
            finally:
                closed.append(True)

    with pytest.raises(SourceBinaryAccessError, match="invalid binary chunk"):
        with open_source_binary_stream(
            UntrustedStorage(), _requirement(sha256(b"source").hexdigest()),
        ) as stream:
            pytest.fail("Untrusted storage data must not be yielded")
    assert closed == [True]


def test_legacy_null_checksum_source_uses_bounded_snapshot_without_claiming_integrity(
    tmp_path, monkeypatch,
):
    """SQL NULL remains allowed, but no unbounded direct storage stream escapes."""
    import backend.app.document.source_binary_access as source_access

    source = tmp_path / "2026" / "source" / "document.docx"
    source.parent.mkdir(parents=True)
    payload = b"legacy-no-checksum"
    source.write_bytes(payload)
    storage = FilesystemStorageService(StorageConfig(inspection_root=tmp_path))

    monkeypatch.setattr(source_access, "MAX_SOURCE_BINARY_BYTES", len(payload))
    with open_source_binary_stream(storage, _requirement(None)) as stream:
        # A bounded legacy snapshot is stable even if storage is replaced
        # after opening. There is no SHA-256 proof for the legacy source.
        source.write_bytes(b"changed after opening")
        assert stream.read() == payload

    source.write_bytes(payload)
    monkeypatch.setattr(source_access, "MAX_SOURCE_BINARY_BYTES", len(payload) - 1)
    with pytest.raises(SourceBinaryAccessError, match="size limit"):
        with open_source_binary_stream(storage, _requirement(None)):
            pytest.fail("Oversized unchecksummed source must not reach copy-forward")


@pytest.mark.parametrize("bad_chunk", [
    "not-bytes", memoryview(b"byte-view"), b"x" * (1024 * 1024 + 1),
])
def test_legacy_null_checksum_source_rejects_invalid_storage_chunks(bad_chunk):
    from contextlib import contextmanager

    closed = []

    class UntrustedStorage:
        @contextmanager
        def read_stream(self, path, *, root):
            assert (root, path) == ("inspection", "2026/source/document.docx")

            class Stream:
                def read(self, size):
                    assert size == 1024 * 1024
                    return bad_chunk

            try:
                yield Stream()
            finally:
                closed.append(True)

    with pytest.raises(SourceBinaryAccessError, match="invalid binary chunk"):
        with open_source_binary_stream(UntrustedStorage(), _requirement(None)):
            pytest.fail("Malformed legacy source must not be yielded")
    assert closed == [True]


def test_legacy_source_snapshot_is_not_a_checksum_recovery_path(tmp_path):
    """Malformed digests are refused even when legacy SQL NULL remains valid."""
    source = tmp_path / "2026" / "source" / "document.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"legacy-source")
    storage = FilesystemStorageService(StorageConfig(inspection_root=tmp_path))
    with pytest.raises(SourceBinaryAccessError, match="not a valid SHA-256"):
        with open_source_binary_stream(storage, _requirement("")):
            pytest.fail("Blank digest must not get legacy exemption")
