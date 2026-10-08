from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, Iterator

from backend.app.document.source_binary_contract import SourceBinaryRequirement
from backend.app.storage.types import StorageServiceProtocol


class SourceBinaryAccessError(RuntimeError):
    pass


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
    if registered_checksum is None:
        # Only SQL NULL means a legacy source never registered a checksum.
        # A persisted blank or malformed digest is corrupt metadata, not
        # evidence that this source is exempt from integrity verification.
        with storage.read_stream(
            requirement.exact_storage_relative_path,
            root=requirement.exact_storage_root,
        ) as stream:
            yield stream
        return

    if (
        not isinstance(registered_checksum, str)
        or len(registered_checksum) != 64
        or any(char not in "0123456789abcdefABCDEF" for char in registered_checksum)
    ):
        raise SourceBinaryAccessError(
            "Persisted source checksum is not a valid SHA-256 hex digest."
        )
    expected_checksum = registered_checksum.lower()

    # Consume the full source once and verify the exact snapshot that will
    # be read by copy-forward. Never yield unverified or partially read bytes.
    with SpooledTemporaryFile(max_size=8 * 1024 * 1024) as verified:
        digest = sha256()
        with storage.read_stream(
            requirement.exact_storage_relative_path,
            root=requirement.exact_storage_root,
        ) as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                verified.write(chunk)
        if digest.hexdigest() != expected_checksum:
            raise SourceBinaryAccessError(
                "Source binary checksum does not match the persisted document version."
            )
        verified.seek(0)
        yield verified
