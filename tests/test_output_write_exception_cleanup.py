"""The output owner cleans up an exclusive write that raised after creating bytes."""
from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace

import pytest

from backend.app.document import output_version as owner


class _Session:
    def execute(self, _stmt):
        return SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(id="version"))


class _WriteThenRaiseStorage:
    def __init__(self, persisted: bytes):
        self.persisted = persisted
        self.deleted = False

    def write_stream(self, _path, stream, *, root, overwrite):
        assert root == "inspection" and overwrite is False
        assert stream.read() == b"rendered-document"
        raise OSError("simulated storage failure after creating target")

    def exists(self, _path, *, root):
        return self.persisted is not None

    def checksum(self, _path, *, root):
        return sha256(self.persisted).hexdigest()

    def delete(self, _path, *, root):
        self.deleted = True
        self.persisted = None


@pytest.mark.parametrize(
    ("persisted", "should_delete"),
    [(b"rendered-document", True), (b"partial-or-changed", False)],
)
def test_finalization_storage_write_exception_cleans_only_checksum_owned_target(
    monkeypatch, persisted, should_delete,
):
    monkeypatch.setattr(
        owner, "_lock_generation_run_for_output_finalization",
        lambda *_args: SimpleNamespace(id="run"),
    )
    monkeypatch.setattr(owner, "_assert_generation_run_finalizable", lambda *_args: None)
    monkeypatch.setattr(
        owner, "_lock_document_variant_for_output_version",
        lambda *_args: SimpleNamespace(id="variant"),
    )
    for check in (
        "_assert_finalization_allocation_identity",
        "_assert_single_current_version_before_finalization",
        "_assert_finalization_targets_latest_version",
    ):
        monkeypatch.setattr(owner, check, lambda *_args: None)

    storage = _WriteThenRaiseStorage(persisted)
    allocation = owner.OutputVersionAllocation(
        document_id="document", document_variant_id="variant",
        document_version_id="version", generation_run_id="run", version_no=1,
        storage_root="inspection", storage_relative_path="2026/case/rendered.docx",
        original_filename="rendered.docx", storage_binding_id=None,
    )
    with pytest.raises((OSError, RuntimeError), match="simulated storage failure"):
        owner.finalize_output_document_version_write(
            _Session(), storage, allocation, binary_payload=b"rendered-document",
        )
    assert storage.deleted is should_delete
    assert storage.persisted == (None if should_delete else persisted)
