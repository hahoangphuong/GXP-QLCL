from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from backend.app.db.enums import DocumentGenerationStatus, DocumentVariantType, LegacyEntityType
from backend.app.db.models.phase1 import (
    CapaCycle,
    Document,
    DocumentGenerationRun,
    DocumentSourceDependency,
    DocumentVariant,
    TemplateBinding,
    TemplateDefinition,
)
from backend.app.document.seed_contract import normalize_template_name
from backend.app.document.service_contract import (
    DocumentGenerationPlan,
    DocumentGenerationRequest,
)
from backend.app.document.source_resolver_contract import SourceDocumentResolution


class DocumentPersistenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class PersistedGenerationState:
    document_id: str
    document_variant_id: str
    generation_run_id: str
    template_definition_id: str | None
    template_binding_id: str | None
    source_dependency_ids: tuple[str, ...]
    reused_generation_run: bool = False


def _variant_type_for_source_application(source_application: str) -> DocumentVariantType:
    if source_application == "Excel":
        return DocumentVariantType.EDITABLE_XLSX
    return DocumentVariantType.EDITABLE_DOCX


def _legacy_entity_type_for_request(request: DocumentGenerationRequest) -> LegacyEntityType | None:
    if request.case_id:
        return LegacyEntityType.CASE
    if request.certificate_id:
        return LegacyEntityType.CERTIFICATE
    if request.business_eligibility_certificate_id:
        return LegacyEntityType.BUSINESS_ELIGIBILITY
    if request.change_request_id:
        return LegacyEntityType.CHANGE_REQUEST
    return None


def _document_parent_filters(request: DocumentGenerationRequest) -> list:
    return [
        Document.case_id == request.case_id,
        Document.capa_cycle_id == request.capa_cycle_id,
        Document.certificate_id == request.certificate_id,
        Document.business_eligibility_certificate_id == request.business_eligibility_certificate_id,
        Document.change_request_id == request.change_request_id,
    ]


def _require_parent_link(request: DocumentGenerationRequest) -> None:
    if not any(
        [
            request.case_id,
            request.capa_cycle_id,
            request.certificate_id,
            request.business_eligibility_certificate_id,
            request.change_request_id,
        ]
    ):
        raise DocumentPersistenceError("Document generation request must include at least one parent link")


def _validate_capa_document_link(session: Session, request: DocumentGenerationRequest) -> None:
    if not request.family_code.startswith("INSPECTION_CAPA_"):
        return
    if not request.capa_cycle_id:
        raise DocumentPersistenceError("CAPA document generation requires capa_cycle_id.")
    capa_cycle = session.get(CapaCycle, request.capa_cycle_id)
    if capa_cycle is None:
        raise DocumentPersistenceError(f"CapaCycle {request.capa_cycle_id!r} was not found.")
    if request.case_id is not None and capa_cycle.case_id != request.case_id:
        raise DocumentPersistenceError("CAPA document case/cycle mismatch.")


def _find_existing_document(session: Session, request: DocumentGenerationRequest) -> Document | None:
    stmt: Select[tuple[Document]] = select(Document).where(
        Document.family_code == request.family_code,
        *_document_parent_filters(request),
    )
    return session.execute(stmt).scalar_one_or_none()


def ensure_document(session: Session, plan: DocumentGenerationPlan) -> Document:
    _require_parent_link(plan.request)
    _validate_capa_document_link(session, plan.request)
    existing = _find_existing_document(session, plan.request)
    if existing is not None:
        return existing
    document = Document(
        legacy_entity_type=_legacy_entity_type_for_request(plan.request),
        family_code=plan.template.family_code,
        document_type_code=plan.template.family_code.lower(),
        title=plan.template.logical_name,
        case_id=plan.request.case_id,
        capa_cycle_id=plan.request.capa_cycle_id,
        certificate_id=plan.request.certificate_id,
        business_eligibility_certificate_id=plan.request.business_eligibility_certificate_id,
        change_request_id=plan.request.change_request_id,
    )
    session.add(document)
    session.flush()
    return document


def ensure_document_variant(session: Session, document: Document, plan: DocumentGenerationPlan) -> DocumentVariant:
    variant_type = _variant_type_for_source_application(plan.template.source_application)
    stmt: Select[tuple[DocumentVariant]] = select(DocumentVariant).where(
        DocumentVariant.document_id == document.id,
        DocumentVariant.variant_type == variant_type,
        DocumentVariant.language_code == plan.request.language_code,
    )
    existing = session.execute(stmt).scalar_one_or_none()
    if existing is not None:
        return existing
    variant = DocumentVariant(
        document_id=document.id,
        variant_type=variant_type,
        language_code=plan.request.language_code,
        is_active=True,
    )
    session.add(variant)
    session.flush()
    return variant


def _lookup_template_definition(session: Session, plan: DocumentGenerationPlan) -> TemplateDefinition | None:
    stmt: Select[tuple[TemplateDefinition]] = select(TemplateDefinition).where(
        TemplateDefinition.family_code == plan.template.family_code,
        TemplateDefinition.template_name == normalize_template_name(plan.template.template_pattern),
        TemplateDefinition.storage_scope == plan.template.storage_scope,
        TemplateDefinition.source_application == plan.template.source_application,
        TemplateDefinition.is_active.is_(True),
    )
    matches = list(session.execute(stmt).scalars())
    if len(matches) > 1:
        raise DocumentPersistenceError(
            f"Ambiguous template_definition rows for family_code={plan.template.family_code!r}"
        )
    return matches[0] if matches else None


def _lookup_template_binding(
    session: Session,
    plan: DocumentGenerationPlan,
    template_definition: TemplateDefinition | None,
) -> TemplateBinding | None:
    if template_definition is None:
        return None
    stmt: Select[tuple[TemplateBinding]] = select(TemplateBinding).where(
        TemplateBinding.family_code == plan.template.family_code,
        TemplateBinding.template_definition_id == template_definition.id,
        TemplateBinding.storage_scope == plan.template.storage_scope,
        TemplateBinding.is_active.is_(True),
    )
    if plan.request.gxp_type is None:
        stmt = stmt.where(TemplateBinding.gxp_type.is_(None))
    else:
        stmt = stmt.where(
            or_(TemplateBinding.gxp_type == plan.request.gxp_type, TemplateBinding.gxp_type == "{GP}")
        )
    if plan.request.legacy_mode is None:
        stmt = stmt.where(TemplateBinding.legacy_mode.is_(None))
    else:
        stmt = stmt.where(TemplateBinding.legacy_mode == plan.request.legacy_mode)
    matches = list(session.execute(stmt).scalars())
    if len(matches) > 1:
        raise DocumentPersistenceError(
            f"Ambiguous template_binding rows for family_code={plan.template.family_code!r}"
        )
    return matches[0] if matches else None


def _existing_generation_run(session: Session, idempotency_key: str | None) -> DocumentGenerationRun | None:
    if not idempotency_key:
        return None
    stmt: Select[tuple[DocumentGenerationRun]] = select(DocumentGenerationRun).where(
        DocumentGenerationRun.idempotency_key == idempotency_key
    )
    return session.execute(stmt).scalar_one_or_none()


def create_document_generation_run(
    session: Session,
    plan: DocumentGenerationPlan,
    document: Document,
    template_definition: TemplateDefinition | None,
    template_binding: TemplateBinding | None,
) -> tuple[DocumentGenerationRun, bool]:
    existing = _existing_generation_run(session, plan.request.idempotency_key)
    if existing is not None:
        return existing, True
    generation_run = DocumentGenerationRun(
        document_id=document.id,
        template_binding_id=template_binding.id if template_binding else None,
        template_definition_id=template_definition.id if template_definition else None,
        output_document_version_id=None,
        status=DocumentGenerationStatus.PENDING,
        source_application=plan.template.source_application,
        requested_by_user_id=plan.request.requested_by_user_id,
        input_payload_redacted=json.dumps(plan.payload.redacted_payload(), ensure_ascii=False, sort_keys=True),
        error_summary=None,
        idempotency_key=plan.request.idempotency_key,
    )
    session.add(generation_run)
    session.flush()
    return generation_run, False


def persist_source_dependencies(
    session: Session,
    generation_run: DocumentGenerationRun,
    source_resolutions: tuple[SourceDocumentResolution, ...],
) -> tuple[str, ...]:
    dependency_ids: list[str] = []
    for resolution in source_resolutions:
        record = DocumentSourceDependency(
            document_generation_run_id=generation_run.id,
            source_document_id=resolution.candidate.document_id,
            source_document_version_id=resolution.candidate.document_version_id,
            dependency_type=resolution.request.dependency_type,
            source_bookmarks=json.dumps(list(resolution.request.required_bookmarks), ensure_ascii=False),
            notes=None,
        )
        session.add(record)
        session.flush()
        dependency_ids.append(record.id)
    return tuple(dependency_ids)


def prepare_generation_persistence(
    session: Session,
    plan: DocumentGenerationPlan,
    source_resolutions: tuple[SourceDocumentResolution, ...] = (),
) -> PersistedGenerationState:
    document = ensure_document(session, plan)
    variant = ensure_document_variant(session, document, plan)
    template_definition = _lookup_template_definition(session, plan)
    template_binding = _lookup_template_binding(session, plan, template_definition)
    generation_run, reused = create_document_generation_run(
        session,
        plan,
        document,
        template_definition,
        template_binding,
    )
    dependency_ids: tuple[str, ...] = ()
    if not reused and source_resolutions:
        dependency_ids = persist_source_dependencies(session, generation_run, source_resolutions)
    return PersistedGenerationState(
        document_id=document.id,
        document_variant_id=variant.id,
        generation_run_id=generation_run.id,
        template_definition_id=template_definition.id if template_definition else None,
        template_binding_id=template_binding.id if template_binding else None,
        source_dependency_ids=dependency_ids,
        reused_generation_run=reused,
    )
