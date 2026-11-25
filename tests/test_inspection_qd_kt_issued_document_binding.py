"""Exact issued QĐKT PDF source policy; stored metadata is never binary proof."""
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from backend.app.db.enums import DocumentVariantType
from backend.app.document.inspection_qd_kt_issued_document_binding import (
    QdKtIssuedDocumentBlocked, require_exact_qdkt_issued_pdf_version,
)


class ScalarSession:
    no_autoflush = nullcontext()

    def __init__(self, *rows):
        self.rows = rows
        self.calls = 0

    def execute(self, statement):
        self.calls += 1
        assert len(statement.selected_columns) == 15
        return self

    def all(self):
        return list(self.rows)


def row(*, case="case-a", family="INSPECTION_QD_KT",
        variant=DocumentVariantType.SIGNED_PDF, checksum="a" * 64,
        binding="binding-a", binding_case="case-a",
        root="inspection", path="case-a/issued/q.pdf", folder="case-a",
        version_variant="variant-a", variant_id="variant-a",
        variant_document="doc-a", document_id="doc-a"):
    return (
        "version-a", version_variant, variant_id, variant_document,
        variant, document_id, case, family, checksum,
        binding, root, path, binding, binding_case, folder,
    )


@pytest.mark.parametrize("variant", [
    DocumentVariantType.SIGNED_PDF, DocumentVariantType.SCANNED_PDF,
])
def test_only_external_pdf_variant_metadata_links_without_verification(variant):
    session = ScalarSession(row(variant=variant))
    result = require_exact_qdkt_issued_pdf_version(
        session, case_id="case-a", document_version_id="version-a")
    assert result["recorded_checksum_sha256"] == "a" * 64
    assert result["variant_type"] == variant.value
    assert session.calls == 1


@pytest.mark.parametrize("variant", [
    DocumentVariantType.EDITABLE_DOCX, DocumentVariantType.GENERATED_PDF,
    DocumentVariantType.EDITABLE_XLSX, None,
])
def test_draft_generated_or_other_variant_never_acts_as_external_pdf(variant):
    with pytest.raises(QdKtIssuedDocumentBlocked, match="VARIANT_INVALID"):
        require_exact_qdkt_issued_pdf_version(
            ScalarSession(row(variant=variant)),
            case_id="case-a", document_version_id="version-a")


@pytest.mark.parametrize("changes,reason", [
    ({"case": "case-b"}, "OWNER_MISMATCH"),
    ({"family": "INSPECTION_KE_HOACH_KT"}, "OWNER_MISMATCH"),
    ({"version_variant": "other-variant"}, "OWNER_MISMATCH"),
    ({"variant_document": "other-doc"}, "OWNER_MISMATCH"),
    ({"checksum": None}, "CHECKSUM_MISSING"),
    ({"checksum": "z" * 64}, "CHECKSUM_MISSING"),
    ({"binding": None}, "STORAGE_OWNER_MISMATCH"),
    ({"binding_case": "case-b"}, "STORAGE_OWNER_MISMATCH"),
    ({"root": "other"}, "STORAGE_OWNER_MISMATCH"),
    ({"folder": "case-b"}, "STORAGE_OWNER_MISMATCH"),
    ({"path": "case-b/issued/q.pdf"}, "STORAGE_OWNER_MISMATCH"),
    ({"path": "../case-a/issued/q.pdf"}, "STORAGE_OWNER_MISMATCH"),
    ({"path": "case-a/../case-b/q.pdf"}, "STORAGE_OWNER_MISMATCH"),
    ({"path": "case-a/issued/q.pdf:stream"}, "STORAGE_OWNER_MISMATCH"),
    ({"path": "case-a/issued/COM¹.pdf"}, "STORAGE_OWNER_MISMATCH"),
    ({"path": "case-a/issued/q\u202e.pdf"}, "STORAGE_OWNER_MISMATCH"),
])
def test_no_foreign_case_storage_or_forged_checksum(changes, reason):
    with pytest.raises(QdKtIssuedDocumentBlocked, match=reason):
        require_exact_qdkt_issued_pdf_version(
            ScalarSession(row(**changes)),
            case_id="case-a", document_version_id="version-a")


def test_missing_source_rejected_without_fallback():
    with pytest.raises(QdKtIssuedDocumentBlocked, match="VERSION_NOT_FOUND"):
        require_exact_qdkt_issued_pdf_version(
            ScalarSession(), case_id="case-a", document_version_id="version-a")
