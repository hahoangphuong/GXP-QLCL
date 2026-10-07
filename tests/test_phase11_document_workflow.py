from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import HTTPException, Request
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
import backend.app.api.routers.document as document_router_module
from backend.app.db.base import Base
from backend.app.db.enums import (
    CaseState,
    ChangeRequestState,
    DocumentGenerationStatus,
    DocumentVariantType,
)
from backend.app.db.models.phase1 import (
    AppUser,
    AuditEvent,
    BusinessEligibilityCertificate,
    Case,
    CapaCycle,
    ChangeRequest,
    Company,
    Document,
    DocumentGenerationRun,
    DocumentSourceDependency,
    DocumentVariant,
    DocumentVersion,
    Site,
    StorageBinding,
    TemplateDefinition,
)
from backend.app.document.contextual_actions import (
    build_document_action_states,
    get_case_document_context_spec,
    list_case_document_context_specs,
)
import backend.app.document.output_version as output_version_module
import backend.app.document.persistence as persistence_module
from backend.app.document.seed_runtime import seed_default_template_metadata
from backend.app.document.service import (
    DocumentPreparationInput,
    prepare_document_generation_job,
)
from backend.app.document.source_resolver_contract import (
    SourceDocumentCandidate,
    SourceDocumentLookupRequest,
    SourceDocumentResolution,
)
from backend.app.document.service_contract import (
    DocumentGenerationPlan,
    DocumentGenerationRequest,
    DocumentPayloadEnvelope,
    TemplateSelectionResult,
)
from backend.app.document.template_binary import assign_template_binary_locator
from backend.app.main import create_app
from backend.app.services.catalog import CatalogReadService
from backend.app.services.document_api import DocumentWorkflowService
from backend.app.storage.filesystem import FilesystemStorageService
from backend.app.storage.types import (
    StorageConfig,
    StorageOperationError,
    StorageTargetExistsError,
)


def _document_content_endpoint(app, path: str):
    route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == path
    )
    return route.endpoint


def _request_for_app(app) -> Request:
    return Request(
        {
            "type": "http",
            "app": app,
            "headers": [],
        }
    )


async def _read_streaming_response_body(response) -> bytes:
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
    return b"".join(chunks)


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
    assert "/cases/{case_id}/documents/{document_id}/content" in routes
    assert "/cases/{case_id}/capa-cycles/{capa_cycle_id}/documents/{document_id}/content" in routes
    assert "/documents/{document_id}/content" not in routes


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


def test_prepare_generation_reuses_idempotency_key_only_for_exact_request():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = DocumentWorkflowService()

    with Session(engine) as session:
        case_id, _ = _seed_case(session)
        seed_default_template_metadata(session)
        payload = {
            "family_code": "CERTIFICATE_DECISION",
            "case_id": case_id,
            "gxp_type": "GP",
            "storage_scope": "inspection_folder",
            "idempotency_key": "phase11-idempotent-exact-001",
            "payload": {"TenCty": "Cong ty A"},
            "strict_payload": True,
        }
        user = build_authenticated_user("inspector01", "inspector")
        first = service.prepare_generation(
            session,
            storage=None,
            payload=payload,
            user=user,
        )
        second = service.prepare_generation(
            session,
            storage=None,
            payload=payload,
            user=user,
        )
        session.commit()

    assert second["reused_generation_run"] is True
    assert second["generation_run_id"] == first["generation_run_id"]
    assert second["document_id"] == first["document_id"]


def test_prepare_generation_rejects_cross_owner_idempotency_reuse():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = DocumentWorkflowService()

    with Session(engine) as session:
        first_case_id, _ = _seed_case(session)
        company = Company(
            legacy_company_id=2,
            legal_name="Cong ty B",
            short_name="CTB",
        )
        session.add(company)
        session.flush()
        site = Site(
            legacy_site_id=101,
            company_id=company.id,
            site_name="Co so B",
        )
        session.add(site)
        session.flush()
        second_case = Case(
            legacy_inspection_id=201,
            legacy_inspection_code="KT-2024-GMP-B",
            site_id=site.id,
            gxp_type="GMP",
            state=CaseState.PLANNED,
            opened_year=2024,
        )
        session.add(second_case)
        session.flush()
        second_case_id = second_case.id
        seed_default_template_metadata(session)

        user = build_authenticated_user("inspector01", "inspector")
        common = {
            "family_code": "CERTIFICATE_DECISION",
            "gxp_type": "GP",
            "storage_scope": "inspection_folder",
            "idempotency_key": "phase11-idempotent-owner-001",
            "payload": {"TenCty": "Cong ty A"},
            "strict_payload": True,
        }
        first = service.prepare_generation(
            session,
            storage=None,
            payload={**common, "case_id": first_case_id},
            user=user,
        )

        try:
            service.prepare_generation(
                session,
                storage=None,
                payload={**common, "case_id": second_case_id},
                user=user,
            )
        except HTTPException as exc:
            assert exc.status_code == 409
            assert "idempotency key is already bound to a different request" in str(
                exc.detail
            )
            assert "document" in str(exc.detail)
        else:
            raise AssertionError("Expected cross-owner idempotency reuse to fail closed")

        session.commit()

    with Session(engine) as session:
        runs = list(
            session.scalars(
                select(DocumentGenerationRun).where(
                    DocumentGenerationRun.idempotency_key
                    == "phase11-idempotent-owner-001"
                )
            )
        )
        assert len(runs) == 1
        assert runs[0].id == first["generation_run_id"]
        second_documents = list(
            session.scalars(
                select(Document).where(Document.case_id == second_case_id)
            )
        )
        assert second_documents == []


def test_idempotent_generation_retry_requires_source_dependency_identity():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        case_id, _ = _seed_case(session)
        source_document = Document(
            family_code="SOURCE_FAMILY",
            document_type_code="SOURCE_FAMILY",
            title="Source",
            case_id=case_id,
        )
        target_document = Document(
            family_code="TARGET_FAMILY",
            document_type_code="TARGET_FAMILY",
            title="Target",
            case_id=case_id,
        )
        session.add_all([source_document, target_document])
        session.flush()

        source_variant = DocumentVariant(
            document_id=source_document.id,
            variant_type=DocumentVariantType.EDITABLE_DOCX,
            language_code="vi",
            is_active=True,
        )
        session.add(source_variant)
        session.flush()

        source_v1 = DocumentVersion(
            document_variant_id=source_variant.id,
            version_no=1,
            storage_binding_id=None,
            storage_root="inspection",
            storage_relative_path="source-v1.docx",
            original_filename="source-v1.docx",
            checksum_sha256="v1",
            is_current=False,
            issued_on=None,
        )
        source_v2 = DocumentVersion(
            document_variant_id=source_variant.id,
            version_no=2,
            storage_binding_id=None,
            storage_root="inspection",
            storage_relative_path="source-v2.docx",
            original_filename="source-v2.docx",
            checksum_sha256="v2",
            is_current=True,
            issued_on=None,
        )
        session.add_all([source_v1, source_v2])
        session.flush()

        run = DocumentGenerationRun(
            document_id=target_document.id,
            template_binding_id=None,
            template_definition_id=None,
            output_document_version_id=None,
            status=DocumentGenerationStatus.FAILED,
            source_application="Word",
            requested_by_user_id=None,
            input_payload_redacted="{}",
            error_summary="first attempt failed",
            idempotency_key="source-lineage-retry-001",
        )
        session.add(run)
        session.flush()
        session.add(
            DocumentSourceDependency(
                document_generation_run_id=run.id,
                source_document_id=source_document.id,
                source_document_version_id=source_v1.id,
                dependency_type="copy_forward",
                source_bookmarks=json.dumps(["A", "B"], ensure_ascii=False),
                notes=None,
            )
        )
        session.flush()

        request = SourceDocumentLookupRequest(
            family_code="SOURCE_FAMILY",
            required_bookmarks=("A", "B"),
            dependency_type="copy_forward",
            case_id=case_id,
        )
        exact_resolution = SourceDocumentResolution(
            request=request,
            candidate=SourceDocumentCandidate(
                document_id=source_document.id,
                family_code="SOURCE_FAMILY",
                document_version_id=source_v1.id,
                available_bookmarks=("A", "B"),
                is_current_version=False,
            ),
        )
        plan = DocumentGenerationPlan(
            request=DocumentGenerationRequest(
                family_code="TARGET_FAMILY",
                requested_by_user_id=None,
                case_id=case_id,
                storage_scope="inspection_folder",
                idempotency_key="source-lineage-retry-001",
            ),
            template=TemplateSelectionResult(
                family_code="TARGET_FAMILY",
                logical_name="Target",
                template_pattern="target.dotx",
                source_application="Word",
                storage_scope="inspection_folder",
                host_procedure="Target.Create",
                population_procedures=(),
                bookmarks=(),
                copy_forward_dependencies=(),
                notes=None,
            ),
            payload=DocumentPayloadEnvelope(
                family_code="TARGET_FAMILY",
                fields=(),
                source_procedures=(),
            ),
            source_dependencies=(),
        )
        persistence_module._preflight_idempotent_generation_run(
            session,
            plan,
            (exact_resolution,),
        )

        drifted_resolution = SourceDocumentResolution(
            request=request,
            candidate=SourceDocumentCandidate(
                document_id=source_document.id,
                family_code="SOURCE_FAMILY",
                document_version_id=source_v2.id,
                available_bookmarks=("A", "B"),
                is_current_version=True,
            ),
        )
        try:
            persistence_module._preflight_idempotent_generation_run(
                session,
                plan,
                (drifted_resolution,),
            )
        except persistence_module.DocumentPersistenceError as exc:
            assert "different source dependencies" in str(exc)
        else:
            raise AssertionError(
                "Expected idempotent retry with source-version drift to fail closed"
            )


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
            render_payload = {
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
            }
            prepared = service.prepare_generation(
                session,
                storage=storage,
                payload=render_payload,
                user=build_authenticated_user("inspector01", "inspector"),
            )
            prepared_run = session.get(
                DocumentGenerationRun,
                prepared["generation_run_id"],
            )
            assert prepared_run is not None
            assert prepared_run.status == DocumentGenerationStatus.PENDING
            session.commit()

            result = service.render_template_docx(
                session,
                storage=storage,
                payload=render_payload,
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


def test_render_failure_cleans_written_output_when_db_session_is_inactive(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = DocumentWorkflowService()
    storage, root = _build_storage()
    try:
        with Session(engine) as session:
            _, site_id = _seed_case(session)
            company_id = session.get(Site, site_id).company_id  # type: ignore[union-attr]
            dkkd_id = _seed_dkkd(session, site_id, company_id)
            seed_default_template_metadata(session)

            output_dir = root / "dkkd" / "Cong ty A - Dia chi A (100)"
            output_dir.mkdir(parents=True, exist_ok=True)
            template = session.execute(
                select(TemplateDefinition).where(
                    TemplateDefinition.family_code == "DDKD_CERTIFICATE"
                )
            ).scalar_one()
            template_relative = "dkkd/z2 giay chung nhan ddkkdd sanitized.dotx"
            template_path = root / "templates" / template_relative
            template_path.parent.mkdir(parents=True, exist_ok=True)
            _build_minimal_docx_with_bookmarks(
                template_path,
                ["TenCty", "DiachiCoso", "HoatdongKD"],
            )
            assign_template_binary_locator(
                session,
                template_definition_id=template.id,
                storage_root="template",
                storage_relative_path=template_relative,
                original_filename="z2 giay chung nhan ddkkdd sanitized.dotx",
            )
            render_payload = {
                "family_code": "DDKD_CERTIFICATE",
                "business_eligibility_certificate_id": dkkd_id,
                "storage_scope": "dkkd_folder",
                "idempotency_key": "phase11-render-inactive-session-cleanup-001",
                "output_filename": "candidate.docx",
                "payload": {
                    "TenCty": "Cong ty A",
                    "DiachiCoso": "123 Duong A",
                    "HoatdongKD": "Bao quan, ban buon thuoc",
                },
                "strict_payload": True,
            }
            prepared = service.prepare_generation(
                session,
                storage=storage,
                payload=render_payload,
                user=build_authenticated_user("inspector01", "inspector"),
            )
            session.commit()

            target = output_dir / "candidate.docx"
            assert target.exists() is False

            def fail_post_write_audit(
                audit_session,
                *,
                actor,
                entity_type,
                entity_id,
                action,
                payload,
            ):
                audit_session.add(
                    AppUser(
                        username=actor.username,
                        display_name="duplicate username",
                        is_active=True,
                    )
                )
                audit_session.flush()
                raise AssertionError("duplicate username flush should fail")

            monkeypatch.setattr(
                service,
                "_write_audit_event",
                fail_post_write_audit,
            )

            try:
                service.render_template_docx(
                    session,
                    storage=storage,
                    payload=render_payload,
                    user=build_authenticated_user("inspector01", "inspector"),
                )
            except IntegrityError:
                assert session.is_active is False
            else:
                raise AssertionError(
                    "Expected post-write DB flush failure to propagate"
                )

            assert target.exists() is False
            session.rollback()

        with Session(engine) as verify:
            run = verify.get(
                DocumentGenerationRun,
                prepared["generation_run_id"],
            )
            assert run is not None
            assert run.status == DocumentGenerationStatus.PENDING
            assert run.output_document_version_id is None
            versions = list(
                verify.scalars(
                    select(DocumentVersion).where(
                        DocumentVersion.document_variant_id
                        == prepared["document_variant_id"]
                    )
                )
            )
            assert versions == []
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_render_conflict_preserves_foreign_output_created_after_allocation(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = DocumentWorkflowService()
    storage, root = _build_storage()
    try:
        with Session(engine) as session:
            _, site_id = _seed_case(session)
            company_id = session.get(Site, site_id).company_id  # type: ignore[union-attr]
            dkkd_id = _seed_dkkd(session, site_id, company_id)
            seed_default_template_metadata(session)

            output_dir = root / "dkkd" / "Cong ty A - Dia chi A (100)"
            output_dir.mkdir(parents=True, exist_ok=True)
            template = session.execute(
                select(TemplateDefinition).where(
                    TemplateDefinition.family_code == "DDKD_CERTIFICATE"
                )
            ).scalar_one()
            template_relative = "dkkd/z2 giay chung nhan ddkkdd sanitized.dotx"
            template_path = root / "templates" / template_relative
            template_path.parent.mkdir(parents=True, exist_ok=True)
            _build_minimal_docx_with_bookmarks(
                template_path,
                ["TenCty", "DiachiCoso", "HoatdongKD"],
            )
            assign_template_binary_locator(
                session,
                template_definition_id=template.id,
                storage_root="template",
                storage_relative_path=template_relative,
                original_filename="z2 giay chung nhan ddkkdd sanitized.dotx",
            )

            render_payload = {
                "family_code": "DDKD_CERTIFICATE",
                "business_eligibility_certificate_id": dkkd_id,
                "storage_scope": "dkkd_folder",
                "idempotency_key": "phase11-render-exclusive-conflict-001",
                "output_filename": "exclusive-conflict.docx",
                "payload": {
                    "TenCty": "Cong ty A",
                    "DiachiCoso": "123 Duong A",
                    "HoatdongKD": "Bao quan, ban buon thuoc",
                },
                "strict_payload": True,
            }
            original_write_stream = storage.write_stream
            foreign_path = output_dir / "exclusive-conflict.docx"

            def conflict_on_exclusive_write(
                relative_path,
                stream,
                *,
                root="inspection",
                overwrite=True,
            ):
                if overwrite is False:
                    foreign_path.write_bytes(b"foreign-output")
                    raise StorageTargetExistsError(
                        "Storage target already exists and will not be overwritten."
                    )
                return original_write_stream(
                    relative_path,
                    stream,
                    root=root,
                    overwrite=overwrite,
                )

            monkeypatch.setattr(
                storage,
                "write_stream",
                conflict_on_exclusive_write,
            )

            try:
                service.render_template_docx(
                    session,
                    storage=storage,
                    payload=render_payload,
                    user=build_authenticated_user("inspector01", "inspector"),
                )
            except HTTPException as exc:
                assert exc.status_code == 409
                assert "will not be overwritten" in exc.detail
            else:
                raise AssertionError(
                    "Expected render to fail closed when output appears after allocation"
                )
            session.commit()

            assert foreign_path.read_bytes() == b"foreign-output"
            run = session.scalars(
                select(DocumentGenerationRun).where(
                    DocumentGenerationRun.idempotency_key
                    == "phase11-render-exclusive-conflict-001"
                )
            ).one()
            assert run.status == DocumentGenerationStatus.FAILED
            version = session.get(DocumentVersion, run.output_document_version_id)
            assert version is not None
            assert version.is_current is False
            assert version.checksum_sha256 is None
            assert version.issued_on is None
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_reused_generation_run_state_machine_allows_prepared_pending_and_failed_retry():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = DocumentWorkflowService()

    with Session(engine) as session:
        case_id, _ = _seed_case(session)
        document = Document(
            family_code="STATE_MACHINE_TEST",
            document_type_code="state_machine_test",
            title="State machine test",
            case_id=case_id,
        )
        session.add(document)
        session.flush()
        run = DocumentGenerationRun(
            document_id=document.id,
            template_binding_id=None,
            template_definition_id=None,
            output_document_version_id=None,
            status=DocumentGenerationStatus.FAILED,
            source_application="Word",
            requested_by_user_id=None,
            input_payload_redacted="{}",
            error_summary="first attempt failed",
            idempotency_key="state-machine-retry-001",
        )
        session.add(run)
        session.flush()
        prepared = SimpleNamespace(
            persisted_state=SimpleNamespace(
                reused_generation_run=True,
                generation_run_id=run.id,
            )
        )

        service._claim_reused_generation_run_for_render(session, prepared)
        session.refresh(run)
        assert run.status == DocumentGenerationStatus.PENDING
        assert run.error_summary is None

        service._claim_reused_generation_run_for_render(session, prepared)
        session.refresh(run)
        assert run.status == DocumentGenerationStatus.PENDING
        assert run.error_summary is None

        run.status = DocumentGenerationStatus.CANCELLED
        run.error_summary = "cancelled by operator"
        session.flush()
        try:
            service._claim_reused_generation_run_for_render(session, prepared)
        except HTTPException as exc:
            assert exc.status_code == 409
            assert exc.detail == "Cancelled document generation run cannot be retried."
        else:
            raise AssertionError("Expected cancelled generation run to fail closed")
        session.refresh(run)
        assert run.status == DocumentGenerationStatus.CANCELLED
        assert run.error_summary == "cancelled by operator"


def test_render_template_docx_restores_previous_current_when_post_write_audit_fails(
    monkeypatch,
):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = DocumentWorkflowService()
    storage, root = _build_storage()
    try:
        with Session(engine) as session:
            _, site_id = _seed_case(session)
            company_id = session.get(Site, site_id).company_id  # type: ignore[union-attr]
            dkkd_id = _seed_dkkd(session, site_id, company_id)
            seed_default_template_metadata(session)

            output_dir = root / "dkkd" / "Cong ty A - Dia chi A (100)"
            output_dir.mkdir(parents=True, exist_ok=True)

            template = session.execute(
                select(TemplateDefinition).where(
                    TemplateDefinition.family_code == "DDKD_CERTIFICATE"
                )
            ).scalar_one()
            template_relative = "dkkd/z2 giay chung nhan ddkkdd sanitized.dotx"
            template_path = root / "templates" / template_relative
            template_path.parent.mkdir(parents=True, exist_ok=True)
            _build_minimal_docx_with_bookmarks(
                template_path,
                ["TenCty", "DiachiCoso", "HoatdongKD"],
            )
            assign_template_binary_locator(
                session,
                template_definition_id=template.id,
                storage_root="template",
                storage_relative_path=template_relative,
                original_filename="z2 giay chung nhan ddkkdd sanitized.dotx",
            )

            common_payload = {
                "family_code": "DDKD_CERTIFICATE",
                "business_eligibility_certificate_id": dkkd_id,
                "storage_scope": "dkkd_folder",
                "payload": {
                    "TenCty": "Cong ty A",
                    "DiachiCoso": "123 Duong A",
                    "HoatdongKD": "Bao quan, ban buon thuoc",
                },
                "strict_payload": True,
            }
            baseline_payload = {
                **common_payload,
                "idempotency_key": "phase11-render-baseline-001",
                "output_filename": "baseline.docx",
            }
            baseline = service.render_template_docx(
                session,
                storage=storage,
                payload=baseline_payload,
                user=build_authenticated_user("inspector01", "inspector"),
            )
            session.commit()

            baseline_path = output_dir / "baseline.docx"
            baseline_bytes = baseline_path.read_bytes()
            try:
                service.render_template_docx(
                    session,
                    storage=storage,
                    payload=baseline_payload,
                    user=build_authenticated_user("inspector01", "inspector"),
                )
            except HTTPException as exc:
                assert exc.status_code == 409
                assert exc.detail == (
                    "Document generation run already succeeded; open the current "
                    "document instead of rendering it again."
                )
            else:
                raise AssertionError(
                    "Expected successful idempotent replay to avoid re-rendering"
                )
            assert baseline_path.read_bytes() == baseline_bytes
            baseline_run = session.get(
                DocumentGenerationRun,
                baseline["generation_run_id"],
            )
            assert baseline_run is not None
            assert baseline_run.status.value == "succeeded"

            original_write_audit_event = service._write_audit_event
            monkeypatch.setattr(
                service,
                "_write_audit_event",
                lambda *args, **kwargs: (_ for _ in ()).throw(
                    RuntimeError("simulated post-write audit failure")
                ),
            )
            candidate_payload = {
                **common_payload,
                "idempotency_key": "phase11-render-cleanup-001",
                "output_filename": "candidate.docx",
            }

            try:
                service.render_template_docx(
                    session,
                    storage=storage,
                    payload=candidate_payload,
                    user=build_authenticated_user("inspector01", "inspector"),
                )
            except RuntimeError as exc:
                assert "simulated post-write audit failure" in str(exc)
            else:
                raise AssertionError("Expected post-write audit failure")

            session.commit()

            baseline_version = session.get(
                DocumentVersion,
                baseline["document_version_id"],
            )
            assert baseline_version is not None
            assert baseline_version.is_current is True
            failed_run = session.scalars(
                select(DocumentGenerationRun).where(
                    DocumentGenerationRun.idempotency_key
                    == "phase11-render-cleanup-001"
                )
            ).one()
            assert failed_run.status.value == "failed"
            failed_version = session.get(
                DocumentVersion,
                failed_run.output_document_version_id,
            )
            assert failed_version is not None
            assert failed_version.is_current is False
            assert failed_version.checksum_sha256 is None
            assert failed_version.issued_on is None

            candidate_path = output_dir / "candidate.docx"
            assert candidate_path.exists() is False
            original_output_identity = (
                failed_version.storage_root,
                failed_version.storage_binding_id,
                failed_version.storage_relative_path,
                failed_version.original_filename,
            )
            assert failed_version.storage_relative_path == candidate_path.relative_to(
                root / "dkkd"
            ).as_posix()

            monkeypatch.setattr(
                service,
                "_write_audit_event",
                original_write_audit_event,
            )
            original_resolve_reused_output_identity = (
                output_version_module._resolve_reused_output_identity
            )
            monkeypatch.setattr(
                output_version_module,
                "_resolve_reused_output_identity",
                lambda session, storage, prepared: (
                    "dkkd",
                    "drifted-folder",
                    None,
                ),
            )
            try:
                service.render_template_docx(
                    session,
                    storage=storage,
                    payload=candidate_payload,
                    user=build_authenticated_user("inspector01", "inspector"),
                )
            except HTTPException as exc:
                assert exc.status_code == 409
                assert "different output identity" in exc.detail
                assert "storage_relative_path=" in exc.detail
            else:
                raise AssertionError(
                    "Expected idempotent retry with storage-binding drift to fail closed"
                )
            session.refresh(failed_run)
            session.refresh(failed_version)
            assert failed_run.status == DocumentGenerationStatus.FAILED
            assert (
                failed_version.storage_root,
                failed_version.storage_binding_id,
                failed_version.storage_relative_path,
                failed_version.original_filename,
            ) == original_output_identity
            assert candidate_path.exists() is False
            drifted_path = root / "dkkd" / "drifted-folder" / "candidate.docx"
            assert drifted_path.exists() is False

            monkeypatch.setattr(
                output_version_module,
                "_resolve_reused_output_identity",
                original_resolve_reused_output_identity,
            )

            mismatched_payload = {
                **candidate_payload,
                "output_filename": "different-candidate.docx",
            }
            try:
                service.render_template_docx(
                    session,
                    storage=storage,
                    payload=mismatched_payload,
                    user=build_authenticated_user("inspector01", "inspector"),
                )
            except HTTPException as exc:
                assert exc.status_code == 409
                assert "different output identity" in exc.detail
                assert "filename='candidate.docx'->'different-candidate.docx'" in exc.detail
                assert "storage_relative_path=" in exc.detail
            else:
                raise AssertionError(
                    "Expected idempotent retry with a different output filename "
                    "to fail closed"
                )
            session.refresh(failed_run)
            session.refresh(failed_version)
            assert failed_run.status == DocumentGenerationStatus.FAILED
            assert (
                failed_version.storage_root,
                failed_version.storage_binding_id,
                failed_version.storage_relative_path,
                failed_version.original_filename,
            ) == original_output_identity
            assert candidate_path.exists() is False
            assert drifted_path.exists() is False

            retry = service.render_template_docx(
                session,
                storage=storage,
                payload=candidate_payload,
                user=build_authenticated_user("inspector01", "inspector"),
            )
            session.commit()

            session.refresh(failed_run)
            session.refresh(failed_version)
            session.refresh(baseline_version)
            assert retry["generation_run_id"] == failed_run.id
            assert retry["document_version_id"] == failed_version.id
            assert failed_run.status == DocumentGenerationStatus.SUCCEEDED
            assert failed_run.error_summary is None
            assert failed_version.is_current is True
            assert failed_version.checksum_sha256
            assert failed_version.issued_on is not None
            assert baseline_version.is_current is False
            assert (
                failed_version.storage_root,
                failed_version.storage_binding_id,
                failed_version.storage_relative_path,
                failed_version.original_filename,
            ) == original_output_identity
            assert drifted_path.exists() is False

        assert baseline_path.exists() is True
        assert candidate_path.exists() is True
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_reused_inspection_output_allocation_detects_folder_drift_without_mutating_binding():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    storage, root = _build_storage()
    try:
        with Session(engine) as session:
            case_id, _ = _seed_case(session)
            seed_default_template_metadata(session)

            original_folder = (
                root
                / "inspection"
                / "2024"
                / "Original Folder - (ID-100) - (KT-2024-GMP)"
            )
            original_folder.mkdir(parents=True, exist_ok=True)

            preparation_input = DocumentPreparationInput(
                request=DocumentGenerationRequest(
                    family_code="CERTIFICATE_DECISION",
                    requested_by_user_id=None,
                    case_id=case_id,
                    gxp_type="GP",
                    storage_scope="inspection_folder",
                    idempotency_key="phase11-output-inspection-drift-001",
                ),
                payload_values={"TenCty": "Cong ty A"},
            )
            prepared = prepare_document_generation_job(
                session,
                preparation_input,
            )
            original_allocation = output_version_module.allocate_output_document_version(
                session,
                storage,
                prepared,
                output_filename="candidate.docx",
            )
            session.commit()

            assert original_allocation.storage_binding_id is not None
            binding = session.get(
                StorageBinding,
                original_allocation.storage_binding_id,
            )
            version = session.get(
                DocumentVersion,
                original_allocation.document_version_id,
            )
            assert binding is not None
            assert version is not None
            original_relative_folder = (
                "2024/Original Folder - (ID-100) - (KT-2024-GMP)"
            )
            assert binding.relative_path == original_relative_folder
            assert version.storage_relative_path == (
                original_relative_folder + "/candidate.docx"
            )

            drifted_folder = (
                root
                / "inspection"
                / "2024"
                / "Drifted Folder - (ID-100) - (KT-2024-GMP)"
            )
            original_folder.rename(drifted_folder)

            try:
                output_version_module.allocate_output_document_version(
                    session,
                    storage,
                    prepared,
                    output_filename="candidate.docx",
                )
            except output_version_module.OutputVersionAllocationError as exc:
                assert "different output identity" in str(exc)
                assert "storage_relative_path=" in str(exc)
            else:
                raise AssertionError(
                    "Expected inspection-folder drift to fail closed"
                )

            session.refresh(binding)
            session.refresh(version)
            assert binding.relative_path == original_relative_folder
            assert binding.observed_folder_label == (
                "Original Folder - (ID-100) - (KT-2024-GMP)"
            )
            assert version.storage_binding_id == binding.id
            assert version.storage_relative_path == (
                original_relative_folder + "/candidate.docx"
            )
            assert (
                original_folder / "candidate.docx"
            ).exists() is False
            assert (
                drifted_folder / "candidate.docx"
            ).exists() is False
            assert session.query(DocumentVersion).count() == 1

            drifted_folder.rename(original_folder)
            retry = output_version_module.allocate_output_document_version(
                session,
                storage,
                prepared,
                output_filename="candidate.docx",
            )
            assert retry == original_allocation
            session.refresh(binding)
            assert binding.relative_path == original_relative_folder
            assert session.query(DocumentVersion).count() == 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_output_allocation_rejects_non_pending_generation_run_before_mutation():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    storage, root = _build_storage()
    try:
        with Session(engine) as session:
            _, site_id = _seed_case(session)
            company_id = session.get(Site, site_id).company_id  # type: ignore[union-attr]
            dkkd_id = _seed_dkkd(session, site_id, company_id)
            seed_default_template_metadata(session)

            output_dir = root / "dkkd" / "Cong ty A - Dia chi A (100)"
            output_dir.mkdir(parents=True, exist_ok=True)

            preparation_input = DocumentPreparationInput(
                request=DocumentGenerationRequest(
                    family_code="DDKD_CERTIFICATE",
                    requested_by_user_id=None,
                    business_eligibility_certificate_id=dkkd_id,
                    storage_scope="dkkd_folder",
                    idempotency_key="phase11-allocation-status-001",
                ),
                payload_values={
                    "TenCty": "Cong ty A",
                    "DiachiCoso": "123 Duong A",
                    "HoatdongKD": "Bao quan, ban buon thuoc",
                },
            )
            prepared = prepare_document_generation_job(
                session,
                preparation_input,
            )
            run = session.get(
                DocumentGenerationRun,
                prepared.persisted_state.generation_run_id,
            )
            assert run is not None
            target = output_dir / "candidate.docx"

            for blocked_status in (
                DocumentGenerationStatus.FAILED,
                DocumentGenerationStatus.CANCELLED,
                DocumentGenerationStatus.SUCCEEDED,
            ):
                marker = f"{blocked_status.value} before allocation"
                run.status = blocked_status
                run.error_summary = marker
                session.flush()

                try:
                    output_version_module.allocate_output_document_version(
                        session,
                        storage,
                        prepared,
                        output_filename="candidate.docx",
                    )
                except output_version_module.OutputVersionAllocationError as exc:
                    assert "cannot allocate output from status" in str(exc)
                    assert repr(blocked_status.value) in str(exc)
                    assert "expected 'pending'" in str(exc)
                else:
                    raise AssertionError(
                        f"Expected {blocked_status.value} generation run to fail before output allocation"
                    )

                session.refresh(run)
                assert run.status == blocked_status
                assert run.error_summary == marker
                assert run.output_document_version_id is None
                assert session.query(DocumentVersion).count() == 0
                assert target.exists() is False

            run.status = DocumentGenerationStatus.PENDING
            run.error_summary = None
            session.flush()
            allocation = output_version_module.allocate_output_document_version(
                session,
                storage,
                prepared,
                output_filename="candidate.docx",
            )
            version = session.get(
                DocumentVersion,
                allocation.document_version_id,
            )
            assert version is not None
            original_identity = (
                version.document_variant_id,
                version.version_no,
                version.storage_binding_id,
                version.storage_root,
                version.storage_relative_path,
                version.original_filename,
            )

            for blocked_status in (
                DocumentGenerationStatus.FAILED,
                DocumentGenerationStatus.CANCELLED,
                DocumentGenerationStatus.SUCCEEDED,
            ):
                marker = f"{blocked_status.value} after allocation"
                run.status = blocked_status
                run.error_summary = marker
                session.flush()

                try:
                    output_version_module.allocate_output_document_version(
                        session,
                        storage,
                        prepared,
                        output_filename="candidate.docx",
                    )
                except output_version_module.OutputVersionAllocationError as exc:
                    assert "cannot allocate output from status" in str(exc)
                    assert repr(blocked_status.value) in str(exc)
                else:
                    raise AssertionError(
                        f"Expected {blocked_status.value} generation run to reject allocation reuse"
                    )

                session.refresh(run)
                session.refresh(version)
                assert run.status == blocked_status
                assert run.error_summary == marker
                assert run.output_document_version_id == allocation.document_version_id
                assert (
                    version.document_variant_id,
                    version.version_no,
                    version.storage_binding_id,
                    version.storage_root,
                    version.storage_relative_path,
                    version.original_filename,
                ) == original_identity
                assert session.query(DocumentVersion).count() == 1
                assert target.exists() is False
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_reused_output_allocation_rejects_version_superseded_by_newer_allocation():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    storage, root = _build_storage()
    try:
        with Session(engine) as session:
            _, site_id = _seed_case(session)
            company_id = session.get(Site, site_id).company_id  # type: ignore[union-attr]
            dkkd_id = _seed_dkkd(session, site_id, company_id)
            seed_default_template_metadata(session)

            output_dir = root / "dkkd" / "Cong ty A - Dia chi A (100)"
            output_dir.mkdir(parents=True, exist_ok=True)

            def build_prepared(idempotency_key: str):
                return prepare_document_generation_job(
                    session,
                    DocumentPreparationInput(
                        request=DocumentGenerationRequest(
                            family_code="DDKD_CERTIFICATE",
                            requested_by_user_id=None,
                            business_eligibility_certificate_id=dkkd_id,
                            storage_scope="dkkd_folder",
                            idempotency_key=idempotency_key,
                        ),
                        payload_values={
                            "TenCty": "Cong ty A",
                            "DiachiCoso": "123 Duong A",
                            "HoatdongKD": "Bao quan, ban buon thuoc",
                        },
                    ),
                )

            older_prepared = build_prepared("phase11-stale-reuse-older")
            older_allocation = output_version_module.allocate_output_document_version(
                session,
                storage,
                older_prepared,
                output_filename="older-candidate.docx",
            )
            newer_prepared = build_prepared("phase11-stale-reuse-newer")
            newer_allocation = output_version_module.allocate_output_document_version(
                session,
                storage,
                newer_prepared,
                output_filename="newer-candidate.docx",
            )

            assert (
                older_allocation.document_variant_id
                == newer_allocation.document_variant_id
            )
            assert older_allocation.version_no == 1
            assert newer_allocation.version_no == 2

            older_run = session.get(
                DocumentGenerationRun,
                older_allocation.generation_run_id,
            )
            newer_run = session.get(
                DocumentGenerationRun,
                newer_allocation.generation_run_id,
            )
            assert older_run is not None
            assert newer_run is not None
            assert older_run.status == DocumentGenerationStatus.PENDING
            assert newer_run.status == DocumentGenerationStatus.PENDING

            try:
                output_version_module.allocate_output_document_version(
                    session,
                    storage,
                    older_prepared,
                    output_filename="older-candidate.docx",
                )
            except output_version_module.OutputVersionAllocationError as exc:
                assert "no longer the latest persisted version" in str(exc)
                assert "allocated version_no=1" in str(exc)
                assert "latest version_no=2" in str(exc)
            else:
                raise AssertionError(
                    "Expected superseded output allocation reuse to fail closed"
                )

            session.refresh(older_run)
            session.refresh(newer_run)
            assert (
                older_run.output_document_version_id
                == older_allocation.document_version_id
            )
            assert (
                newer_run.output_document_version_id
                == newer_allocation.document_version_id
            )
            versions = list(
                session.scalars(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.document_variant_id
                        == older_allocation.document_variant_id
                    )
                    .order_by(DocumentVersion.version_no.asc())
                )
            )
            assert [row.version_no for row in versions] == [1, 2]
            assert all(row.is_current is False for row in versions)
            assert (output_dir / "older-candidate.docx").exists() is False
            assert (output_dir / "newer-candidate.docx").exists() is False
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_output_allocation_rejects_stale_prepared_lineage_before_mutation():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    storage, root = _build_storage()
    try:
        with Session(engine) as session:
            _, site_id = _seed_case(session)
            company_id = session.get(Site, site_id).company_id  # type: ignore[union-attr]
            dkkd_id = _seed_dkkd(session, site_id, company_id)
            seed_default_template_metadata(session)

            output_dir = root / "dkkd" / "Cong ty A - Dia chi A (100)"
            output_dir.mkdir(parents=True, exist_ok=True)

            prepared = prepare_document_generation_job(
                session,
                DocumentPreparationInput(
                    request=DocumentGenerationRequest(
                        family_code="DDKD_CERTIFICATE",
                        requested_by_user_id=None,
                        business_eligibility_certificate_id=dkkd_id,
                        storage_scope="dkkd_folder",
                        idempotency_key="phase11-output-lineage-001",
                    ),
                    payload_values={
                        "TenCty": "Cong ty A",
                        "DiachiCoso": "123 Duong A",
                        "HoatdongKD": "Bao quan, ban buon thuoc",
                    },
                ),
            )
            run = session.get(
                DocumentGenerationRun,
                prepared.persisted_state.generation_run_id,
            )
            assert run is not None
            canonical_document_id = prepared.persisted_state.document_id
            canonical_variant_id = prepared.persisted_state.document_variant_id

            foreign_document = Document(
                family_code="FOREIGN_OUTPUT_LINEAGE",
                document_type_code="foreign_output_lineage",
                title="Foreign output lineage",
                business_eligibility_certificate_id=dkkd_id,
            )
            session.add(foreign_document)
            session.flush()
            foreign_variant = DocumentVariant(
                document_id=foreign_document.id,
                variant_type=DocumentVariantType.EDITABLE_DOCX,
                language_code="vi",
                is_active=True,
            )
            session.add(foreign_variant)
            session.flush()

            cross_document_prepared = replace(
                prepared,
                persisted_state=replace(
                    prepared.persisted_state,
                    document_id=foreign_document.id,
                    document_variant_id=foreign_variant.id,
                ),
            )
            try:
                output_version_module.allocate_output_document_version(
                    session,
                    storage,
                    cross_document_prepared,
                    output_filename="candidate.docx",
                )
            except output_version_module.OutputVersionAllocationError as exc:
                assert "allocation lineage identity mismatch" in str(exc)
                assert "generation_run.document_id" in str(exc)
            else:
                raise AssertionError(
                    "Expected cross-document prepared lineage to fail closed"
                )

            variant_owner_mismatch_prepared = replace(
                prepared,
                persisted_state=replace(
                    prepared.persisted_state,
                    document_variant_id=foreign_variant.id,
                ),
            )
            try:
                output_version_module.allocate_output_document_version(
                    session,
                    storage,
                    variant_owner_mismatch_prepared,
                    output_filename="candidate.docx",
                )
            except output_version_module.OutputVersionAllocationError as exc:
                assert "allocation lineage identity mismatch" in str(exc)
                assert "document_variant.document_id" in str(exc)
            else:
                raise AssertionError(
                    "Expected foreign variant ownership to fail closed"
                )

            session.refresh(run)
            assert run.document_id == canonical_document_id
            assert run.output_document_version_id is None
            assert (
                session.query(DocumentVersion)
                .filter(DocumentVersion.document_variant_id == canonical_variant_id)
                .count()
                == 0
            )
            assert (
                session.query(DocumentVersion)
                .filter(DocumentVersion.document_variant_id == foreign_variant.id)
                .count()
                == 0
            )

            allocation = output_version_module.allocate_output_document_version(
                session,
                storage,
                prepared,
                output_filename="candidate.docx",
            )
            assert allocation.document_id == canonical_document_id
            assert allocation.document_variant_id == canonical_variant_id
            assert session.query(DocumentVersion).count() == 1

            reused_variant_mismatch_prepared = replace(
                prepared,
                persisted_state=replace(
                    prepared.persisted_state,
                    document_variant_id=foreign_variant.id,
                ),
            )
            try:
                output_version_module.allocate_output_document_version(
                    session,
                    storage,
                    reused_variant_mismatch_prepared,
                    output_filename="candidate.docx",
                )
            except output_version_module.OutputVersionAllocationError as exc:
                assert "allocation lineage identity mismatch" in str(exc)
                assert "document_variant.id" in str(exc)
            else:
                raise AssertionError(
                    "Expected reused allocation with stale variant identity to fail closed"
                )

            session.refresh(run)
            assert run.output_document_version_id == allocation.document_version_id
            assert session.query(DocumentVersion).count() == 1
            version = session.get(DocumentVersion, allocation.document_version_id)
            assert version is not None
            assert version.document_variant_id == canonical_variant_id
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_finalize_output_write_rejects_stale_allocation_identity_before_storage_io(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    storage, root = _build_storage()
    try:
        with Session(engine) as session:
            _, site_id = _seed_case(session)
            company_id = session.get(Site, site_id).company_id  # type: ignore[union-attr]
            dkkd_id = _seed_dkkd(session, site_id, company_id)
            seed_default_template_metadata(session)

            output_dir = root / "dkkd" / "Cong ty A - Dia chi A (100)"
            output_dir.mkdir(parents=True, exist_ok=True)

            preparation_input = DocumentPreparationInput(
                request=DocumentGenerationRequest(
                    family_code="DDKD_CERTIFICATE",
                    requested_by_user_id=None,
                    business_eligibility_certificate_id=dkkd_id,
                    storage_scope="dkkd_folder",
                    idempotency_key="phase11-finalize-identity-001",
                ),
                payload_values={
                    "TenCty": "Cong ty A",
                    "DiachiCoso": "123 Duong A",
                    "HoatdongKD": "Bao quan, ban buon thuoc",
                },
            )
            prepared = prepare_document_generation_job(
                session,
                preparation_input,
            )
            allocation = output_version_module.allocate_output_document_version(
                session,
                storage,
                prepared,
                output_filename="candidate.docx",
            )
            session.commit()

            run = session.get(
                DocumentGenerationRun,
                allocation.generation_run_id,
            )
            version = session.get(
                DocumentVersion,
                allocation.document_version_id,
            )
            assert run is not None
            assert version is not None
            assert run.status == DocumentGenerationStatus.PENDING

            corrupt_current_a = DocumentVersion(
                document_variant_id=allocation.document_variant_id,
                version_no=allocation.version_no + 1,
                storage_binding_id=None,
                storage_root="dkkd",
                storage_relative_path="corrupt/current-a.docx",
                original_filename="current-a.docx",
                checksum_sha256="corrupt-a",
                is_current=True,
                issued_on=None,
            )
            corrupt_current_b = DocumentVersion(
                document_variant_id=allocation.document_variant_id,
                version_no=allocation.version_no + 2,
                storage_binding_id=None,
                storage_root="dkkd",
                storage_relative_path="corrupt/current-b.docx",
                original_filename="current-b.docx",
                checksum_sha256="corrupt-b",
                is_current=True,
                issued_on=None,
            )
            session.add_all([corrupt_current_a, corrupt_current_b])
            session.flush()

            original_target = (
                root / "dkkd" / allocation.storage_relative_path
            )
            assert original_target.exists() is False

            try:
                output_version_module.finalize_output_document_version_write(
                    session,
                    storage,
                    allocation,
                    binary_payload=b"must-not-repair-corrupt-current-lineage",
                )
            except output_version_module.OutputVersionAllocationError as exc:
                assert "multiple current versions before output finalization" in str(exc)
            else:
                raise AssertionError(
                    "Expected duplicate current lineage to fail before output write"
                )

            assert original_target.exists() is False
            session.refresh(run)
            session.refresh(version)
            assert run.status == DocumentGenerationStatus.PENDING
            assert version.is_current is False
            assert corrupt_current_a.is_current is True
            assert corrupt_current_b.is_current is True

            corrupt_current_a.is_current = False
            corrupt_current_b.is_current = False
            session.flush()

            try:
                output_version_module.finalize_output_document_version_write(
                    session,
                    storage,
                    allocation,
                    binary_payload=b"must-not-finalize-stale-version",
                )
            except output_version_module.OutputVersionAllocationError as exc:
                assert "not the latest persisted version" in str(exc)
                assert f"allocated version_no={allocation.version_no!r}" in str(exc)
            else:
                raise AssertionError(
                    "Expected an older allocated version to fail before output write"
                )

            assert original_target.exists() is False
            session.refresh(run)
            session.refresh(version)
            assert run.status == DocumentGenerationStatus.PENDING
            assert version.is_current is False

            session.delete(corrupt_current_a)
            session.delete(corrupt_current_b)
            session.flush()

            for blocked_status in (
                DocumentGenerationStatus.FAILED,
                DocumentGenerationStatus.CANCELLED,
                DocumentGenerationStatus.SUCCEEDED,
            ):
                marker = f"{blocked_status.value} marker"
                run.status = blocked_status
                run.error_summary = marker
                session.flush()

                try:
                    output_version_module.finalize_output_document_version_write(
                        session,
                        storage,
                        allocation,
                        binary_payload=b"must-not-be-written",
                    )
                except output_version_module.OutputVersionAllocationError as exc:
                    assert "cannot be finalized from status" in str(exc)
                    assert repr(blocked_status.value) in str(exc)
                    assert "expected 'pending'" in str(exc)
                else:
                    raise AssertionError(
                        f"Expected {blocked_status.value} generation run to fail before output write"
                    )

                assert original_target.exists() is False
                session.refresh(run)
                session.refresh(version)
                assert run.status == blocked_status
                assert run.error_summary == marker
                assert version.checksum_sha256 is None
                assert version.is_current is False
                assert version.issued_on is None

            run.status = DocumentGenerationStatus.PENDING
            run.error_summary = None
            session.flush()

            version.storage_relative_path = (
                "Cong ty A - Dia chi A (100)/drifted-candidate.docx"
            )
            session.flush()
            try:
                output_version_module.finalize_output_document_version_write(
                    session,
                    storage,
                    allocation,
                    binary_payload=b"must-not-be-written",
                )
            except output_version_module.OutputVersionAllocationError as exc:
                assert "finalization allocation identity mismatch" in str(exc)
                assert "document_version.storage_relative_path=" in str(exc)
            else:
                raise AssertionError(
                    "Expected DB locator drift to fail before output write"
                )

            assert original_target.exists() is False
            assert (
                output_dir / "drifted-candidate.docx"
            ).exists() is False
            session.refresh(run)
            assert run.status == DocumentGenerationStatus.PENDING
            assert version.checksum_sha256 is None
            assert version.is_current is False
            assert version.issued_on is None

            version.storage_relative_path = allocation.storage_relative_path
            run.output_document_version_id = None
            session.flush()
            try:
                output_version_module.finalize_output_document_version_write(
                    session,
                    storage,
                    allocation,
                    binary_payload=b"must-not-be-written",
                )
            except output_version_module.OutputVersionAllocationError as exc:
                assert "finalization allocation identity mismatch" in str(exc)
                assert "generation_run.output_document_version_id=" in str(exc)
            else:
                raise AssertionError(
                    "Expected generation-run linkage drift to fail before output write"
                )

            assert original_target.exists() is False
            session.refresh(version)
            assert version.checksum_sha256 is None
            assert version.is_current is False
            assert version.issued_on is None

            run.output_document_version_id = allocation.document_version_id
            session.flush()
            tampered_allocation = replace(
                allocation,
                storage_relative_path=(
                    "Cong ty A - Dia chi A (100)/tampered-candidate.docx"
                ),
            )
            try:
                output_version_module.finalize_output_document_version_write(
                    session,
                    storage,
                    tampered_allocation,
                    binary_payload=b"must-not-be-written",
                )
            except output_version_module.OutputVersionAllocationError as exc:
                assert "finalization allocation identity mismatch" in str(exc)
                assert "document_version.storage_relative_path=" in str(exc)
            else:
                raise AssertionError(
                    "Expected tampered allocation to fail before output write"
                )

            assert original_target.exists() is False
            assert (
                output_dir / "tampered-candidate.docx"
            ).exists() is False

            original_target.write_bytes(b"foreign-output")
            try:
                output_version_module.finalize_output_document_version_write(
                    session,
                    storage,
                    allocation,
                    binary_payload=b"must-not-overwrite-foreign-output",
                )
            except StorageTargetExistsError as exc:
                assert "will not be overwritten" in str(exc)
            else:
                raise AssertionError(
                    "Expected output finalization to reject a target created after allocation"
                )

            assert original_target.read_bytes() == b"foreign-output"
            session.refresh(run)
            session.refresh(version)
            assert run.status == DocumentGenerationStatus.PENDING
            assert version.checksum_sha256 is None
            assert version.is_current is False
            assert version.issued_on is None

            original_target.unlink()

            original_execute = session.execute

            def fail_post_write_db_update(statement, *args, **kwargs):
                if getattr(statement, "is_update", False):
                    raise RuntimeError("simulated post-write DB failure")
                return original_execute(statement, *args, **kwargs)

            monkeypatch.setattr(
                session,
                "execute",
                fail_post_write_db_update,
            )
            try:
                output_version_module.finalize_output_document_version_write(
                    session,
                    storage,
                    allocation,
                    binary_payload=b"must-clean-after-post-write-db-failure",
                )
            except RuntimeError as exc:
                assert "simulated post-write DB failure" in str(exc)
            else:
                raise AssertionError(
                    "Expected post-write DB mutation failure"
                )
            assert original_target.exists() is False

            monkeypatch.setattr(session, "execute", original_execute)
            session.rollback()
            run = session.get(DocumentGenerationRun, allocation.generation_run_id)
            version = session.get(DocumentVersion, allocation.document_version_id)
            assert run is not None
            assert version is not None
            assert run.status == DocumentGenerationStatus.PENDING
            assert version.is_current is False
            assert version.checksum_sha256 is None

            def replace_target_then_fail_db_update(statement, *args, **kwargs):
                if getattr(statement, "is_update", False):
                    original_target.write_bytes(b"foreign-replacement")
                    raise RuntimeError(
                        "simulated DB failure after foreign replacement"
                    )
                return original_execute(statement, *args, **kwargs)

            monkeypatch.setattr(
                session,
                "execute",
                replace_target_then_fail_db_update,
            )
            try:
                output_version_module.finalize_output_document_version_write(
                    session,
                    storage,
                    allocation,
                    binary_payload=b"render-owned-before-replacement",
                )
            except RuntimeError as exc:
                assert "simulated DB failure after foreign replacement" in str(exc)
                assert "Output cleanup failed" in str(exc)
                assert "checksum no longer matches the render result" in str(exc)
            else:
                raise AssertionError(
                    "Expected ownership drift to fail closed during finalizer cleanup"
                )
            assert original_target.read_bytes() == b"foreign-replacement"

            monkeypatch.setattr(session, "execute", original_execute)
            original_target.unlink()
            session.rollback()
            run = session.get(DocumentGenerationRun, allocation.generation_run_id)
            version = session.get(DocumentVersion, allocation.document_version_id)
            assert run is not None
            assert version is not None
            assert run.status == DocumentGenerationStatus.PENDING
            assert version.is_current is False
            assert version.checksum_sha256 is None

            checksum = output_version_module.finalize_output_document_version_write(
                session,
                storage,
                allocation,
                binary_payload=b"canonical-output",
            )
            session.commit()

            session.refresh(run)
            session.refresh(version)
            assert original_target.read_bytes() == b"canonical-output"
            assert checksum == version.checksum_sha256
            assert version.is_current is True
            assert version.issued_on is not None
            assert run.status == DocumentGenerationStatus.SUCCEEDED
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_finalize_output_write_refreshes_preloaded_generation_run_status_before_storage_io(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'finalize-generation-run-refresh.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    storage, root = _build_storage()
    contender = None
    try:
        with Session(engine) as session:
            _, site_id = _seed_case(session)
            company_id = session.get(Site, site_id).company_id  # type: ignore[union-attr]
            dkkd_id = _seed_dkkd(session, site_id, company_id)
            seed_default_template_metadata(session)

            output_dir = root / "dkkd" / "Cong ty A - Dia chi A (100)"
            output_dir.mkdir(parents=True, exist_ok=True)

            preparation_input = DocumentPreparationInput(
                request=DocumentGenerationRequest(
                    family_code="DDKD_CERTIFICATE",
                    requested_by_user_id=None,
                    business_eligibility_certificate_id=dkkd_id,
                    storage_scope="dkkd_folder",
                    idempotency_key="phase11-finalize-run-refresh-001",
                ),
                payload_values={
                    "TenCty": "Cong ty A",
                    "DiachiCoso": "123 Duong A",
                    "HoatdongKD": "Bao quan, ban buon thuoc",
                },
            )
            prepared = prepare_document_generation_job(session, preparation_input)
            allocation = output_version_module.allocate_output_document_version(
                session,
                storage,
                prepared,
                output_filename="candidate.docx",
            )
            session.commit()

        contender = Session(engine, expire_on_commit=False)
        stale_run = contender.get(DocumentGenerationRun, allocation.generation_run_id)
        assert stale_run is not None
        assert stale_run.status == DocumentGenerationStatus.PENDING
        contender.commit()

        with Session(engine) as canceller:
            canonical_run = canceller.get(
                DocumentGenerationRun,
                allocation.generation_run_id,
            )
            assert canonical_run is not None
            canonical_run.status = DocumentGenerationStatus.CANCELLED
            canonical_run.error_summary = "cancelled concurrently"
            canceller.commit()

        target = root / "dkkd" / allocation.storage_relative_path
        assert target.exists() is False

        try:
            output_version_module.finalize_output_document_version_write(
                contender,
                storage,
                allocation,
                binary_payload=b"must-not-write-from-stale-pending-state",
            )
        except output_version_module.OutputVersionAllocationError as exc:
            assert "cannot be finalized from status" in str(exc)
            assert repr(DocumentGenerationStatus.CANCELLED.value) in str(exc)
        else:
            raise AssertionError(
                "Expected finalization to refresh persisted generation-run status before output I/O"
            )

        assert target.exists() is False
        assert stale_run.status == DocumentGenerationStatus.CANCELLED
        assert stale_run.error_summary == "cancelled concurrently"
        version = contender.get(DocumentVersion, allocation.document_version_id)
        assert version is not None
        assert version.is_current is False
        assert version.checksum_sha256 is None
        assert version.issued_on is None
    finally:
        if contender is not None:
            contender.rollback()
            contender.close()
        shutil.rmtree(root, ignore_errors=True)
        engine.dispose()


def test_restore_render_version_state_does_not_reactivate_stale_previous_current_when_candidate_was_never_promoted():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        case_id, _ = _seed_case(session)
        document = Document(
            family_code="RESTORE_STALE_CURRENT_TEST",
            document_type_code="RESTORE_STALE_CURRENT_TEST",
            title="Restore stale current test",
            case_id=case_id,
        )
        session.add(document)
        session.flush()
        variant = DocumentVariant(
            document_id=document.id,
            variant_type=DocumentVariantType.EDITABLE_DOCX,
            language_code="vi",
            is_active=True,
        )
        session.add(variant)
        session.flush()

        previous = DocumentVersion(
            document_variant_id=variant.id,
            version_no=1,
            storage_binding_id=None,
            storage_root="inspection",
            storage_relative_path="restore/previous.docx",
            original_filename="previous.docx",
            checksum_sha256="previous",
            is_current=False,
            issued_on=None,
        )
        candidate = DocumentVersion(
            document_variant_id=variant.id,
            version_no=2,
            storage_binding_id=None,
            storage_root="inspection",
            storage_relative_path="restore/candidate.docx",
            original_filename="candidate.docx",
            checksum_sha256=None,
            is_current=False,
            issued_on=None,
        )
        newer = DocumentVersion(
            document_variant_id=variant.id,
            version_no=3,
            storage_binding_id=None,
            storage_root="inspection",
            storage_relative_path="restore/newer.docx",
            original_filename="newer.docx",
            checksum_sha256="newer",
            is_current=True,
            issued_on=None,
        )
        session.add_all([previous, candidate, newer])
        session.flush()

        allocated = SimpleNamespace(
            allocated=SimpleNamespace(
                output_allocation=SimpleNamespace(
                    document_variant_id=variant.id,
                    document_version_id=candidate.id,
                )
            )
        )
        DocumentWorkflowService._restore_render_version_state(
            session,
            allocated,
            (previous.id,),
            output_was_current_before_render=False,
        )
        session.flush()

        assert previous.is_current is False
        assert candidate.is_current is False
        assert newer.is_current is True


def test_render_cleanup_preserves_target_before_finalizer_returns_checksum():
    service = DocumentWorkflowService()
    storage, root = _build_storage()
    try:
        target = root / "inspection" / "2026" / "foreign-before-finalizer.docx"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"foreign-output")
        allocated = SimpleNamespace(
            allocated=SimpleNamespace(
                output_allocation=SimpleNamespace(
                    storage_root="inspection",
                    storage_relative_path="2026/foreign-before-finalizer.docx",
                )
            )
        )

        cleanup_error = service._cleanup_allocated_render_output(
            storage,
            allocated,
            output_was_current_before_render=False,
            expected_checksum=None,
        )

        assert cleanup_error is None
        assert target.read_bytes() == b"foreign-output"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_render_route_removes_new_output_when_db_commit_fails(monkeypatch):
    storage, root = _build_storage()
    try:
        target = root / "inspection" / "2026" / "orphan.docx"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"render-owned-output")
        checksum = storage.checksum("2026/orphan.docx", root="inspection")

        app = create_app("sqlite:///:memory:", storage_service=storage)
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", None) == "/documents/render-template-docx"
        )

        monkeypatch.setattr(
            DocumentWorkflowService,
            "render_template_docx",
            lambda self, session, *, storage, payload, user: {
                "output_storage_root": "inspection",
                "output_storage_relative_path": "2026/orphan.docx",
                "checksum_sha256": checksum,
                "_rollback_cleanup_required": True,
            },
        )
        monkeypatch.setattr(
            document_router_module,
            "commit_or_409",
            lambda session: (_ for _ in ()).throw(
                RuntimeError("simulated commit failure")
            ),
        )

        try:
            route.endpoint(
                payload=SimpleNamespace(model_dump=lambda: {}),
                request=_request_for_app(app),
                session=SimpleNamespace(),
                user=build_authenticated_user(
                    "inspector01",
                    permissions={"document.write"},
                ),
            )
        except RuntimeError as exc:
            assert "simulated commit failure" in str(exc)
        else:
            raise AssertionError("Expected DB commit failure")

        assert target.exists() is False
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_render_route_preserves_replaced_output_when_db_commit_fails(monkeypatch):
    storage, root = _build_storage()
    try:
        target = root / "inspection" / "2026" / "replaced.docx"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"render-owned-output")
        rendered_checksum = storage.checksum(
            "2026/replaced.docx",
            root="inspection",
        )

        app = create_app("sqlite:///:memory:", storage_service=storage)
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", None) == "/documents/render-template-docx"
        )

        monkeypatch.setattr(
            DocumentWorkflowService,
            "render_template_docx",
            lambda self, session, *, storage, payload, user: {
                "output_storage_root": "inspection",
                "output_storage_relative_path": "2026/replaced.docx",
                "checksum_sha256": rendered_checksum,
                "_rollback_cleanup_required": True,
            },
        )

        def replace_output_then_fail_commit(session):
            target.write_bytes(b"foreign-replacement")
            raise RuntimeError("simulated commit failure after foreign replacement")

        monkeypatch.setattr(
            document_router_module,
            "commit_or_409",
            replace_output_then_fail_commit,
        )

        try:
            route.endpoint(
                payload=SimpleNamespace(model_dump=lambda: {}),
                request=_request_for_app(app),
                session=SimpleNamespace(),
                user=build_authenticated_user(
                    "inspector01",
                    permissions={"document.write"},
                ),
            )
        except HTTPException as exc:
            assert exc.status_code == 500
            assert "Document DB commit failed and output cleanup also failed" in exc.detail
            assert "checksum no longer matches the render result" in exc.detail
        else:
            raise AssertionError(
                "Expected commit-failure cleanup to fail closed on replaced output"
            )

        assert target.read_bytes() == b"foreign-replacement"
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


def test_contextual_create_contracts_remain_typed_and_fail_closed_until_promoted():
    specs = list_case_document_context_specs()
    visible_specs = [spec for spec in specs if spec.classification == "PROVEN" and spec.workflow_step is not None]

    assert visible_specs
    khkt = get_case_document_context_spec("INSPECTION_KE_HOACH_KT")
    assert khkt is not None
    assert khkt.create_readiness == "READY_CREATE_OPEN_HISTORY"
    assert all(
        spec.create_readiness == "BUSINESS_INPUT_CONTRACT_MISSING"
        for spec in visible_specs
        if spec.family_code != "INSPECTION_KE_HOACH_KT"
    )
    assert get_case_document_context_spec("ASSESSMENT_MINUTES").create_readiness == "LEGACY_ONLY_UNRESOLVED"

    actions = build_document_action_states(
        open_available=False,
        history_available=False,
        create_readiness=khkt.create_readiness,
        permissions=frozenset({"document.write"}),
        family_code=khkt.family_code,
        parent_scope=khkt.parent_scope,
        parent_id="case-123",
        document_type_code=None,
    )
    create = next(action for action in actions if action["action_key"] == "create")

    assert create["available"] is True
    assert create["reason_code"] is None
    assert create["family_code"] == khkt.family_code
    assert create["parent_scope"] == khkt.parent_scope
    assert create["parent_id"] == "case-123"

    denied_actions = build_document_action_states(
        open_available=False,
        history_available=False,
        create_readiness=khkt.create_readiness,
        permissions=frozenset(),
        family_code=khkt.family_code,
        parent_scope=khkt.parent_scope,
        parent_id="case-123",
        document_type_code=None,
    )
    denied_create = next(action for action in denied_actions if action["action_key"] == "create")
    assert denied_create["available"] is False
    assert denied_create["reason_code"] == "permission_denied"
    assert denied_create["disabled_reason"] == "Tài khoản hiện tại không có quyền tạo tài liệu."


def test_khkt_contextual_create_is_only_available_while_document_is_missing():
    khkt = get_case_document_context_spec("INSPECTION_KE_HOACH_KT")
    assert khkt is not None

    missing_actions = build_document_action_states(
        open_available=False,
        history_available=False,
        create_readiness=khkt.create_readiness,
        permissions=frozenset({"document.write"}),
        family_code=khkt.family_code,
        parent_scope=khkt.parent_scope,
        parent_id="case-123",
        document_type_code=None,
        create_contract={
            "create_gxp_type": "GMP",
            "create_storage_scope": "inspection_folder",
            "create_output_filename": "3. Kế hoạch kiểm tra GMP.docx",
        },
    )
    missing_create = next(action for action in missing_actions if action["action_key"] == "create")
    assert missing_create["available"] is True
    assert missing_create["create_output_filename"] == "3. Kế hoạch kiểm tra GMP.docx"

    existing_actions = build_document_action_states(
        open_available=True,
        history_available=True,
        create_readiness="READY_OPEN_HISTORY",
        permissions=frozenset({"document.read", "document.write"}),
        family_code=khkt.family_code,
        parent_scope=khkt.parent_scope,
        parent_id="case-123",
        document_type_code="INSPECTION_KE_HOACH_KT",
        create_contract={
            "create_gxp_type": "GMP",
            "create_storage_scope": "inspection_folder",
            "create_output_filename": "3. Kế hoạch kiểm tra GMP.docx",
        },
    )
    existing_create = next(action for action in existing_actions if action["action_key"] == "create")
    assert existing_create["available"] is False
    assert existing_create["reason_code"] == "ready_open_history"
    assert "chỉ hỗ trợ mở và xem lịch sử" in existing_create["disabled_reason"]


def test_khkt_contextual_create_retries_until_current_binary_exists():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CatalogReadService()
    user = build_authenticated_user(
        "manager01",
        "manager",
        permissions={"document.read", "document.write"},
    )

    with Session(engine) as session:
        case_id, _ = _seed_case(session)
        document = Document(
            family_code="INSPECTION_KE_HOACH_KT",
            document_type_code="INSPECTION_KE_HOACH_KT",
            title="Kế hoạch kiểm tra",
            case_id=case_id,
        )
        session.add(document)
        session.flush()

        def khkt_actions():
            item = next(
                row
                for row in service._build_case_contextual_document_actions(
                    session,
                    case_id=case_id,
                    capa_cycles=[],
                    user=user,
                )
                if row["family_code"] == "INSPECTION_KE_HOACH_KT"
            )
            return {action["action_key"]: action for action in item["actions"]}

        shell_actions = khkt_actions()
        assert shell_actions["create"]["available"] is True
        assert shell_actions["open"]["available"] is False
        assert shell_actions["history"]["available"] is True

        variant = DocumentVariant(
            document_id=document.id,
            variant_type=DocumentVariantType.EDITABLE_DOCX,
            language_code="vi",
            is_active=True,
        )
        session.add(variant)
        session.flush()
        version = DocumentVersion(
            document_variant_id=variant.id,
            version_no=1,
            storage_binding_id=None,
            storage_root="inspection",
            storage_relative_path="2024/3. Kế hoạch kiểm tra GMP.docx",
            original_filename="3. Kế hoạch kiểm tra GMP.docx",
            checksum_sha256=None,
            is_current=False,
            issued_on=None,
        )
        session.add(version)
        session.flush()

        allocated_only_actions = khkt_actions()
        assert allocated_only_actions["create"]["available"] is True
        assert allocated_only_actions["open"]["available"] is False
        assert allocated_only_actions["history"]["available"] is True

        version.is_current = True
        session.flush()

        current_actions = khkt_actions()
        assert current_actions["create"]["available"] is False
        assert current_actions["create"]["reason_code"] == "ready_open_history"
        assert current_actions["open"]["available"] is True
        assert current_actions["history"]["available"] is True


def test_khkt_workspace_prefers_openable_current_binary_over_incomplete_duplicate():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CatalogReadService()
    user = build_authenticated_user(
        "manager01",
        "manager",
        permissions={"document.read", "document.write"},
    )

    with Session(engine) as session:
        case_id, _ = _seed_case(session)
        usable_document = Document(
            family_code="INSPECTION_KE_HOACH_KT",
            document_type_code="INSPECTION_KE_HOACH_KT",
            title="Kế hoạch kiểm tra usable",
            case_id=case_id,
        )
        broken_document = Document(
            family_code="INSPECTION_KE_HOACH_KT",
            document_type_code="INSPECTION_KE_HOACH_KT",
            title="Kế hoạch kiểm tra broken",
            case_id=case_id,
        )
        session.add_all([usable_document, broken_document])
        session.flush()
        usable_variant = DocumentVariant(
            document_id=usable_document.id,
            variant_type=DocumentVariantType.EDITABLE_DOCX,
            language_code="vi",
            is_active=True,
        )
        broken_variant = DocumentVariant(
            document_id=broken_document.id,
            variant_type=DocumentVariantType.EDITABLE_DOCX,
            language_code="vi",
            is_active=True,
        )
        session.add_all([usable_variant, broken_variant])
        session.flush()
        session.add_all(
            [
                DocumentVersion(
                    document_variant_id=usable_variant.id,
                    version_no=1,
                    storage_binding_id=None,
                    storage_root="inspection",
                    storage_relative_path="2024/usable-khkt.docx",
                    original_filename="usable-khkt.docx",
                    checksum_sha256="usable",
                    is_current=True,
                    issued_on=None,
                ),
                DocumentVersion(
                    document_variant_id=broken_variant.id,
                    version_no=2,
                    storage_binding_id=None,
                    storage_root="inspection",
                    storage_relative_path="",
                    original_filename="broken-khkt.docx",
                    checksum_sha256="broken",
                    is_current=True,
                    issued_on=None,
                ),
            ]
        )
        session.flush()

        item = next(
            row
            for row in service._build_case_contextual_document_actions(
                session,
                case_id=case_id,
                capa_cycles=[],
                user=user,
            )
            if row["family_code"] == "INSPECTION_KE_HOACH_KT"
        )
        actions = {action["action_key"]: action for action in item["actions"]}

    assert item["document_id"] == usable_document.id
    assert item["original_filename"] == "usable-khkt.docx"
    assert item["open_available"] is True
    assert actions["open"]["available"] is True
    assert actions["create"]["available"] is False
    assert actions["create"]["reason_code"] == "ready_open_history"


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


def test_get_current_document_binary_locator_rejects_multiple_current_versions_in_one_variant():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = DocumentWorkflowService()

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
        variant = DocumentVariant(
            document_id=document.id,
            variant_type=DocumentVariantType.EDITABLE_DOCX,
            language_code="vi",
            is_active=True,
        )
        session.add(variant)
        session.flush()
        session.add_all(
            [
                DocumentVersion(
                    document_variant_id=variant.id,
                    version_no=1,
                    storage_binding_id=None,
                    storage_root="inspection",
                    storage_relative_path="2026/old.docx",
                    original_filename="old.docx",
                    checksum_sha256="old",
                    is_current=False,
                    issued_on=None,
                ),
                DocumentVersion(
                    document_variant_id=variant.id,
                    version_no=2,
                    storage_binding_id=None,
                    storage_root="inspection",
                    storage_relative_path="2026/current.docx",
                    original_filename="current.docx",
                    checksum_sha256="new",
                    is_current=True,
                    issued_on=None,
                ),
                DocumentVersion(
                    document_variant_id=variant.id,
                    version_no=3,
                    storage_binding_id=None,
                    storage_root="inspection",
                    storage_relative_path="",
                    original_filename="broken-current.docx",
                    checksum_sha256="broken",
                    is_current=True,
                    issued_on=None,
                ),
            ]
        )
        session.commit()

        try:
            service.get_current_document_binary_locator_for_parent(
                session,
                document_id=document.id,
                expected_parent_scope="case",
                expected_parent_id=case_id,
            )
        except HTTPException as exc:
            assert exc.status_code == 409
            assert exc.detail == "Document variant has multiple current binary versions."
        else:
            raise AssertionError(
                "Expected duplicate current versions in one document variant to fail closed"
            )


def test_get_current_document_binary_locator_preserves_current_selection_across_distinct_variants():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = DocumentWorkflowService()

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
        incomplete_variant = DocumentVariant(
            document_id=document.id,
            variant_type=DocumentVariantType.EDITABLE_DOCX,
            language_code="vi",
            is_active=True,
        )
        complete_variant = DocumentVariant(
            document_id=document.id,
            variant_type=DocumentVariantType.EDITABLE_DOCX,
            language_code="en",
            is_active=True,
        )
        session.add_all([incomplete_variant, complete_variant])
        session.flush()
        session.add_all(
            [
                DocumentVersion(
                    document_variant_id=incomplete_variant.id,
                    version_no=1,
                    storage_binding_id=None,
                    storage_root="inspection",
                    storage_relative_path="",
                    original_filename="incomplete-current.docx",
                    checksum_sha256="incomplete",
                    is_current=True,
                    issued_on=None,
                ),
                DocumentVersion(
                    document_variant_id=complete_variant.id,
                    version_no=1,
                    storage_binding_id=None,
                    storage_root="inspection",
                    storage_relative_path="2026/current.docx",
                    original_filename="current.docx",
                    checksum_sha256="current",
                    is_current=True,
                    issued_on=None,
                ),
            ]
        )
        session.commit()

        locator = service.get_current_document_binary_locator_for_parent(
            session,
            document_id=document.id,
            expected_parent_scope="case",
            expected_parent_id=case_id,
        )

    assert locator.storage_root == "inspection"
    assert locator.storage_relative_path == "2026/current.docx"
    assert locator.original_filename == "current.docx"
    assert locator.media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_document_content_route_streams_current_binary_without_locator_leakage(tmp_path: Path):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    storage, root = _build_storage()
    try:
        with Session(engine) as session:
            case_id, _ = _seed_case(session)
            target_dir = root / "inspection" / "2026"
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / "decision.docx"
            target_file.write_bytes(b"docx-binary")
            document = Document(
                family_code="CERTIFICATE_DECISION",
                document_type_code="CERTIFICATE_DECISION",
                title="Quyết định cấp CC",
                case_id=case_id,
            )
            session.add(document)
            session.flush()
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
                    storage_relative_path="2026/decision.docx",
                    original_filename="decision.docx",
                    checksum_sha256="checksum",
                    is_current=True,
                    issued_on=None,
                )
            )
            session.commit()
            document_id = document.id

        app = create_app(str(engine.url), storage_service=storage)
        with Session(engine) as read_session:
            response = _document_content_endpoint(app, "/cases/{case_id}/documents/{document_id}/content")(
                case_id,
                document_id,
                _request_for_app(app),
                read_session,
                build_authenticated_user("reader.local", permissions={"document.read"}),
            )

            assert response.status_code == 200
            assert asyncio.run(_read_streaming_response_body(response)) == b"docx-binary"
            assert response.headers["content-type"].startswith(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            assert "filename*=UTF-8''decision.docx" in response.headers["content-disposition"]
            assert "2026/decision.docx" not in str(response.headers)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_document_content_route_fails_closed_when_current_binary_is_missing_from_storage(
    tmp_path: Path,
):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    storage, root = _build_storage()
    try:
        with Session(engine) as session:
            case_id, _ = _seed_case(session)
            document = Document(
                family_code="INSPECTION_KE_HOACH_KT",
                document_type_code="INSPECTION_KE_HOACH_KT",
                title="Kế hoạch kiểm tra",
                case_id=case_id,
            )
            session.add(document)
            session.flush()
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
                    storage_relative_path="2026/missing-khkt.docx",
                    original_filename="missing-khkt.docx",
                    checksum_sha256="db-checksum-only",
                    is_current=True,
                    issued_on=None,
                )
            )
            session.commit()
            document_id = document.id

        app = create_app(str(engine.url), storage_service=storage)
        with Session(engine) as read_session:
            try:
                _document_content_endpoint(
                    app,
                    "/cases/{case_id}/documents/{document_id}/content",
                )(
                    case_id,
                    document_id,
                    _request_for_app(app),
                    read_session,
                    build_authenticated_user(
                        "reader.local",
                        permissions={"document.read"},
                    ),
                )
            except HTTPException as exc:
                assert exc.status_code == 409
                assert exc.detail == "Document current binary is missing from storage."
            else:
                raise AssertionError(
                    "Expected missing current document binary to fail closed"
                )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_document_content_route_reports_storage_service_failure_before_stream(
    tmp_path: Path,
    monkeypatch,
):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    storage, root = _build_storage()
    try:
        with Session(engine) as session:
            case_id, _ = _seed_case(session)
            document = Document(
                family_code="INSPECTION_KE_HOACH_KT",
                document_type_code="INSPECTION_KE_HOACH_KT",
                title="Kế hoạch kiểm tra",
                case_id=case_id,
            )
            session.add(document)
            session.flush()
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
                    storage_relative_path="2026/unavailable-khkt.docx",
                    original_filename="unavailable-khkt.docx",
                    checksum_sha256="db-checksum-only",
                    is_current=True,
                    issued_on=None,
                )
            )
            session.commit()
            document_id = document.id

        monkeypatch.setattr(
            storage,
            "exists",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                StorageOperationError("simulated storage outage")
            ),
        )
        app = create_app(str(engine.url), storage_service=storage)
        with Session(engine) as read_session:
            try:
                _document_content_endpoint(
                    app,
                    "/cases/{case_id}/documents/{document_id}/content",
                )(
                    case_id,
                    document_id,
                    _request_for_app(app),
                    read_session,
                    build_authenticated_user(
                        "reader.local",
                        permissions={"document.read"},
                    ),
                )
            except HTTPException as exc:
                assert exc.status_code == 503
                assert exc.detail == (
                    "StorageService failed while opening document content."
                )
            else:
                raise AssertionError(
                    "Expected storage failure to remain distinct from missing binary"
                )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_document_content_routes_enforce_exact_case_and_capa_parent_ownership():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    storage, root = _build_storage()
    try:
        with Session(engine) as session:
            case_id, site_id = _seed_case(session)
            other_case = Case(
                legacy_inspection_id=201,
                legacy_inspection_code="KT-2024-GMP-OTHER",
                site_id=site_id,
                gxp_type="GMP",
                state=CaseState.PLANNED,
                opened_year=2024,
            )
            session.add(other_case)
            session.flush()
            first_cycle_id = _seed_capa_cycle(session, case_id, round_no=1)
            second_cycle_id = _seed_capa_cycle(session, case_id, round_no=2)
            change_request = ChangeRequest(
                site_id=site_id,
                legacy_change_request_id=400,
                scope_label="Thay đổi độc lập",
                state=ChangeRequestState.RECEIVED,
            )
            session.add(change_request)
            session.flush()
            case_document = Document(
                family_code="INSPECTION_QD_KT",
                document_type_code="INSPECTION_QD_KT",
                case_id=case_id,
            )
            capa_document = Document(
                family_code="INSPECTION_CAPA_LAN_1",
                document_type_code="INSPECTION_CAPA_LAN_1",
                capa_cycle_id=first_cycle_id,
            )
            change_document = Document(
                family_code="CHANGE_NOTICE",
                document_type_code="CHANGE_NOTICE",
                change_request_id=change_request.id,
            )
            ambiguous_document = Document(
                family_code="INVALID_MULTI_PARENT",
                document_type_code="INVALID_MULTI_PARENT",
                case_id=case_id,
                change_request_id=change_request.id,
            )
            session.add_all([case_document, capa_document, change_document, ambiguous_document])
            session.commit()
            other_case_id = other_case.id
            case_document_id = case_document.id
            capa_document_id = capa_document.id
            change_document_id = change_document.id
            ambiguous_document_id = ambiguous_document.id

        app = create_app(str(engine.url), storage_service=storage)
        case_endpoint = _document_content_endpoint(app, "/cases/{case_id}/documents/{document_id}/content")
        capa_endpoint = _document_content_endpoint(
            app,
            "/cases/{case_id}/capa-cycles/{capa_cycle_id}/documents/{document_id}/content",
        )
        user = build_authenticated_user("reader.local", permissions={"document.read"})
        with Session(engine) as read_session:
            rejected_calls = [
                lambda: case_endpoint(other_case_id, case_document_id, _request_for_app(app), read_session, user),
                lambda: capa_endpoint(case_id, second_cycle_id, capa_document_id, _request_for_app(app), read_session, user),
                lambda: case_endpoint(case_id, capa_document_id, _request_for_app(app), read_session, user),
                lambda: case_endpoint(case_id, change_document_id, _request_for_app(app), read_session, user),
                lambda: case_endpoint(case_id, ambiguous_document_id, _request_for_app(app), read_session, user),
            ]
            for invoke in rejected_calls:
                try:
                    invoke()
                except HTTPException as exc:
                    assert exc.status_code == 404
                else:
                    raise AssertionError("Expected binary document route to reject an unrelated business owner")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_owner_scoped_binary_locator_fails_closed_for_missing_or_incomplete_current_version():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = DocumentWorkflowService()

    with Session(engine) as session:
        case_id, _ = _seed_case(session)
        missing_version_document = Document(
            family_code="INSPECTION_QD_KT",
            document_type_code="INSPECTION_QD_KT",
            case_id=case_id,
        )
        incomplete_locator_document = Document(
            family_code="INSPECTION_KE_HOACH_KT",
            document_type_code="INSPECTION_KE_HOACH_KT",
            case_id=case_id,
        )
        noncurrent_only_document = Document(
            family_code="INSPECTION_KE_HOACH_KT",
            document_type_code="INSPECTION_KE_HOACH_KT",
            case_id=case_id,
        )
        session.add_all([
            missing_version_document,
            incomplete_locator_document,
            noncurrent_only_document,
        ])
        session.flush()
        variant = DocumentVariant(
            document_id=incomplete_locator_document.id,
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
                storage_relative_path="",
                original_filename="incomplete.docx",
                checksum_sha256="checksum",
                is_current=True,
                issued_on=None,
            )
        )
        noncurrent_variant = DocumentVariant(
            document_id=noncurrent_only_document.id,
            variant_type=DocumentVariantType.EDITABLE_DOCX,
            language_code="vi",
            is_active=True,
        )
        session.add(noncurrent_variant)
        session.flush()
        session.add(
            DocumentVersion(
                document_variant_id=noncurrent_variant.id,
                version_no=1,
                storage_binding_id=None,
                storage_root="inspection",
                storage_relative_path="2026/not-current.docx",
                original_filename="not-current.docx",
                checksum_sha256=None,
                is_current=False,
                issued_on=None,
            )
        )
        session.commit()

        for document_id, expected_detail in [
            (missing_version_document.id, "Document does not have a current binary version."),
            (noncurrent_only_document.id, "Document does not have a current binary version."),
            (incomplete_locator_document.id, "Document current version locator is incomplete."),
        ]:
            try:
                service.get_current_document_binary_locator_for_parent(
                    session,
                    document_id=document_id,
                    expected_parent_scope="case",
                    expected_parent_id=case_id,
                )
            except HTTPException as exc:
                assert exc.status_code == 409
                assert exc.detail == expected_detail
            else:
                raise AssertionError("Expected incomplete document binary state to fail closed")


def test_document_content_route_requires_document_read_permission(tmp_path: Path):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    storage, root = _build_storage()
    try:
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
                    storage_relative_path="2026/decision.docx",
                    original_filename="decision.docx",
                    checksum_sha256="checksum",
                    is_current=True,
                    issued_on=None,
                )
            )
            session.commit()
            document_id = document.id

        app = create_app(str(engine.url), storage_service=storage)
        with Session(engine) as read_session:
            try:
                _document_content_endpoint(app, "/cases/{case_id}/documents/{document_id}/content")(
                    case_id,
                    document_id,
                    _request_for_app(app),
                    read_session,
                    build_authenticated_user("blocked.local", permissions={"case.read"}),
                )
            except HTTPException as exc:
                assert exc.status_code == 403
            else:
                raise AssertionError("Expected document content route to require document.read permission")
    finally:
        shutil.rmtree(root, ignore_errors=True)
