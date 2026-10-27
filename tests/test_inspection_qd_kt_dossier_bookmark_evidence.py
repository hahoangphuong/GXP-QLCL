"""QĐKT dossier bookmark/date evidence must stay source-bound and fail closed."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from backend.app.document.inspection_qd_kt_cross_system_identity_evidence import (
    QdKtRg3CrosswalkResult,
)
from backend.app.document.inspection_qd_kt_dossier_bookmark_evidence import (
    assess_qdkt_dossier_bookmark_evidence,
    load_qdkt_dossier_bookmark_source_evidence,
)
from backend.app.document.inspection_qd_kt_dotx_binary_audit import (
    QdKtDotxAuditBlocked,
    classify_qdkt_target_bookmark,
    inspect_qdkt_dotx_binary,
    inspect_supplied_qdkt_dotx_set,
)
from backend.app.document.inspection_qd_kt_template_asset_contract import (
    InspectionQdKtTemplateAsset,
)


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"


def _part_xml(*, name: str | None = None, bookmark_id: str = "1", close: bool = True) -> bytes:
    start = "" if name is None else f'<w:bookmarkStart w:id="{bookmark_id}" w:name="{name}"/>'
    end = "" if name is None or not close else f'<w:bookmarkEnd w:id="{bookmark_id}"/>'
    return (
        f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>'
        f'Xét hồ sơ đề nghị</w:t></w:r>{start}<w:r><w:instrText> REF source </w:instrText>'
        f'<w:t>giá trị</w:t></w:r>{end}</w:p></w:body></w:document>'
    ).encode()


def _dotx_bytes(document: bytes, *, headers: dict[str, bytes] | None = None) -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("word/document.xml", document)
        archive.writestr(
            "[Content_Types].xml",
            (
                f'<Types xmlns="{TYPES}"><Override PartName="/word/document.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.'
                'wordprocessingml.template.main+xml"/></Types>'
            ),
        )
        for part, content in (headers or {}).items():
            archive.writestr(part, content)
    return stream.getvalue()


def _asset(content: bytes, gxp_type: str = "GMP") -> InspectionQdKtTemplateAsset:
    filename = f"2. QD KT - {gxp_type}.dotx"
    return InspectionQdKtTemplateAsset(
        gxp_type=gxp_type,
        filename=filename,
        storage_root="template",
        storage_relative_path=filename,
        checksum_sha256=sha256(content).hexdigest(),
    )


def _audit(tmp_path: Path, *, gxp_type: str, target: str | None = None):
    content = _dotx_bytes(_part_xml(name=target))
    path = tmp_path / f"{gxp_type}.dotx"
    path.write_bytes(content)
    return inspect_qdkt_dotx_binary(path, asset=_asset(content, gxp_type))


def _proven_crosswalk(**changes: object) -> QdKtRg3CrosswalkResult:
    result = QdKtRg3CrosswalkResult(
        status="IDENTITY_PROVEN_SEMANTICS_PARTIAL",
        legacy_inspection_id=42,
        case_id="case-42",
        same_worksheet_row=True,
        same_inspection_record=True,
        same_registered_site=True,
        same_canonical_case=True,
        same_application=True,
        dossier_value_projection_verified=True,
        dossier_value_present=True,
        submitted_value_projection_verified=True,
        submitted_value_present=True,
    )
    return replace(result, **changes)


def test_audit_scans_document_header_footer_and_records_span_context(tmp_path: Path) -> None:
    content = _dotx_bytes(
        _part_xml(name="HsDK"),
        headers={
            "word/header1.xml": _part_xml(name="NgaynopHsDK", bookmark_id="2"),
            "word/footer1.xml": _part_xml(name=None),
        },
    )
    path = tmp_path / "source.dotx"
    path.write_bytes(content)

    audit = inspect_qdkt_dotx_binary(path, asset=_asset(content))

    assert audit.scanned_word_parts == (
        "word/document.xml",
        "word/footer1.xml",
        "word/header1.xml",
    )
    assert {span.name for span in audit.bookmark_spans} == {"HsDK", "NgaynopHsDK"}
    dossier = next(span for span in audit.bookmark_spans if span.name == "NgaynopHsDK")
    assert dossier.part_name == "word/header1.xml"
    assert dossier.start_location.startswith("/w:document[1]/w:body[1]/w:p[1]")
    assert dossier.end_location.startswith("/w:document[1]/w:body[1]/w:p[1]")
    assert dossier.paragraph_text == "Xét hồ sơ đề nghịgiá trị"
    assert dossier.field_code_text == "REF source"
    assert audit.dossier_plain_text_paragraph_count == 3
    assert classify_qdkt_target_bookmark(audit, "NgaynopHsDK").status == "EXACT_PRESENT"


def test_target_classification_is_case_sensitive_and_absence_is_explicit(tmp_path: Path) -> None:
    case_variant = _audit(tmp_path, gxp_type="GMP", target="ngaynophsdk")
    assert classify_qdkt_target_bookmark(case_variant, "NgaynopHsDK").status == "CASE_VARIANT_ONLY"
    assert classify_qdkt_target_bookmark(case_variant, "HsDK").status == "ABSENT"


def test_duplicate_name_across_word_parts_fails_closed(tmp_path: Path) -> None:
    content = _dotx_bytes(
        _part_xml(name="HsDK"),
        headers={"word/header1.xml": _part_xml(name="HsDK", bookmark_id="2")},
    )
    path = tmp_path / "source.dotx"
    path.write_bytes(content)
    with pytest.raises(QdKtDotxAuditBlocked, match="QDKT_DOTX_BOOKMARK_STRUCTURE_UNVERIFIED"):
        inspect_qdkt_dotx_binary(path, asset=_asset(content))


def test_unclosed_bookmark_in_header_fails_closed(tmp_path: Path) -> None:
    content = _dotx_bytes(
        _part_xml(name=None),
        headers={"word/header1.xml": _part_xml(name="HsDK", close=False)},
    )
    path = tmp_path / "source.dotx"
    path.write_bytes(content)
    with pytest.raises(QdKtDotxAuditBlocked, match="QDKT_DOTX_BOOKMARK_STRUCTURE_UNVERIFIED"):
        inspect_qdkt_dotx_binary(path, asset=_asset(content))


def test_nested_and_overlapping_spans_are_detected_without_becoming_targets(tmp_path: Path) -> None:
    xml = (
        f'<w:document xmlns:w="{W}"><w:body><w:p>'
        '<w:bookmarkStart w:id="1" w:name="Outer"/>'
        '<w:bookmarkStart w:id="2" w:name="Inner"/>'
        '<w:bookmarkEnd w:id="1"/><w:bookmarkEnd w:id="2"/>'
        '</w:p></w:body></w:document>'
    ).encode()
    content = _dotx_bytes(xml)
    path = tmp_path / "source.dotx"
    path.write_bytes(content)
    audit = inspect_qdkt_dotx_binary(path, asset=_asset(content))
    assert audit.nested_bookmark_pairs == (("Outer", "Inner"),)
    assert audit.overlapping_bookmark_pairs == (("Inner", "Outer"),)
    assert classify_qdkt_target_bookmark(audit, "HsDK").status == "ABSENT"


def test_source_contract_closes_submission_semantics_without_claiming_receipt() -> None:
    evidence = load_qdkt_dossier_bookmark_source_evidence()
    assert evidence.workbook_sheet == "db.ktra"
    assert evidence.registration_group_label == "ĐĂNG KÝ"
    assert evidence.submission_header == "Ngày nộp"
    assert evidence.dossier_header == "Mã hồ sơ"
    assert evidence.submission_named_ranges == ("db_NgayDky_ktra", "Ngay_nop_HS")
    assert evidence.date_semantics == "DOSSIER_SUBMISSION_DATE"
    assert evidence.receipt_date_equivalence is False
    assert evidence.date_display_transform == "Replace('-', '/')"
    assert evidence.canonical_date_timezone_rule == "PARTIAL_UNPROVEN_BUSINESS_TIMEZONE"
    assert evidence.contains_raw_business_values is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["date_semantics"].update(
            business_meaning="DOSSIER_RECEIPT_DATE"
        ),
        lambda payload: payload["templates"][0]["targets"]["HsDK"].update(
            status="VERIFIED_PRESENT"
        ),
    ],
)
def test_source_evidence_semantic_or_physical_drift_fails_closed(
    tmp_path: Path,
    mutate,
) -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "artifacts/legacy_audit/inspection_qd_kt_dossier_bookmark_source_evidence.json"
    )
    payload = json.loads(source.read_text(encoding="utf-8"))
    mutate(payload)
    path = tmp_path / "source-evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="QDKT_DOSSIER"):
        load_qdkt_dossier_bookmark_source_evidence(path)


def test_synthetic_absence_proves_gate_behavior_but_not_original_template_identity(tmp_path: Path) -> None:
    audits = tuple(
        _audit(tmp_path, gxp_type=gxp_type)
        for gxp_type in ("GLP", "GMP", "GMPbb", "GSP")
    )
    result = assess_qdkt_dossier_bookmark_evidence(
        template_audits=audits,
        crosswalk=_proven_crosswalk(),
        allow_synthetic_template_checksums=True,
    )
    assert result.status == "SYNTHETIC_PHYSICAL_BEHAVIOR_ONLY"
    assert result.template_identity_verified is False
    assert result.legacy_assignment_chain_verified is True
    assert result.canonical_case_application_site_verified is True
    assert result.ready_to_render is False
    rows = {row.bookmark_name: row for row in result.fields}
    assert rows["HsDK"].business_semantics == "DOSSIER_CODE"
    assert rows["HsDK"].canonical_mapping_confidence == "VERIFIED"
    assert rows["NgaynopHsDK"].business_semantics == "DOSSIER_SUBMISSION_DATE"
    assert rows["NgaynopHsDK"].canonical_mapping_confidence == "PARTIAL"
    assert all(row.physical_bookmark_status == "SYNTHETIC_ABSENT" for row in rows.values())


@pytest.mark.parametrize(
    "status",
    [
        "NO_MATCHING_CANONICAL_CASE",
        "AMBIGUOUS_CANONICAL_CASE",
        "SOURCE_ROW_CHANGED_AFTER_IMPORT",
        "SITE_IDENTITY_CONFLICT",
        "MISSING_CANONICAL_APPLICATION",
        "AMBIGUOUS_CANONICAL_APPLICATION",
        "APPLICATION_CASE_IDENTITY_CONFLICT",
        "DOSSIER_VALUE_CONFLICT",
        "SUBMISSION_VALUE_CONFLICT",
        "AMBIGUOUS_SUBMISSION_DATE",
        "MISSING_LEGACY_INSPECTION_ID",
    ],
)
def test_canonical_or_date_conflict_never_reaches_verified_gate(tmp_path: Path, status: str) -> None:
    audits = tuple(_audit(tmp_path, gxp_type=kind) for kind in ("GLP", "GMP", "GMPbb", "GSP"))
    result = assess_qdkt_dossier_bookmark_evidence(
        template_audits=audits,
        crosswalk=_proven_crosswalk(status=status),
        allow_synthetic_template_checksums=True,
    )
    assert result.status == f"CANONICAL_PROVENANCE_BLOCKED:{status}"
    assert result.canonical_case_application_site_verified is False
    assert result.ready_to_render is False


def test_khkt_without_rg3_lineage_is_separate_and_blocked(tmp_path: Path) -> None:
    audits = tuple(_audit(tmp_path, gxp_type=kind) for kind in ("GLP", "GMP", "GMPbb", "GSP"))
    result = assess_qdkt_dossier_bookmark_evidence(
        template_audits=audits,
        crosswalk=QdKtRg3CrosswalkResult(status="KHKT_PATH_HAS_NO_RG3_SELECTION"),
        allow_synthetic_template_checksums=True,
    )
    assert result.status == "KHKT_PATH_HAS_NO_RG3_LINEAGE"
    assert result.ready_to_render is False


@pytest.mark.parametrize("missing", ["dossier_value_present", "submitted_value_present"])
def test_equal_null_values_do_not_satisfy_required_dossier_presence(
    tmp_path: Path,
    missing: str,
) -> None:
    audits = tuple(_audit(tmp_path, gxp_type=kind) for kind in ("GLP", "GMP", "GMPbb", "GSP"))
    result = assess_qdkt_dossier_bookmark_evidence(
        template_audits=audits,
        crosswalk=_proven_crosswalk(**{missing: False}),
        allow_synthetic_template_checksums=True,
    )
    assert result.status == "REQUIRED_DOSSIER_VALUES_MISSING"
    assert result.ready_to_render is False


def test_template_set_cannot_be_partial(tmp_path: Path) -> None:
    audits = tuple(_audit(tmp_path, gxp_type=kind) for kind in ("GLP", "GMP", "GSP"))
    result = assess_qdkt_dossier_bookmark_evidence(
        template_audits=audits,
        crosswalk=_proven_crosswalk(),
        allow_synthetic_template_checksums=True,
    )
    assert result.status == "TEMPLATE_SET_UNVERIFIED"
    assert result.ready_to_render is False


def test_local_authoritative_binaries_reproduce_absence_when_available() -> None:
    template_dir = Path(__file__).resolve().parents[1] / "legacy" / "Templates"
    if not template_dir.is_dir():
        pytest.skip("authoritative ignored legacy templates are not present")
    audits = inspect_supplied_qdkt_dotx_set(template_dir)
    assert {row.gxp_type for row in audits} == {"GLP", "GMP", "GMPbb", "GSP"}
    assert all(classify_qdkt_target_bookmark(row, "HsDK").status == "ABSENT" for row in audits)
    assert all(classify_qdkt_target_bookmark(row, "NgaynopHsDK").status == "ABSENT" for row in audits)
    assert all(row.binary_checksum_verified and not row.ready_to_render for row in audits)
    result = assess_qdkt_dossier_bookmark_evidence(
        template_audits=audits,
        crosswalk=_proven_crosswalk(),
    )
    assert result.status == "PHYSICAL_BOOKMARKS_VERIFIED_ABSENT"
    assert result.template_identity_verified is True
    assert all(row.physical_bookmark_status == "VERIFIED_ABSENT" for row in result.fields)
    assert result.ready_to_render is False
