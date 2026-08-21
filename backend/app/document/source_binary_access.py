from __future__ import annotations

from contextlib import contextmanager
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
    with storage.read_stream(
        requirement.exact_storage_relative_path,
        root=requirement.exact_storage_root,
    ) as stream:
        yield stream
