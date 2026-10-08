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
