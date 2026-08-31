from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.audit_payload import normalize_and_redact_audit_payload
from backend.app.auth import AuthenticatedUser
from backend.app.db.enums import AuditActorType, DocumentGenerationStatus
from backend.app.db.models.phase1 import (
    AppUser,
    AuditEvent,
    Document,
    DocumentGenerationRun,
    DocumentSourceDependency,
    DocumentVariant,
    DocumentVersion,
    TemplateDefinition,
)
from backend.app.document.docx_template_render import (
    DocxTemplateRenderError,
    render_template_aware_docx_and_finalize,
)
from backend.app.document.output_version import OutputVersionAllocationError
from backend.app.document.persistence import DocumentPersistenceError
from backend.app.document.payload_builders import DocumentPayloadBuildError
from backend.app.document.service import (
    DocumentPreparationInput,
    prepare_document_generation_job,
    prepare_template_aware_docx_generation,
)
from backend.app.document.service_contract import (
    DocumentGenerationRequest,
    DocumentTemplateSelectionError,
)
from backend.app.document.source_binary_contract import SourceBinaryContractError
from backend.app.document.template_binary import TemplateBinaryError
from backend.app.document.template_contract_runtime import (
    TemplateContractRuntimeError,
    build_scalar_replacement_plan_for_template,
    load_default_template_contract_reconciliation,
)
from backend.app.storage.types import StorageOperationError, StorageServiceProtocol


@dataclass(frozen=True)
class TemplateReadiness:
    template_definition_id: str | None
    family_code: str
    template_name: str
    readiness_status: str
    detail: str
    storage_root: str | None
    storage_relative_path: str | None
    original_filename: str | None
    checksum_sha256: str | None
    scalar_replacement_mode: str | None
    template_variant_key: str | None


class DocumentWorkflowService:
    def _get_or_create_app_user(self, session: Session, user: AuthenticatedUser) -> AppUser:
        stmt = select(AppUser).where(AppUser.username == user.username)
        row = session.scalars(stmt).first()
        if row is not None:
            return row
        row = AppUser(username=user.username, display_name=user.username, is_active=True)
        session.add(row)
        session.flush()
        return row

    def _write_audit_event(
        self,
        session: Session,
        *,
        actor: AppUser,
        entity_type: str,
        entity_id: str,
        action: str,
        payload: dict[str, Any],
    ) -> AuditEvent:
        audit_event = AuditEvent(
            actor_type=AuditActorType.USER,
            actor_user_id=actor.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_redacted=json.dumps(normalize_and_redact_audit_payload(payload), ensure_ascii=False, sort_keys=True),
        )
        session.add(audit_event)
        session.flush()
        return audit_event

    def _build_generation_request(self, payload: dict[str, Any], user_id: str) -> DocumentGenerationRequest:
        return DocumentGenerationRequest(
            family_code=payload["family_code"],
            requested_by_user_id=user_id,
            case_id=payload.get("case_id"),
            capa_cycle_id=payload.get("capa_cycle_id"),
            certificate_id=payload.get("certificate_id"),
            business_eligibility_certificate_id=payload.get("business_eligibility_certificate_id"),
            change_request_id=payload.get("change_request_id"),
            gxp_type=payload.get("gxp_type"),
            legacy_mode=payload.get("legacy_mode"),
            storage_scope=payload.get("storage_scope"),
            language_code=payload.get("language_code") or "vi",
            idempotency_key=payload.get("idempotency_key"),
            payload=payload.get("payload"),
        )

    def _build_preparation_input(self, payload: dict[str, Any], user_id: str) -> DocumentPreparationInput:
        request = self._build_generation_request(payload, user_id)
        return DocumentPreparationInput(
            request=request,
            payload_values=dict(payload.get("payload") or {}),
            payload_notes=payload.get("payload_notes"),
            strict_payload=bool(payload.get("strict_payload", True)),
        )

    def _load_template_definition(self, session: Session, template_definition_id: str | None) -> TemplateDefinition | None:
        if template_definition_id is None:
            return None
        return session.get(TemplateDefinition, template_definition_id)

    def _inspect_template_readiness(
        self,
        session: Session,
        storage: StorageServiceProtocol | None,
        prepared,
    ) -> TemplateReadiness:
        template_definition = self._load_template_definition(session, prepared.persisted_state.template_definition_id)
        template_name = (
            prepared.generation_plan.template.template_pattern
            if template_definition is None
            else template_definition.template_name
        )
        if template_definition is None:
            return TemplateReadiness(
                template_definition_id=None,
                family_code=prepared.generation_plan.template.family_code,
                template_name=template_name,
                readiness_status="missing_template_definition",
                detail="No template_definition row is linked to the prepared generation.",
                storage_root=None,
                storage_relative_path=None,
                original_filename=None,
                checksum_sha256=None,
                scalar_replacement_mode=None,
                template_variant_key=None,
            )
        if template_definition.template_storage_root is None or template_definition.template_storage_relative_path is None:
            return TemplateReadiness(
                template_definition_id=template_definition.id,
                family_code=template_definition.family_code,
                template_name=template_definition.template_name,
                readiness_status="missing_template_locator",
                detail="TemplateDefinition has no exact template binary locator yet.",
                storage_root=None,
                storage_relative_path=None,
                original_filename=template_definition.template_original_filename,
                checksum_sha256=template_definition.template_checksum_sha256,
                scalar_replacement_mode=None,
                template_variant_key=None,
            )
        if template_definition.template_storage_root != "template":
            return TemplateReadiness(
                template_definition_id=template_definition.id,
                family_code=template_definition.family_code,
                template_name=template_definition.template_name,
                readiness_status="invalid_template_root",
                detail="TemplateDefinition template binary locator must use storage_root='template'.",
                storage_root=template_definition.template_storage_root,
                storage_relative_path=template_definition.template_storage_relative_path,
                original_filename=template_definition.template_original_filename,
                checksum_sha256=template_definition.template_checksum_sha256,
                scalar_replacement_mode=None,
                template_variant_key=None,
            )
        if storage is None:
            return TemplateReadiness(
                template_definition_id=template_definition.id,
                family_code=template_definition.family_code,
                template_name=template_definition.template_name,
                readiness_status="storage_service_unavailable",
                detail="StorageService is not available, so template bytes cannot be opened.",
                storage_root=template_definition.template_storage_root,
                storage_relative_path=template_definition.template_storage_relative_path,
                original_filename=template_definition.template_original_filename,
                checksum_sha256=template_definition.template_checksum_sha256,
                scalar_replacement_mode=None,
                template_variant_key=None,
            )
        try:
            with storage.read_stream(
                template_definition.template_storage_relative_path,
                root=template_definition.template_storage_root,
            ) as stream:
                template_bytes = stream.read()
            replacement_plan = build_scalar_replacement_plan_for_template(
                load_default_template_contract_reconciliation(),
                prepared.generation_plan.template.family_code,
                prepared.payload_result.envelope.fields,
                template_bytes=template_bytes,
            )
        except (TemplateContractRuntimeError, TemplateBinaryError, StorageOperationError, FileNotFoundError) as exc:
            return TemplateReadiness(
                template_definition_id=template_definition.id,
                family_code=template_definition.family_code,
                template_name=template_definition.template_name,
                readiness_status="runtime_contract_failed",
                detail=str(exc),
                storage_root=template_definition.template_storage_root,
                storage_relative_path=template_definition.template_storage_relative_path,
                original_filename=template_definition.template_original_filename,
                checksum_sha256=template_definition.template_checksum_sha256,
                scalar_replacement_mode=None,
                template_variant_key=None,
            )
        return TemplateReadiness(
            template_definition_id=template_definition.id,
            family_code=template_definition.family_code,
            template_name=template_definition.template_name,
            readiness_status="direct_stream_ready",
            detail="TemplateDefinition has an exact template binary locator and its runtime contract is inspectable.",
            storage_root=template_definition.template_storage_root,
            storage_relative_path=template_definition.template_storage_relative_path,
            original_filename=template_definition.template_original_filename,
            checksum_sha256=template_definition.template_checksum_sha256,
            scalar_replacement_mode=replacement_plan.mode,
            template_variant_key=replacement_plan.template_variant_key,
        )

    def _build_blocked_reasons(self, prepared, template_readiness: TemplateReadiness) -> list[str]:
        reasons: list[str] = []
        if not prepared.render_ready:
            for requirement in prepared.source_binary_requirements:
                if requirement.readiness_status != "direct_stream_ready":
                    reasons.append(
                        f"source_dependency:{requirement.source_family_code}:{requirement.readiness_status}"
                    )
        if prepared.generation_plan.template.source_application != "Word":
            reasons.append(f"source_application:{prepared.generation_plan.template.source_application}")
        if template_readiness.readiness_status != "direct_stream_ready":
            reasons.append(f"template:{template_readiness.readiness_status}")
        elif template_readiness.scalar_replacement_mode not in {"contract_exact", "contract_variant_exact"}:
            reasons.append(f"template:{template_readiness.scalar_replacement_mode or 'unknown_mode'}")
        return reasons

    def _mark_generation_run_failed(self, session: Session, generation_run_id: str, detail: str) -> None:
        row = session.get(DocumentGenerationRun, generation_run_id)
        if row is None:
            return
        row.status = DocumentGenerationStatus.FAILED
        row.error_summary = detail
        session.flush()

    def _serialize_generation_status(self, session: Session, generation_run_id: str) -> dict[str, Any]:
        row = session.get(DocumentGenerationRun, generation_run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Document generation run not found.")
        dependencies = list(
            session.scalars(
                select(DocumentSourceDependency).where(
                    DocumentSourceDependency.document_generation_run_id == row.id
                )
            )
        )
        return {
            "generation_run_id": row.id,
            "document_id": row.document_id,
            "template_binding_id": row.template_binding_id,
            "template_definition_id": row.template_definition_id,
            "output_document_version_id": row.output_document_version_id,
            "status": row.status.value,
            "source_application": row.source_application,
            "requested_by_user_id": row.requested_by_user_id,
            "input_payload_redacted": None if row.input_payload_redacted is None else json.loads(row.input_payload_redacted),
            "error_summary": row.error_summary,
            "idempotency_key": row.idempotency_key,
            "source_dependencies": [
                {
                    "source_family_code": self._source_dependency_family_code(session, item.source_document_id),
                    "dependency_type": item.dependency_type,
                    "required_bookmarks": []
                    if item.source_bookmarks is None
                    else list(json.loads(item.source_bookmarks)),
                    "condition": item.notes,
                }
                for item in dependencies
            ],
        }

    def _source_dependency_family_code(self, session: Session, source_document_id: str) -> str:
        row = session.get(Document, source_document_id)
        return "unknown" if row is None else row.family_code

    def _serialize_document_detail(self, session: Session, document_id: str) -> dict[str, Any]:
        row = session.get(Document, document_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        variants = list(session.scalars(select(DocumentVariant).where(DocumentVariant.document_id == row.id)))
        runs = list(session.scalars(select(DocumentGenerationRun).where(DocumentGenerationRun.document_id == row.id)))
        return {
            "document_id": row.id,
            "family_code": row.family_code,
            "document_type_code": row.document_type_code,
            "title": row.title,
            "legacy_entity_type": None if row.legacy_entity_type is None else row.legacy_entity_type.value,
            "case_id": row.case_id,
            "capa_cycle_id": row.capa_cycle_id,
            "certificate_id": row.certificate_id,
            "business_eligibility_certificate_id": row.business_eligibility_certificate_id,
            "change_request_id": row.change_request_id,
            "variants": [
                {
                    "id": variant.id,
                    "variant_type": variant.variant_type.value,
                    "language_code": variant.language_code,
                    "is_active": variant.is_active,
                    "versions": [
                        {
                            "id": version.id,
                            "version_no": version.version_no,
                            "original_filename": version.original_filename,
                            "is_current": version.is_current,
                            "issued_on": version.issued_on,
                        }
                        for version in session.scalars(
                            select(DocumentVersion)
                            .where(DocumentVersion.document_variant_id == variant.id)
                            .order_by(DocumentVersion.version_no.asc())
                        )
                    ],
                }
                for variant in variants
            ],
            "generation_runs": [self._serialize_generation_status(session, run.id) for run in runs],
        }

    def prepare_generation(
        self,
        session: Session,
        *,
        storage: StorageServiceProtocol | None,
        payload: dict[str, Any],
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        actor = self._get_or_create_app_user(session, user)
        try:
            prepared = prepare_document_generation_job(
                session,
                self._build_preparation_input(payload, actor.id),
            )
        except (
            DocumentTemplateSelectionError,
            DocumentPayloadBuildError,
            DocumentPersistenceError,
            SourceBinaryContractError,
        ) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        template_readiness = self._inspect_template_readiness(session, storage, prepared)
        blocked_reasons = self._build_blocked_reasons(prepared, template_readiness)
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="document_generation_run",
            entity_id=prepared.persisted_state.generation_run_id,
            action="document.prepare",
            payload={
                "family_code": prepared.generation_plan.template.family_code,
                "document_id": prepared.persisted_state.document_id,
                "generation_run_id": prepared.persisted_state.generation_run_id,
                "render_ready": prepared.render_ready,
                "template_render_ready": not blocked_reasons,
                "blocked_reasons": blocked_reasons,
            },
        )
        session.flush()
        generation_run = session.get(DocumentGenerationRun, prepared.persisted_state.generation_run_id)
        if generation_run is None:
            raise HTTPException(status_code=500, detail="Prepared generation run disappeared unexpectedly.")
        return {
            "document_id": prepared.persisted_state.document_id,
            "document_variant_id": prepared.persisted_state.document_variant_id,
            "generation_run_id": prepared.persisted_state.generation_run_id,
            "generation_status": generation_run.status.value,
            "reused_generation_run": prepared.persisted_state.reused_generation_run,
            "render_ready": prepared.render_ready,
            "template_render_ready": len(blocked_reasons) == 0,
            "blocked_reasons": blocked_reasons,
            "selected_template": {
                "family_code": prepared.generation_plan.template.family_code,
                "logical_name": prepared.generation_plan.template.logical_name,
                "template_pattern": prepared.generation_plan.template.template_pattern,
                "source_application": prepared.generation_plan.template.source_application,
                "storage_scope": prepared.generation_plan.template.storage_scope,
                "host_procedure": prepared.generation_plan.template.host_procedure,
                "population_procedures": list(prepared.generation_plan.template.population_procedures),
                "notes": prepared.generation_plan.template.notes,
            },
            "payload_used_fields": list(prepared.payload_result.used_fields),
            "missing_registry_fields": list(prepared.payload_result.missing_registry_fields),
            "unexpected_input_fields": list(prepared.payload_result.unexpected_input_fields),
            "source_dependencies": [
                {
                    "source_family_code": item.source_family_code,
                    "dependency_type": item.dependency_type,
                    "required_bookmarks": list(item.required_bookmarks),
                    "condition": item.condition,
                }
                for item in prepared.generation_plan.source_dependencies
            ],
            "source_binary_requirements": [
                {
                    "source_document_id": item.source_document_id,
                    "source_document_version_id": item.source_document_version_id,
                    "source_family_code": item.source_family_code,
                    "readiness_status": item.readiness_status,
                    "detail": item.detail,
                    "storage_root": item.storage_root,
                    "folder_relative_path": item.folder_relative_path,
                    "exact_storage_root": item.exact_storage_root,
                    "exact_storage_relative_path": item.exact_storage_relative_path,
                    "original_filename": item.original_filename,
                    "required_bookmarks": list(item.required_bookmarks),
                    "legacy_filename_prefix_hints": list(item.legacy_filename_prefix_hints),
                }
                for item in prepared.source_binary_requirements
            ],
            "template_readiness": {
                "template_definition_id": template_readiness.template_definition_id,
                "family_code": template_readiness.family_code,
                "template_name": template_readiness.template_name,
                "readiness_status": template_readiness.readiness_status,
                "detail": template_readiness.detail,
                "storage_root": template_readiness.storage_root,
                "storage_relative_path": template_readiness.storage_relative_path,
                "original_filename": template_readiness.original_filename,
                "checksum_sha256": template_readiness.checksum_sha256,
                "scalar_replacement_mode": template_readiness.scalar_replacement_mode,
                "template_variant_key": template_readiness.template_variant_key,
            },
            "template_definition_id": prepared.persisted_state.template_definition_id,
            "template_binding_id": prepared.persisted_state.template_binding_id,
            "audit_event_id": audit_event.id,
        }

    def render_template_docx(
        self,
        session: Session,
        *,
        storage: StorageServiceProtocol | None,
        payload: dict[str, Any],
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        if storage is None:
            raise HTTPException(status_code=503, detail="StorageService is unavailable for document rendering.")
        actor = self._get_or_create_app_user(session, user)
        render_payload = dict(payload)
        if not render_payload.get("idempotency_key"):
            render_payload["idempotency_key"] = f"render-{uuid4()}"
        try:
            prepared = prepare_document_generation_job(
                session,
                self._build_preparation_input(render_payload, actor.id),
            )
            template_readiness = self._inspect_template_readiness(session, storage, prepared)
            blocked_reasons = self._build_blocked_reasons(prepared, template_readiness)
            if blocked_reasons:
                detail = "Document family is not render-safe: " + ", ".join(blocked_reasons)
                self._mark_generation_run_failed(session, prepared.persisted_state.generation_run_id, detail)
                raise HTTPException(status_code=409, detail=detail)
            allocated = prepare_template_aware_docx_generation(
                session,
                storage,
                self._build_preparation_input(render_payload, actor.id),
                output_filename=render_payload["output_filename"],
            )
            result = render_template_aware_docx_and_finalize(session, storage, allocated)
        except HTTPException:
            raise
        except (
            DocumentTemplateSelectionError,
            DocumentPayloadBuildError,
            DocumentPersistenceError,
            OutputVersionAllocationError,
            SourceBinaryContractError,
            TemplateBinaryError,
            TemplateContractRuntimeError,
            DocxTemplateRenderError,
            StorageOperationError,
        ) as exc:
            if "prepared" in locals():
                self._mark_generation_run_failed(session, prepared.persisted_state.generation_run_id, str(exc))
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="document_generation_run",
            entity_id=result.generation_run_id,
            action="document.render_template_docx",
            payload={
                "document_version_id": result.document_version_id,
                "generation_run_id": result.generation_run_id,
                "checksum_sha256": result.checksum_sha256,
                "scalar_replacement_mode": result.scalar_replacement_mode,
                "template_variant_key": result.template_variant_key,
            },
        )
        session.flush()
        document_version = session.get(DocumentVersion, result.document_version_id)
        if document_version is None or document_version.storage_root is None or document_version.storage_relative_path is None:
            raise HTTPException(status_code=500, detail="Rendered document version locator is incomplete.")
        generation_run = session.get(DocumentGenerationRun, result.generation_run_id)
        if generation_run is None:
            raise HTTPException(status_code=500, detail="Rendered generation run disappeared unexpectedly.")
        return {
            "document_id": generation_run.document_id,
            "document_variant_id": document_version.document_variant_id,
            "document_version_id": result.document_version_id,
            "generation_run_id": result.generation_run_id,
            "generation_status": generation_run.status.value,
            "output_storage_root": document_version.storage_root,
            "output_storage_relative_path": document_version.storage_relative_path,
            "output_original_filename": document_version.original_filename,
            "checksum_sha256": result.checksum_sha256,
            "byte_size": result.byte_size,
            "scalar_replacement_mode": result.scalar_replacement_mode,
            "template_variant_key": result.template_variant_key,
            "replaced_bookmarks": list(result.replaced_bookmarks),
            "replaced_table_regions": list(result.replaced_table_regions),
            "replaced_parts": list(result.replaced_parts),
            "audit_event_id": audit_event.id,
        }

    def get_generation_run(self, session: Session, generation_run_id: str) -> dict[str, Any]:
        return self._serialize_generation_status(session, generation_run_id)

    def get_document(self, session: Session, document_id: str) -> dict[str, Any]:
        return self._serialize_document_detail(session, document_id)
