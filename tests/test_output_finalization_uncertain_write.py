"""A failed write cannot establish target ownership by matching checksum."""
from types import SimpleNamespace
import pytest

import backend.app.document.output_version as module


class FakeSession:
    def __init__(self, version):
        self.version = version
        self.flushes = 0

    def execute(self, statement):
        return SimpleNamespace(scalar_one_or_none=lambda: self.version)

    def flush(self):
        self.flushes += 1


class UncertainStorage:
    def __init__(self, *, publish):
        self.publish = publish
        self.content = b"same-payload" if not publish else None
        self.deleted = False
        self.checksummed = False

    def write_stream(self, relative_path, stream, *, root, overwrite):
        assert overwrite is False
        if self.publish:
            self.content = stream.read()
        raise OSError("injected uncertain publication failure")

    def exists(self, path, *, root):
        return self.content is not None

    def checksum(self, path, *, root):
        self.checksummed = True
        from hashlib import sha256
        return sha256(self.content).hexdigest()

    def delete(self, path, *, root):
        self.deleted = True
        self.content = None


@pytest.mark.parametrize("published", [False, True])
def test_uncertain_output_write_never_deletes_checksum_matching_target(monkeypatch, published):
    version = SimpleNamespace(id="version", document_variant_id="variant")
    session = FakeSession(version)
    allocation = SimpleNamespace(
        generation_run_id="run", document_version_id="version",
        document_variant_id="variant", storage_root="inspection",
        storage_relative_path="folder/target.docx",
    )
    storage = UncertainStorage(publish=published)
    monkeypatch.setattr(module, "_lock_generation_run_for_output_finalization",
                        lambda *a: SimpleNamespace())
    monkeypatch.setattr(module, "_assert_generation_run_finalizable", lambda *a: None)
    monkeypatch.setattr(module, "_lock_document_variant_for_output_version",
                        lambda *a: SimpleNamespace())
    for name in (
        "_assert_finalization_allocation_identity",
        "_assert_single_current_version_before_finalization",
        "_assert_finalization_targets_latest_version",
    ):
        monkeypatch.setattr(module, name, lambda *a: None)
    with pytest.raises(OSError, match="uncertain publication"):
        module.finalize_output_document_version_write(
            session, storage, allocation, binary_payload=b"same-payload",
        )
    assert storage.content == b"same-payload"
    assert storage.deleted is False
    assert storage.checksummed is False
    assert session.flushes == 0
