from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.document.output_version import (
    OutputVersionAllocation,
    allocate_output_document_version,
)
from backend.app.document.docx_render import DocxRenderResult, render_baseline_docx_and_finalize
from backend.app.document.docx_template_render import (
    DocxTemplateRenderResult,
    render_template_aware_docx_and_finalize,
)
from backend.app.document.template_binary import TemplateBinaryRequirement, build_template_binary_requirement
from backend.app.document.payload_builders import (
    PayloadBuildInput,
    PayloadBuildResult,
    build_payload_envelope,
    load_default_payload_builder_registry,
)
from backend.app.document.persistence import PersistedGenerationState, prepare_generation_persistence
from backend.app.document.evaluation_scope_payload import (
    assert_no_c5e_scope_field_override,
    enrich_payload_result_with_c5e_scope,
)
from backend.app.document.service_contract import (
    DocumentGenerationPlan,
    DocumentGenerationRequest,
    load_default_registry,
    plan_document_generation,
)
from backend.app.document.source_binary_contract import SourceBinaryRequirement, build_source_binary_requirements
from backend.app.document.source_resolver_contract import (
    SourceDocumentLookupRequest,
    SourceDocumentResolution,
    build_source_lookup_requests,
)
from backend.app.document.source_resolver_db import resolve_source_document_from_db
from backend.app.storage.local import LocalStorageService


@dataclass(frozen=True)
class DocumentPreparationInput:
    request: DocumentGenerationRequest
    payload_values: dict[str, str]
    table_regions: tuple["TableRegionRenderInput", ...] = ()
    payload_notes: str | None = None
    strict_payload: bool = True
    copy_pt: bool = False


@dataclass(frozen=True)
class TableRegionRenderInput:
    region_bookmark_name: str
    rows: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class PreparedDocumentGeneration:
    payload_result: PayloadBuildResult
    generation_plan: DocumentGenerationPlan
    table_regions: tuple["TableRegionRenderInput", ...]
    source_lookup_requests: tuple[SourceDocumentLookupRequest, ...]
    source_resolutions: tuple[SourceDocumentResolution, ...]
    source_binary_requirements: tuple[SourceBinaryRequirement, ...]
    persisted_state: PersistedGenerationState
    render_ready: bool


@dataclass(frozen=True)
class AllocatedDocumentGeneration:
    prepared: PreparedDocumentGeneration
    output_allocation: OutputVersionAllocation


@dataclass(frozen=True)
class TemplateAwareAllocatedDocumentGeneration:
    allocated: AllocatedDocumentGeneration
    template_binary_requirement: TemplateBinaryRequirement
    template_render_ready: bool


def build_document_payload_result(
    session: Session,
    preparation_input: DocumentPreparationInput,
) -> PayloadBuildResult:
    """Build generic payload values, then apply C.5e scope ownership."""
    payload_registry = load_default_payload_builder_registry()
    assert_no_c5e_scope_field_override(
        family_code=preparation_input.request.family_code,
        values=preparation_input.payload_values,
    )
    payload_result = build_payload_envelope(
        payload_registry,
        PayloadBuildInput(
            family_code=preparation_input.request.family_code,
            values=preparation_input.payload_values,
            notes=preparation_input.payload_notes,
            strict=preparation_input.strict_payload,
        ),
    )
    return enrich_payload_result_with_c5e_scope(
        session,
        family_code=preparation_input.request.family_code,
        case_id=preparation_input.request.case_id,
        copy_pt=preparation_input.copy_pt,
        payload_result=payload_result,
    )


def prepare_document_generation_job(
    session: Session,
    preparation_input: DocumentPreparationInput,
) -> PreparedDocumentGeneration:
    payload_result = build_document_payload_result(session, preparation_input)
    registry = load_default_registry()
    generation_plan = plan_document_generation(
        registry,
        preparation_input.request,
        payload_result.envelope,
    )
    source_lookup_requests = build_source_lookup_requests(generation_plan)
    source_resolutions = tuple(resolve_source_document_from_db(session, request) for request in source_lookup_requests)
    source_binary_requirements = build_source_binary_requirements(session, source_resolutions)
    persisted_state = prepare_generation_persistence(
        session,
        generation_plan,
        source_resolutions=source_resolutions,
    )
    render_ready = all(requirement.readiness_status == "direct_stream_ready" for requirement in source_binary_requirements)
    if not source_binary_requirements:
        render_ready = True
    return PreparedDocumentGeneration(
        payload_result=payload_result,
        generation_plan=generation_plan,
        table_regions=preparation_input.table_regions,
        source_lookup_requests=source_lookup_requests,
        source_resolutions=source_resolutions,
        source_binary_requirements=source_binary_requirements,
        persisted_state=persisted_state,
        render_ready=render_ready,
    )


def prepare_and_allocate_document_generation_job(
    session: Session,
    storage: LocalStorageService,
    preparation_input: DocumentPreparationInput,
    *,
    output_filename: str,
) -> AllocatedDocumentGeneration:
    prepared = prepare_document_generation_job(session, preparation_input)
    output_allocation = allocate_output_document_version(
        session,
        storage,
        prepared,
        output_filename=output_filename,
    )
    return AllocatedDocumentGeneration(
        prepared=prepared,
        output_allocation=output_allocation,
    )


def prepare_template_aware_docx_generation(
    session: Session,
    storage: LocalStorageService,
    preparation_input: DocumentPreparationInput,
    *,
    output_filename: str,
) -> TemplateAwareAllocatedDocumentGeneration:
    allocated = prepare_and_allocate_document_generation_job(
        session,
        storage,
        preparation_input,
        output_filename=output_filename,
    )
    template_binary_requirement = build_template_binary_requirement(session, allocated)
    template_render_ready = (
        allocated.prepared.generation_plan.template.source_application == "Word"
        and allocated.prepared.render_ready
        and template_binary_requirement.readiness_status == "direct_stream_ready"
    )
    return TemplateAwareAllocatedDocumentGeneration(
        allocated=allocated,
        template_binary_requirement=template_binary_requirement,
        template_render_ready=template_render_ready,
    )


def render_baseline_docx_generation(
    session: Session,
    storage: LocalStorageService,
    preparation_input: DocumentPreparationInput,
    *,
    output_filename: str,
) -> DocxRenderResult:
    allocated = prepare_and_allocate_document_generation_job(
        session,
        storage,
        preparation_input,
        output_filename=output_filename,
    )
    return render_baseline_docx_and_finalize(session, storage, allocated)


def render_template_aware_docx_generation(
    session: Session,
    storage: LocalStorageService,
    preparation_input: DocumentPreparationInput,
    *,
    output_filename: str,
) -> DocxTemplateRenderResult:
    prepared = prepare_template_aware_docx_generation(
        session,
        storage,
        preparation_input,
        output_filename=output_filename,
    )
    return render_template_aware_docx_and_finalize(session, storage, prepared)
