"""Regression of the actual bytes/DB boundary, not only saved SHA metadata."""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import replace
from hashlib import sha256
from io import BytesIO

import pytest

from backend.app.db.enums import DocumentVariantType
from backend.app.document.inspection_qd_kt_issued_pdf_binary_audit import (
    MAX_PDF_BYTES, QdKtIssuedPdfBinaryAuditBlocked, QdKtIssuedPdfBinaryLocator,
    audit_case_issued_pdf_binary_readonly, measure_exact_issued_pdf_bytes,
    resolve_exact_issued_pdf_binary_locator,
)

PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nstartxref\n0\n%%EOF\n"
HASH = sha256(PDF).hexdigest()


def locator():
    return QdKtIssuedPdfBinaryLocator(
        case_id="case-a", decision_id="decision-a",
        binding_id="binding-a", document_id="doc-a",
        document_version_id="version-a",
        variant_type=DocumentVariantType.SCANNED_PDF,
        storage_root="inspection", storage_relative_path="case-a/issued/decision.pdf",
        recorded_checksum_sha256=HASH,
    )


class FakeStorage:
    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = []

    @contextmanager
    def read_stream(self, path, *, root):
        self.calls.append((path, root))
        payload = self.payloads[min(len(self.calls) - 1, len(self.payloads) - 1)]
        if isinstance(payload, BaseException):
            raise payload
        yield BytesIO(payload)


class ScriptedSession:
    no_autoflush = nullcontext()

    def __init__(self, *rows):
        self.rows = rows
        self.calls = 0

    def execute(self, statement):
        assert len(statement.selected_columns) == 18
        self.calls += 1
        return self

    def all(self):
        return [self.rows[min(self.calls - 1, len(self.rows) - 1)]] if self.rows else []


def record(*, case_id="case-a", pdf_type=DocumentVariantType.SCANNED_PDF,
           binding_checksum=HASH, version_checksum=HASH,
           path="case-a/issued/decision.pdf", folder="case-a",
           binding_case="case-a", version_binding="folder-a",
           variant_document="doc-a", family="INSPECTION_QD_KT",
           linked_version="version-a"):
    return (
        "binding-a", linked_version, binding_checksum, "version-a", "variant-a",
        version_checksum, version_binding, "inspection", path,
        "variant-a", variant_document, pdf_type, "doc-a", case_id, family,
        "folder-a", binding_case, folder,
    )


def test_bound_resolver_uses_scalar_db_snapshot_only():
    session = ScriptedSession(record())
    actual = resolve_exact_issued_pdf_binary_locator(
        session, case_id="case-a", decision_id="decision-a",
    )
    assert actual == locator()
    assert session.calls == 1


@pytest.mark.parametrize("changes", [
    {"case_id": "case-b"},
    {"binding_case": "case-b"},
    {"family": "INSPECTION_KE_HOACH_KT"},
    {"variant_document": "doc-b"},
    {"pdf_type": DocumentVariantType.EDITABLE_DOCX},
    {"pdf_type": DocumentVariantType.GENERATED_PDF},
    {"binding_checksum": "b" * 64},
    {"version_checksum": "b" * 64},
    {"linked_version": "version-b"},
    {"version_binding": "folder-b"},
    {"folder": "case-b"},
    {"path": "case-b/issued/decision.pdf"},
    {"path": "case-a/../other/decision.pdf"},
    {"path": "case-a/issued/decision.pdf:stream"},
    {"path": "case-a/issued/NUL.pdf"},
])
def test_foreign_owner_version_drift_and_invalid_path_block_before_io(changes):
    with pytest.raises(QdKtIssuedPdfBinaryAuditBlocked, match="OWNER_OR_SOURCE_DRIFT"):
        resolve_exact_issued_pdf_binary_locator(
            ScriptedSession(record(**changes)),
            case_id="case-a", decision_id="decision-a",
        )


def test_exact_bounded_bytes_produce_narrow_nonlegal_evidence():
    storage = FakeStorage(PDF)
    result = measure_exact_issued_pdf_bytes(storage, locator=locator())
    assert result.verified_sha256 == HASH
    assert result.verified_pdf_bytes == len(PDF)
    assert result.actual_binary_checksum_verified is True
    assert result.basic_pdf_envelope_verified is True
    assert result.signature_cryptographically_verified is False
    assert result.pdf_decision_content_verified is False
    assert result.independent_legal_issuance_verified is False
    assert result.ready_to_render is False
    assert storage.calls == [("case-a/issued/decision.pdf", "inspection")]


@pytest.mark.parametrize("payload,error", [
    (PDF + b"tampered", "PDF_TRAILER_INVALID"),
    (b"not a PDF\n%%EOF", "NOT_PDF"),
    (b"%PDF-1.4\n%%END", "PDF_TRAILER_INVALID"),
    (b"%PDF-1.4\n%%EOF\n\x01", "PDF_TRAILER_INVALID"),
    (b"%PDF-1.4\n%%EOF\n", "CHECKSUM_MISMATCH"),
    (PDF + b"\x00" * (MAX_PDF_BYTES + 1), "TOO_LARGE"),
])
def test_wrong_binary_never_counts_as_verified(payload, error):
    with pytest.raises(QdKtIssuedPdfBinaryAuditBlocked, match=error):
        measure_exact_issued_pdf_bytes(FakeStorage(payload), locator=locator())


@pytest.mark.parametrize("stage", ["read", "chunk", "type", "close"])
def test_invalid_stream_and_lifecycle_fails_closed(stage):
    class BadStorage:
        @contextmanager
        def read_stream(self, path, *, root):
            class Stream:
                def read(self, size):
                    if stage == "read":
                        raise OSError("remote disconnect")
                    if stage == "chunk":
                        return b"x" * (1024 * 1024 + 1)
                    if stage == "type":
                        return None
                    return PDF if not hasattr(self, "sent") else b""
            stream = Stream()
            try:
                yield stream
            finally:
                if stage == "close":
                    raise TimeoutError("remote close failed")
    with pytest.raises(QdKtIssuedPdfBinaryAuditBlocked):
        measure_exact_issued_pdf_bytes(BadStorage(), locator=locator())


def test_invalid_locator_never_opens_storage():
    storage = FakeStorage(PDF)
    with pytest.raises(QdKtIssuedPdfBinaryAuditBlocked, match="LOCATOR_UNPROVEN"):
        measure_exact_issued_pdf_bytes(
            storage, locator=replace(locator(), storage_relative_path="../other.pdf"),
        )
    assert storage.calls == []


def test_trusted_entrypoint_reads_twice_with_three_db_checks():
    storage = FakeStorage(PDF)
    session = ScriptedSession(record())
    actual = audit_case_issued_pdf_binary_readonly(
        session, storage, case_id="case-a", decision_id="decision-a",
    )
    assert actual.actual_binary_checksum_verified
    assert session.calls == 3
    assert len(storage.calls) == 2


def test_trusted_entrypoint_rejects_intermediate_db_drift():
    storage = FakeStorage(PDF)
    session = ScriptedSession(record(), record(path="case-a/issued/replaced.pdf"))
    with pytest.raises(QdKtIssuedPdfBinaryAuditBlocked, match="SOURCE_CHANGED"):
        audit_case_issued_pdf_binary_readonly(
            session, storage, case_id="case-a", decision_id="decision-a",
        )
    assert session.calls == 2
    assert len(storage.calls) == 1


def test_trusted_entrypoint_rejects_final_db_drift():
    storage = FakeStorage(PDF)
    session = ScriptedSession(record(), record(), record(path="case-a/issued/changed.pdf"))
    with pytest.raises(QdKtIssuedPdfBinaryAuditBlocked, match="SOURCE_CHANGED"):
        audit_case_issued_pdf_binary_readonly(
            session, storage, case_id="case-a", decision_id="decision-a",
        )
    assert session.calls == 3
    assert len(storage.calls) == 2


def test_trusted_entrypoint_detects_binary_change_on_second_read():
    storage = FakeStorage(PDF, PDF.replace(b"Catalog", b"CatalogX"))
    with pytest.raises(QdKtIssuedPdfBinaryAuditBlocked, match="CHECKSUM_MISMATCH"):
        audit_case_issued_pdf_binary_readonly(
            ScriptedSession(record()), storage,
            case_id="case-a", decision_id="decision-a",
        )
    assert len(storage.calls) == 2
