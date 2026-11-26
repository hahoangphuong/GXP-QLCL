"""Template bytes are bounded before the renderer sees a complete snapshot.

Covers generic/legacy nullable checksum and registered SHA-256 templates; no
claims about actual Google operator authentication or legal QĐKT issuance.
"""
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace

import pytest

from backend.app.document.template_binary import (
    TemplateBinaryError, open_template_binary_stream,
)
from backend.app.storage.filesystem import FilesystemStorageService
from backend.app.storage.types import StorageConfig


def _requirement(checksum):
    return SimpleNamespace(
        readiness_status="direct_stream_ready",
        storage_root="template",
        storage_relative_path="gxp/synthetic.dotx",
        checksum_sha256=checksum,
    )


def test_template_binary_exact_boundary_and_snapshot_read(tmp_path, monkeypatch):
    import backend.app.document.template_binary as owner

    root = tmp_path / "templates"
    path = root / "gxp" / "synthetic.dotx"
    path.parent.mkdir(parents=True)
    data = b"synthetic registered template"
    path.write_bytes(data)
    storage = FilesystemStorageService(StorageConfig(
        inspection_root=tmp_path, template_root=root,
    ))
    monkeypatch.setattr(owner, "MAX_TEMPLATE_BINARY_BYTES", len(data))
    with open_template_binary_stream(storage, _requirement(sha256(data).hexdigest())) as stream:
        path.write_bytes(b"different physical storage after verified snapshot")
        assert stream.read() == data
    assert stream.closed
    # A legacy SQL-NULL template can be read under the same cap, but
    # the absence of a checksum does not become a signature/integrity proof.
    path.write_bytes(data)
    with open_template_binary_stream(storage, _requirement(None)) as stream:
        assert stream.read() == data


@pytest.mark.parametrize("has_checksum", [False, True])
def test_template_binary_over_limit_fails_before_renderer_receives_bytes(
    tmp_path, monkeypatch, has_checksum,
):
    import backend.app.document.template_binary as owner

    root = tmp_path / "templates"
    path = root / "gxp" / "synthetic.dotx"
    path.parent.mkdir(parents=True)
    data = b"synthetic template bytes"
    path.write_bytes(data)
    storage = FilesystemStorageService(StorageConfig(
        inspection_root=tmp_path, template_root=root,
    ))
    monkeypatch.setattr(owner, "MAX_TEMPLATE_BINARY_BYTES", len(data) - 1)
    checksum = sha256(data).hexdigest() if has_checksum else None
    with pytest.raises(TemplateBinaryError, match="render size limit"):
        with open_template_binary_stream(storage, _requirement(checksum)):
            pytest.fail("Over-limit source must not be yielded")


@pytest.mark.parametrize("bad_chunk", [
    "text from broken adapter", memoryview(b"unexpected memoryview"),
    b"x" * (1024 * 1024 + 1),
])
def test_template_binary_invalid_storage_chunks_fail_closed_and_release_stream(bad_chunk):
    closed = []

    class UntrustedStorage:
        @contextmanager
        def read_stream(self, path, *, root):
            assert (root, path) == ("template", "gxp/synthetic.dotx")

            class Stream:
                def read(self, maximum):
                    assert maximum == 1024 * 1024
                    return bad_chunk

            try:
                yield Stream()
            finally:
                closed.append(True)

    with pytest.raises(TemplateBinaryError, match="invalid binary chunk"):
        with open_template_binary_stream(UntrustedStorage(), _requirement(None)):
            pytest.fail("Malformed template stream must not be yielded")
    assert closed == [True]


@pytest.mark.parametrize("checksum", [
    "", " ", "0" * 63, "g" * 64, "0" * 65,
])
def test_malformed_template_checksum_never_reclassified_as_legacy_null(checksum):
    class ForbiddenStorage:
        def read_stream(self, *args, **kwargs):
            raise AssertionError("Invalid checksum should be rejected before storage access")

    with pytest.raises(TemplateBinaryError, match="not a valid SHA-256"):
        with open_template_binary_stream(ForbiddenStorage(), _requirement(checksum)):
            pytest.fail("Malformed checksum must not be treated as NULL")


def test_template_binary_checksum_mismatch_blocks_read_with_no_bytes_yielded(tmp_path):
    root = tmp_path / "templates"
    path = root / "gxp" / "synthetic.dotx"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"unexpected source")
    storage = FilesystemStorageService(StorageConfig(
        inspection_root=tmp_path, template_root=root,
    ))
    with pytest.raises(TemplateBinaryError, match="checksum does not match"):
        with open_template_binary_stream(
            storage, _requirement(sha256(b"expected source").hexdigest()),
        ):
            pytest.fail("Tampered template must not be available to renderer")
