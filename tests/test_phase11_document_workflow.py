from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState, DocumentVariantType
from backend.app.db.models.phase1 import (
    AuditEvent,
    BusinessEligibilityCertificate,
    Case,
    CapaCycle,
    Company,
    Document,
    DocumentGenerationRun,
    DocumentVariant,
    DocumentVersion,
    Site,
    TemplateDefinition,
)
from backend.app.document.contextual_actions import get_case_document_context_spec, list_case_document_context_specs
from backend.app.document.seed_runtime import seed_default_template_metadata
from backend.app.document.template_binary import assign_template_binary_locator
from backend.app.main import create_app
from backend.app.services.document_api import DocumentWorkflowService
from backend.app.storage.filesystem import FilesystemStorageService
from backend.app.storage.types import StorageConfig


def _build_minimal_docx_with_bookmarks(path: Path, bookmark_names: list[str]) -> None:
    bookmarks_xml = []
    for index, name in enumerate(bookmark_names, start=1):
        bookmarks_xml.append(
            f'<w:p><w:bookmarkStart w:id="{index}" w:name="{name}"/><w:r><w:t>VALUE</w:t></w:r><w:bookmarkEnd w:id="{index}"/></w:p>'
        )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(bookmarks_xml)
        + "</w:body></w:document>"
    )
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document_xml)


def _build_storage() -> tuple[FilesystemStorageService, Path]:
    root = Path(tempfile.mkdtemp(prefix="phase11-doc-"))
    inspection_root = root / "inspection"
    dkkd_root = root / "dkkd"
    template_root = root / "templates"
    inspection_root.mkdir(parents=True, exist_ok=True)
    dkkd_root.mkdir(parents=True, exist_ok=True)
    template_root.mkdir(parents=True, exist_ok=True)
    return (
        FilesystemStorageService(
            StorageConfig(
                inspection_root=inspection_root,
                dkkd_root=dkkd_root,
                template_root=template_root,
            )
        ),
        root,
    )


def _seed_case(session: Session) -> tuple[str, str]:
    company = Company(legacy_company_id=1, legal_name="Cong ty A", short_name="CTA")
    session.add(company)
    session.flush()
    site = Site(legacy_site_id=100, company_id=company.id, site_name="Co so A")
    session.add(site)
    session.flush()
    case = Case(
        legacy_inspection_id=200,
        legacy_inspection_code="KT-2024-GMP",
        site_id=site.id,
        gxp_type="GMP",
        state=CaseState.PLANNED,
        opened_year=2024,
    )
    session.add(case)
    session.commit()
    return case.id, site.id


def _seed_dkkd(session: Session, site_id: str, company_id: str) -> str:
    row = BusinessEligibilityCertificate(
        legacy_dkkd_id=300,
        site_id=site_id,
        company_id=company_id,
        latest_flag=True,
        latest_legacy_dkkd_id=300,
    )
    session.add(row)
    session.commit()
    return row.id


def _seed_capa_cycle(session: Session, case_id: str, *, round_no: int, status: str = "requested") -> str:
    row = CapaCycle(
        case_id=case_id,
        round_no=round_no,
        requested_on=None,
        submitted_on=None,
        assessed_on=None,
        assessor_name=None,
        result=None,
        status=status,
        notes=f"Round {round_no}",
    )
    session.add(row)
    session.commit()
    return row.id


def test_phase11_document_routes_are_registered():
    app = create_app("sqlite:///:memory:")
    routes = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/documents/prepare" in routes
    assert "/documents/render-template-docx" in routes
    assert "/document-generation-runs/{generation_run_id}" in routes
    assert "/documents/{document_id}" in routes


def test_prepare_generation_persists_pending_run_and_status():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = DocumentWorkflowService()

    with Session(engine) as session:
        case_id, _ = _seed_case(session)
        seed_default_template_metadata(session)
        result = service.prepare_generation(
            session,
            storage=None,
            payload={
                "family_code": "CERTIFICATE_DECISION",
                "case_id": case_id,
                "gxp_type": "GP",
                "storage_scope": "inspection_folder",
                "idempotency_key": "phase11-prepare-001",
                "payload": {
                    "TenCty": "Cong ty A",
                },
                "strict_payload": True,
            },
            user=build_authenticated_user("inspector01", "inspector"),
        )
        session.commit()

    assert result["generation_status"] == "pending"
    assert result["generation_run_id"] is not None
    assert result["template_readiness"]["readiness_status"] == "missing_template_locator"
    assert any(item.startswith("template:") for item in result["blocked_reasons"])

    with Session(engine) as session:
        run = session.get(DocumentGenerationRun, result["generation_run_id"])
        assert run is not None
        assert run.status.value == "pending"
        status = service.get_generation_run(session, result["generation_run_id"])
        assert status["document_id"] == result["document_id"]
        detail = service.get_document(session, result["document_id"])
        assert detail["document_id"] == result["document_id"]
        assert len(detail["generation_runs"]) == 1


def test_document_audit_payload_redacts_sensitive_keys():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = DocumentWorkflowService()

    with Session(engine) as session:
        actor = service._get_or_create_app_user(session, build_authenticated_user("inspector01", "inspector"))
        service._write_audit_event(
            session,
            actor=actor,
            entity_type="document_generation_run",
            entity_id="run-1",
            action="document_generation.prepare",
            payload={
                "family_code": "INSPECTION_CAPA_LAN_1",
                "payload": {"TenCty": "Cong ty A"},
                "access_token": "secret-token",
                "binary_blob": "abc",
            },
        )
        session.commit()

    with Session(engine) as session:
        audit_event = session.scalars(select(AuditEvent)).one()
        assert json.loads(audit_event.payload_redacted) == {
            "access_token": "<redacted>",
            "binary_blob": "<redacted>",
            "family_code": "INSPECTION_CAPA_LAN_1",
            "payload": {"TenCty": "Cong ty A"},
        }


def test_render_template_docx_blocks_payload_passthrough_family_and_marks_run_failed():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = DocumentWorkflowService()
    storage, root = _build_storage()
    try:
        with Session(engine) as session:
            case_id, _ = _seed_case(session)
            seed_default_template_metadata(session)
            template = session.execute(
                select(TemplateDefinition).where(TemplateDefinition.family_code == "CERTIFICATE_DECISION")
            ).scalar_one()
            template_relative = "inspection/certificate-decision.docx"
            template_path = root / "templates" / template_relative
            template_path.parent.mkdir(parents=True, exist_ok=True)
            _build_minimal_docx_with_bookmarks(template_path, ["TenCty"])
            assign_template_binary_locator(
                session,
                template_definition_id=template.id,
                storage_root="template",
                storage_relative_path=template_relative,
                original_filename="certificate-decision.docx",
            )
            try:
                service.render_template_docx(
                    session,
                    storage=storage,
                    payload={
                        "family_code": "CERTIFICATE_DECISION",
                        "case_id": case_id,
                        "gxp_type": "GP",
                        "storage_scope": "inspection_folder",
                        "idempotency_key": "phase11-render-block-001",
                        "output_filename": "2. Quyet dinh cap giay.docx",
                        "payload": {
                            "TenCty": "Cong ty A",
                        },
                        "strict_payload": True,
                    },
                    user=build_authenticated_user("inspector01", "inspector"),
                )
                session.commit()
            except Exception as exc:
                session.commit()
                assert "not render-safe" in str(exc)
            else:
                raise AssertionError("Expected unresolved payload_passthrough family to be blocked")

        with Session(engine) as session:
            run = session.scalars(
                select(DocumentGenerationRun).where(DocumentGenerationRun.idempotency_key == "phase11-render-block-001")
            ).one()
            assert run.status.value == "failed"
            assert run.error_summary is not None
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_render_template_docx_succeeds_for_dkkd_certificate_and_updates_lineage():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = DocumentWorkflowService()
    storage, root = _build_storage()
    try:
        with Session(engine) as session:
            case_id, site_id = _seed_case(session)
            company_id = session.get(Site, site_id).company_id  # type: ignore[union-attr]
            dkkd_id = _seed_dkkd(session, site_id, company_id)
            seed_default_template_metadata(session)

            inspection_folder = root / "dkkd" / "Cong ty A - Dia chi A (100)"
            inspection_folder.mkdir(parents=True, exist_ok=True)

            template = session.execute(
                select(TemplateDefinition).where(TemplateDefinition.family_code == "DDKD_CERTIFICATE")
            ).scalar_one()
            template_relative = "dkkd/z2 giay chung nhan ddkkdd sanitized.dotx"
            target_template = root / "templates" / template_relative
            target_template.parent.mkdir(parents=True, exist_ok=True)
            _build_minimal_docx_with_bookmarks(target_template, ["TenCty", "DiachiCoso", "HoatdongKD"])
            assign_template_binary_locator(
                session,
                template_definition_id=template.id,
                storage_root="template",
                storage_relative_path=template_relative,
                original_filename="z2 giay chung nhan ddkkdd sanitized.dotx",
            )
            result = service.render_template_docx(
                session,
                storage=storage,
                payload={
                    "family_code": "DDKD_CERTIFICATE",
                    "business_eligibility_certificate_id": dkkd_id,
                    "storage_scope": "dkkd_folder",
                    "idempotency_key": "phase11-render-success-001",
                    "output_filename": "z2. Giay chung nhan DDKKDD.docx",
                    "payload": {
                        "TenCty": "Cong ty A",
                        "DiachiCoso": "123 Duong A",
                        "HoatdongKD": "Bao quan, ban buon thuoc",
                    },
                    "strict_payload": True,
                },
                user=build_authenticated_user("inspector01", "inspector"),
            )
            session.commit()

        assert result["generation_status"] == "succeeded"
        assert result["scalar_replacement_mode"] == "contract_variant_exact"
        assert result["checksum_sha256"]

        with Session(engine) as session:
            run = session.scalars(
                select(DocumentGenerationRun).where(DocumentGenerationRun.idempotency_key == "phase11-render-success-001")
            ).one()
            assert run.status.value == "succeeded"
            version = session.get(DocumentVersion, result["document_version_id"])
            assert version is not None
            assert version.is_current is True
            detail = service.get_document(session, result["document_id"])
            assert len(detail["variants"]) == 1
            assert len(detail["generation_runs"]) == 1

        written = root / "dkkd" / "Cong ty A - Dia chi A (100)" / "z2. Giay chung nhan DDKKDD.docx"
        assert written.exists()
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_prepare_generation_links_capa_document_to_exact_cycle():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = DocumentWorkflowService()

    with Session(engine) as session:
        case_id, _ = _seed_case(session)
        capa_cycle_id = _seed_capa_cycle(session, case_id, round_no=1)
        seed_default_template_metadata(session)
        result = service.prepare_generation(
            session,
            storage=None,
            payload={
                "family_code": "INSPECTION_CAPA_LAN_1",
                "case_id": case_id,
                "capa_cycle_id": capa_cycle_id,
                "gxp_type": "GP",
                "storage_scope": "inspection_folder",
                "idempotency_key": "phase11-capa-prepare-001",
                "payload": {
                    "CAPAx": "Bang CAPA 1",
                },
                "strict_payload": True,
            },
            user=build_authenticated_user("inspector01", "inspector"),
        )
        session.commit()

    with Session(engine) as session:
        document = session.get(Document, result["document_id"])
        assert document is not None
        assert document.capa_cycle_id == capa_cycle_id
        detail = service.get_document(session, result["document_id"])
        assert detail["capa_cycle_id"] == capa_cycle_id


def test_prepare_generation_rejects_orphan_capa_document_without_cycle():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = DocumentWorkflowService()

    with Session(engine) as session:
        case_id, _ = _seed_case(session)
        seed_default_template_metadata(session)
        try:
            service.prepare_generation(
                session,
                storage=None,
                payload={
                    "family_code": "INSPECTION_CAPA_LAN_1",
                    "case_id": case_id,
                    "gxp_type": "GP",
                    "storage_scope": "inspection_folder",
                    "idempotency_key": "phase11-capa-prepare-002",
                    "payload": {
                        "CAPAx": "Bang CAPA 1",
                    },
                    "strict_payload": True,
                },
                user=build_authenticated_user("inspector01", "inspector"),
            )
        except Exception as exc:
            assert "requires capa_cycle_id" in str(exc)
        else:
            raise AssertionError("Expected CAPA document without cycle to fail closed")


def test_capa_round_documents_do_not_cross_link_between_rounds():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = DocumentWorkflowService()

    with Session(engine) as session:
        case_id, _ = _seed_case(session)
        round_1_cycle_id = _seed_capa_cycle(session, case_id, round_no=1, status="rejected")
        round_2_cycle_id = _seed_capa_cycle(session, case_id, round_no=2, status="requested")
        seed_default_template_metadata(session)
        first = service.prepare_generation(
            session,
            storage=None,
            payload={
                "family_code": "INSPECTION_CAPA_LAN_1",
                "case_id": case_id,
                "capa_cycle_id": round_1_cycle_id,
                "gxp_type": "GP",
                "storage_scope": "inspection_folder",
                "idempotency_key": "phase11-capa-round-1",
                "payload": {"CAPAx": "Bang CAPA 1"},
                "strict_payload": True,
            },
            user=build_authenticated_user("inspector01", "inspector"),
        )
        first_variant = session.scalars(
            select(DocumentVariant).where(DocumentVariant.document_id == first["document_id"])
        ).one()
        session.add(
            DocumentVersion(
                document_variant_id=first_variant.id,
                version_no=1,
                storage_binding_id=None,
                storage_root=None,
                storage_relative_path=None,
                original_filename=None,
                checksum_sha256=None,
                is_current=True,
                issued_on=None,
            )
        )
        session.flush()
        second = service.prepare_generation(
            session,
            storage=None,
            payload={
                "family_code": "INSPECTION_CAPA_LAN_2",
                "case_id": case_id,
                "capa_cycle_id": round_2_cycle_id,
                "gxp_type": "GP",
                "legacy_mode": "lan_2",
                "storage_scope": "inspection_folder",
                "idempotency_key": "phase11-capa-round-2",
                "payload": {"CAPAx": "Bang CAPA 2"},
                "strict_payload": True,
            },
            user=build_authenticated_user("inspector01", "inspector"),
        )
        session.commit()

    with Session(engine) as session:
        first_document = session.get(Document, first["document_id"])
        second_document = session.get(Document, second["document_id"])
        assert first_document is not None
        assert second_document is not None
        assert first_document.capa_cycle_id == round_1_cycle_id
        assert second_document.capa_cycle_id == round_2_cycle_id
        assert first_document.capa_cycle_id != second_document.capa_cycle_id


def test_case_document_context_registry_keeps_only_proven_step_assignments_active():
    specs = {spec.family_code: spec for spec in list_case_document_context_specs()}

    assert specs["INSPECTION_BBTD_HOSO_DK"].classification == "PROVEN"
    assert specs["INSPECTION_BBTD_HOSO_DK"].workflow_step == "Hồ sơ"
    assert specs["CERTIFICATE_ISSUANCE_WORD"].classification == "PROVEN"
    assert specs["CERTIFICATE_ISSUANCE_WORD"].workflow_step == "Chứng nhận GxP"
    assert specs["INSPECTION_CAPA_LAN_1"].parent_scope == "capa_cycle"
    assert specs["ASSESSMENT_MINUTES"].classification == "AMBIGUOUS"
    assert specs["ASSESSMENT_MINUTES"].workflow_step is None
    assert get_case_document_context_spec("UNKNOWN_FAMILY") is None


def test_get_document_detail_hides_storage_locator_fields_from_ui_projection():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = DocumentWorkflowService()
    document_id: str

    with Session(engine) as session:
        case_id, _ = _seed_case(session)
        document = Document(
            family_code="CERTIFICATE_DECISION",
            document_type_code="CERTIFICATE_DECISION",
            title="Quyết định cấp CC",
            case_id=case_id,
        )
        session.add(document)
        session.flush()
        document_id = document.id
        variant = DocumentVariant(
            document_id=document.id,
            variant_type=DocumentVariantType.EDITABLE_DOCX,
            language_code="vi",
            is_active=True,
        )
        session.add(variant)
        session.flush()
        session.add(
            DocumentVersion(
                document_variant_id=variant.id,
                version_no=1,
                storage_binding_id=None,
                storage_root="inspection",
                storage_relative_path="2026/file.docx",
                original_filename="file.docx",
                checksum_sha256="abc123",
                is_current=True,
                issued_on=None,
            )
        )
        session.commit()

    with Session(engine) as session:
        detail = service.get_document(session, document_id)

    version_payload = detail["variants"][0]["versions"][0]
    assert "storage_binding_id" not in version_payload
    assert "storage_root" not in version_payload
    assert "storage_relative_path" not in version_payload
    assert "checksum_sha256" not in version_payload
