from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.document.c5e_certificate_detail_semantic_projection import (
    CERTIFICATE_DETAIL_FAMILY,
    CertificateDetailSemanticProjection,
    CertificateDetailSemanticProjectionError,
    project_certificate_detail_semantic_operations,
)
from backend.app.document.inspection_ke_hoach_kt_payload_input import (
    FAMILY_CODE as KHKT_FAMILY_CODE,
    InspectionKeHoachKtPayloadInput,
    InspectionKeHoachKtPayloadInputError,
    load_inspection_ke_hoach_kt_payload_input,
)
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
    DocumentPayloadBuildError,
    PayloadBuildInput,
    PayloadBuildResult,
    build_payload_envelope,
    load_default_payload_builder_registry,
)
from backend.app.document.persistence import PersistedGenerationState, prepare_generation_persistence
from backend.app.document.evaluation_scope_payload import (
    assert_no_c5e_scope_field_override,
    enrich_payload_result_with_c5e_scope,
    load_c5e_evaluation_scope_projection_input,
)
from backend.app.document.service_contract import (
    DocumentGenerationPlan,
    DocumentGenerationRequest,
    DocumentPayloadEnvelope,
    DocumentPayloadField,
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
    generated_at: datetime | None = None


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
    certificate_detail_projection: CertificateDetailSemanticProjection | None = None
    khkt_payload_input: InspectionKeHoachKtPayloadInput | None = None


@dataclass(frozen=True)
class AllocatedDocumentGeneration:
    prepared: PreparedDocumentGeneration
    output_allocation: OutputVersionAllocation


@dataclass(frozen=True)
class TemplateAwareAllocatedDocumentGeneration:
    allocated: AllocatedDocumentGeneration
    template_binary_requirement: TemplateBinaryRequirement
    template_render_ready: bool



def _khkt_payload_result(
    preparation_input: DocumentPreparationInput,
    payload_input: InspectionKeHoachKtPayloadInput,
) -> PayloadBuildResult:
    if preparation_input.payload_values:
        raise DocumentPayloadBuildError(
            "INSPECTION_KE_HOACH_KT business payload is DB-owned and must not be supplied by the caller."
        )
    values = {
        "Fulldate": payload_input.fulldate,
        "Tencoso": payload_input.site_name,
        "Diadiem": payload_input.province_name,
        "Diadiemx": payload_input.diadiemx,
        "Diachicoso": payload_input.site_address,
        "VKNx": payload_input.vknx,
        "QDKT": payload_input.decision_reference,
        "NgayQDKT": f"{payload_input.decision_date.day:02d}/{payload_input.decision_date.month:02d}/{payload_input.decision_date.year:04d}",
        "Daychuyen": payload_input.daychuyen,
        "GioiHanPvi": payload_input.gioi_han_pvi,
        "TieuchuanKT": payload_input.applicable_standard,
    }
    if payload_input.dossier_code is not None:
        values["HsDK"] = payload_input.dossier_code
    if payload_input.submitted_on is not None:
        values["NgaynopHsDK"] = (
            f"{payload_input.submitted_on.day:02d}/{payload_input.submitted_on.month:02d}/"
            f"{payload_input.submitted_on.year:04d}"
        )
    fields = tuple(
        DocumentPayloadField(
            field_name=name,
            value=value,
            source="KHKT.canonical_payload_input",
            is_sensitive=False,
        )
        for name, value in values.items()
    )
    return PayloadBuildResult(
        envelope=DocumentPayloadEnvelope(
            family_code=KHKT_FAMILY_CODE,
            fields=fields,
            source_procedures=("KHKT.canonical_payload_input",),
            notes="Canonical DB-backed KHKT payload; final physical targets are template-contract owned.",
        ),
        used_fields=tuple(values),
        missing_registry_fields=(),
        unexpected_input_fields=(),
    )


def _build_khkt_payload_input(
    session: Session,
    preparation_input: DocumentPreparationInput,
) -> InspectionKeHoachKtPayloadInput | None:
    if preparation_input.request.family_code != KHKT_FAMILY_CODE:
        return None
    if preparation_input.request.case_id is None:
        raise DocumentPayloadBuildError(
            "INSPECTION_KE_HOACH_KT canonical payload requires case_id."
        )
    if preparation_input.generated_at is None:
        raise DocumentPayloadBuildError(
            "INSPECTION_KE_HOACH_KT canonical payload requires a frozen generated_at timestamp."
        )
    try:
        payload_input = load_inspection_ke_hoach_kt_payload_input(
            session,
            case_id=preparation_input.request.case_id,
            generated_at=preparation_input.generated_at,
        )
    except InspectionKeHoachKtPayloadInputError as exc:
        raise DocumentPayloadBuildError(str(exc)) from exc

    requested_gxp_type = str(preparation_input.request.gxp_type or "").strip()
    if not requested_gxp_type:
        raise DocumentPayloadBuildError(
            "INSPECTION_KE_HOACH_KT requires request gxp_type to match the canonical case GxP."
        )
    if requested_gxp_type != payload_input.gxp_type:
        raise DocumentPayloadBuildError(
            "INSPECTION_KE_HOACH_KT request/case GxP mismatch: "
            f"request={requested_gxp_type!r}, case={payload_input.gxp_type!r}."
        )

    requested_language_code = str(preparation_input.request.language_code or "").strip()
    if requested_language_code != "vi":
        raise DocumentPayloadBuildError(
            "INSPECTION_KE_HOACH_KT language_code is backend-owned and must be 'vi'."
        )
    return payload_input


def build_document_payload_result(
    session: Session,
    preparation_input: DocumentPreparationInput,
    *,
    khkt_payload_input: InspectionKeHoachKtPayloadInput | None = None,
) -> PayloadBuildResult:
    """Build generic payload values, with KHKT owned by its canonical aggregate."""
    if preparation_input.request.family_code == KHKT_FAMILY_CODE:
        if khkt_payload_input is None:
            khkt_payload_input = _build_khkt_payload_input(session, preparation_input)
        if khkt_payload_input is None:  # pragma: no cover - guarded by family branch
            raise DocumentPayloadBuildError("KHKT canonical payload input was not built.")
        return _khkt_payload_result(preparation_input, khkt_payload_input)

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


def _build_certificate_detail_projection(
    session: Session,
    *,
    request: DocumentGenerationRequest,
) -> CertificateDetailSemanticProjection | None:
    """Build the production legacy Input_DC_to_CC semantic projection."""

    if request.family_code != CERTIFICATE_DETAIL_FAMILY:
        return None

    if request.case_id is None:
        raise DocumentPayloadBuildError(
            f"C.5e certificate-detail projection requires case_id for family_code={CERTIFICATE_DETAIL_FAMILY!r}."
        )

    projection_input = load_c5e_evaluation_scope_projection_input(
        session,
        case_id=request.case_id,
    )

    if request.gxp_type is not None and request.gxp_type != projection_input.gxp_type:
        raise DocumentPayloadBuildError(
            "C.5e certificate-detail request/case GxP mismatch: "
            f"request={request.gxp_type!r}, case={projection_input.gxp_type!r}."
        )

    try:
        return project_certificate_detail_semantic_operations(
            family_code=request.family_code,
            blocks=projection_input.blocks,
            taxonomy_nodes=projection_input.taxonomy_nodes,
            gxp_type=projection_input.gxp_type,
            eng_part=True,
        )
    except CertificateDetailSemanticProjectionError as exc:
        raise DocumentPayloadBuildError(
            f"C.5e certificate-detail semantic projection failed: {exc}"
        ) from exc


def prepare_document_generation_job(
    session: Session,
    preparation_input: DocumentPreparationInput,
) -> PreparedDocumentGeneration:
    khkt_payload_input = _build_khkt_payload_input(session, preparation_input)
    payload_result = build_document_payload_result(
        session,
        preparation_input,
        khkt_payload_input=khkt_payload_input,
    )
    registry = load_default_registry()
    generation_plan = plan_document_generation(
        registry,
        preparation_input.request,
        payload_result.envelope,
    )
    certificate_detail_projection = _build_certificate_detail_projection(
        session,
        request=preparation_input.request,
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
        certificate_detail_projection=certificate_detail_projection,
        khkt_payload_input=khkt_payload_input,
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
