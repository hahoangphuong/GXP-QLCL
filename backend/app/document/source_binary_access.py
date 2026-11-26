from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, Iterator

from backend.app.document.source_binary_contract import SourceBinaryRequirement
from backend.app.storage.types import StorageServiceProtocol


class SourceBinaryAccessError(RuntimeError):
    pass


# Bound the snapshot before any copy-forward consumer gets its bytes.
# A stale/oversized source must not exhaust a worker's temporary disk.
MAX_SOURCE_BINARY_BYTES = 256 * 1024 * 1024
SOURCE_READ_CHUNK_BYTES = 1024 * 1024


@contextmanager
def open_source_binary_stream(
    storage: StorageServiceProtocol,
    requirement: SourceBinaryRequirement,
) -> Iterator[BinaryIO]:
    if requirement.readiness_status != "direct_stream_ready":
        raise SourceBinaryAccessError(
            f"Source binary is not ready for direct access: {requirement.readiness_status}."
        )
    if requirement.exact_storage_root is None or requirement.exact_storage_relative_path is None:
        raise SourceBinaryAccessError("Source binary locator is incomplete.")
    registered_checksum = requirement.checksum_sha256
    # Only SQL NULL is a legacy source with no registered digest; it remains
    # *unverified*, but must obey the same bounded byte-stream contract.
    # A blank/malformed persisted digest is corruption, not an exemption.
    if registered_checksum is not None and (
        not isinstance(registered_checksum, str)
        or len(registered_checksum) != 64
        or any(char not in "0123456789abcdefABCDEF" for char in registered_checksum)
    ):
        raise SourceBinaryAccessError(
            "Persisted source checksum is not a valid SHA-256 hex digest."
        )
    expected_checksum = (
        registered_checksum.lower() if registered_checksum is not None else None
    )

    # Snapshot the complete bounded source before yielding it to copy-forward.
    # Verify the digest when one is registered; legacy SQL-NULL sources still
    # have no integrity proof and must never be described as checksum-verified.
    with SpooledTemporaryFile(max_size=8 * 1024 * 1024) as verified:
        digest = sha256()
        total_bytes = 0
        with storage.read_stream(
            requirement.exact_storage_relative_path,
            root=requirement.exact_storage_root,
        ) as stream:
            while True:
                chunk = stream.read(SOURCE_READ_CHUNK_BYTES)
                if type(chunk) is not bytes or len(chunk) > SOURCE_READ_CHUNK_BYTES:
                    raise SourceBinaryAccessError(
                        "Source storage returned an invalid binary chunk."
                    )
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_SOURCE_BINARY_BYTES:
                    raise SourceBinaryAccessError(
                        "Source binary exceeds the copy-forward size limit."
                    )
                digest.update(chunk)
                verified.write(chunk)
        if expected_checksum is not None and digest.hexdigest() != expected_checksum:
            raise SourceBinaryAccessError(
                "Source binary checksum does not match the persisted document version."
            )
        verified.seek(0)
        yield verified
