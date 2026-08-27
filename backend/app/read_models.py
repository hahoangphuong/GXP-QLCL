from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel
from typing import Literal


class CompanyRead(BaseModel):
    id: str
    legacy_company_id: int | None
    legal_name: str
    short_name: str | None


class SiteRead(BaseModel):
    id: str
    legacy_site_id: int | None
    company_id: str
    site_name: str
    province_name: str | None


class CaseRead(BaseModel):
    id: str
    legacy_inspection_id: int | None
    legacy_inspection_code: str | None
    site_id: str
    gxp_type: str
    state: str


class CompanyDetailRead(BaseModel):
    id: str
    legacy_company_id: int | None
    legal_name: str
    english_name: str | None
    short_name: str | None
    legal_address: str | None
    legal_address_en: str | None
    is_inactive: bool


class SiteDetailRead(BaseModel):
    id: str
    legacy_site_id: int | None
    company_id: str
    site_name: str
    site_name_en: str | None
    site_address: str | None
    site_address_en: str | None
    province_name: str | None
    short_name: str | None


class CaseDetailRead(BaseModel):
    id: str
    legacy_inspection_id: int | None
    legacy_inspection_code: str | None
    site_id: str
    gxp_type: str
    scope_code: str | None
    applicable_standard: str | None
    inspection_type: str | None
    state: str
    opened_year: int | None
    row_version: int


class DashboardQueueItemRead(BaseModel):
    case_id: str
    site_id: str
    facility_name: str
    company_name: str
    gxp_type: str
    state: str
    reference_code: str | None
    opened_year: int | None


class DashboardSummaryRead(BaseModel):
    total_facilities: int
    total_cases: int
    active_cases: int
    waiting_inspection: int
    waiting_certificate_decision: int
    active_certificates: int
    expiring_certificates_90_days: int
    incomplete_changes: int
    queue: list[DashboardQueueItemRead]


class FacilitySearchResultRead(BaseModel):
    result_key: str
    site_id: str
    legacy_site_id: int | None
    facility_code: str | None
    context_code: str | None
    result_grain: Literal["facility", "production_line"]
    gxp_type: str | None
    line_code: str | None
    facility_name: str
    company_name: str
    gxp_types: list[str]
    certificate_scope_summary: str | None
    province_name: str | None
    last_inspection_code: str | None
    current_state: str | None
    current_certificate_number: str | None
    current_certificate_expiry: date | None


class FacilityWorkspaceSummaryRead(BaseModel):
    context_key: str
    site_id: str
    legacy_site_id: int | None
    facility_code: str | None
    context_code: str | None
    context_grain: Literal["facility", "production_line"]
    selected_line_code: str | None
    facility_name: str
    company_name: str
    address: str | None
    province_name: str | None
    gxp_types: list[str]
    selected_gxp_type: str | None
    current_state: str | None
    primary_standard: str | None
    current_certificate_number: str | None
    current_certificate_expiry: date | None
    certificate_scope_summary: str | None


class FacilityHistoryItemRead(BaseModel):
    id: str
    source_type: Literal["case", "change_request"]
    reference_code: str | None
    event_type: str
    gxp_type: str | None
    standard: str | None
    occurred_on: date | None
    state: str


class FacilityWorkspaceRead(BaseModel):
    summary: FacilityWorkspaceSummaryRead
    history: list[FacilityHistoryItemRead]


class CaseTransitionRequest(BaseModel):
    target_state: str
    expected_version: int
    reason: str | None = None


class CaseTransitionRead(BaseModel):
    case_id: str
    previous_state: str
    current_state: str
    row_version: int
    audit_event_id: str
    inspection_event_id: str | None


class CaseApplicationUpsertRequest(BaseModel):
    expected_version: int | None = None
    submitted_on: datetime | None = None
    dossier_code: str | None = None
    dossier_reference: str | None = None
    applicant_name: str | None = None
    reason: str | None = None


class CaseApplicationRead(BaseModel):
    case_id: str
    row_version: int
    submitted_on: datetime | None
    dossier_code: str | None
    dossier_reference: str | None
    applicant_name: str | None
    audit_event_id: str
    inspection_event_id: str | None


class CaseAssessmentUpsertRequest(BaseModel):
    expected_version: int | None = None
    assessed_on: datetime | None = None
    assessor_name: str | None = None
    assessment_result: str | None = None
    notes: str | None = None
    reason: str | None = None


class CaseAssessmentRead(BaseModel):
    case_id: str
    row_version: int
    assessed_on: datetime | None
    assessor_name: str | None
    assessment_result: str | None
    notes: str | None
    audit_event_id: str
    inspection_event_id: str | None


class InspectionPlanUpsertRequest(BaseModel):
    expected_version: int | None = None
    plan_start_on: date | None = None
    plan_end_on: date | None = None
    planning_sheet_name: str | None = None
    decision_document_hint: str | None = None
    reason: str | None = None


class InspectionPlanRead(BaseModel):
    case_id: str
    row_version: int
    plan_start_on: date | None
    plan_end_on: date | None
    planning_sheet_name: str | None
    decision_document_hint: str | None
    audit_event_id: str
    inspection_event_id: str | None


class InspectionOutcomeUpsertRequest(BaseModel):
    expected_version: int | None = None
    inspected_on: date | None = None
    inspected_to_on: date | None = None
    decision_reference: str | None = None
    bbkt_reference: str | None = None
    outcome_result: str | None = None
    reason: str | None = None


class InspectionOutcomeRead(BaseModel):
    case_id: str
    row_version: int
    inspected_on: date | None
    inspected_to_on: date | None
    decision_reference: str | None
    bbkt_reference: str | None
    outcome_result: str | None
    audit_event_id: str
    inspection_event_id: str | None


class CapaCycleCreateRequest(BaseModel):
    expected_case_version: int | None = None
    requested_on: date | None = None
    notes: str | None = None
    reason: str | None = None


class CapaCycleUpdateRequest(BaseModel):
    expected_version: int
    requested_on: date | None = None
    notes: str | None = None
    reason: str | None = None


class CapaCycleSubmitRequest(BaseModel):
    expected_version: int
    submitted_on: date
    notes: str | None = None
    reason: str | None = None


class CapaCycleAssessRequest(BaseModel):
    expected_version: int
    assessed_on: date
    assessor_name: str | None = None
    result: str
    notes: str | None = None
    reason: str | None = None


class CapaCycleRead(BaseModel):
    capa_cycle_id: str
    case_id: str
    row_version: int
    round_no: int
    requested_on: date | None
    submitted_on: date | None
    assessed_on: date | None
    assessor_user_id: str | None
    assessor_name: str | None
    result: str | None
    status: str
    notes: str | None
    audit_event_id: str | None = None


class InspectionTeamMemberUpsertItem(BaseModel):
    inspector_profile_id: str | None = None
    person_id: str | None = None
    role_label: str | None = None
    sort_order: int = 0


class InspectionTeamUpsertRequest(BaseModel):
    expected_version: int | None = None
    display_text: str | None = None
    members: list[InspectionTeamMemberUpsertItem]
    reason: str | None = None


class InspectionTeamMemberRead(BaseModel):
    id: str
    inspector_profile_id: str | None
    person_id: str | None
    role_label: str | None
    sort_order: int


class InspectionTeamRead(BaseModel):
    case_id: str
    team_id: str
    row_version: int
    display_text: str | None
    members: list[InspectionTeamMemberRead]
    audit_event_id: str


class CertificateScopeUpsertItem(BaseModel):
    scope_key: str | None = None
    scope_text: str
    language_code: str = "vi"
    sort_order: int = 0


class CertificateIssueRequest(BaseModel):
    case_id: str | None = None
    certificate_type: str
    issuance_basis: str = "inspection_case"
    certificate_number: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    scopes: list[CertificateScopeUpsertItem] = []
    reason: str | None = None


class CertificateLatestVersionUpsertRequest(BaseModel):
    expected_version: int
    certificate_number: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    scopes: list[CertificateScopeUpsertItem] = []
    reason: str | None = None


class CertificatePromoteCurrentRequest(BaseModel):
    expected_version: int
    reason: str | None = None


class CertificateScopeRead(BaseModel):
    id: str
    scope_key: str | None
    scope_text: str
    language_code: str
    sort_order: int


class CertificateMutationRead(BaseModel):
    certificate_id: str
    row_version: int
    site_id: str
    case_id: str | None
    certificate_type: str
    issuance_basis: str
    latest_flag: bool
    latest_version_id: str
    latest_version_no: int
    certificate_number: str | None
    issue_date: date | None
    expiry_date: date | None
    scopes: list[CertificateScopeRead]
    audit_event_id: str
    inspection_event_id: str | None


class BusinessEligibilityLinkUpsertItem(BaseModel):
    certificate_id: str
    link_role: str = "source_certificate"


class BusinessEligibilityIssueRequest(BaseModel):
    certificate_number: str | None = None
    issued_on: date | None = None
    expires_on: date | None = None
    professional_responsible_person_name: str | None = None
    notes: str | None = None
    linked_certificates: list[BusinessEligibilityLinkUpsertItem] = []
    reason: str | None = None


class BusinessEligibilityLatestVersionUpsertRequest(BaseModel):
    expected_version: int
    certificate_number: str | None = None
    issued_on: date | None = None
    expires_on: date | None = None
    professional_responsible_person_name: str | None = None
    notes: str | None = None
    linked_certificates: list[BusinessEligibilityLinkUpsertItem] = []
    reason: str | None = None


class BusinessEligibilityPromoteCurrentRequest(BaseModel):
    expected_version: int
    reason: str | None = None


class BusinessEligibilityLinkRead(BaseModel):
    id: str
    certificate_id: str
    link_role: str


class BusinessEligibilityMutationRead(BaseModel):
    business_eligibility_certificate_id: str
    row_version: int
    site_id: str
    company_id: str
    latest_flag: bool
    latest_version_id: str
    latest_version_no: int
    certificate_number: str | None
    issued_on: date | None
    expires_on: date | None
    professional_responsible_person_name: str | None
    notes: str | None
    linked_certificates: list[BusinessEligibilityLinkRead]
    audit_event_id: str
    inspection_event_id: str | None


class DocumentGenerationPrepareRequest(BaseModel):
    family_code: str
    case_id: str | None = None
    capa_cycle_id: str | None = None
    certificate_id: str | None = None
    business_eligibility_certificate_id: str | None = None
    change_request_id: str | None = None
    gxp_type: str | None = None
    legacy_mode: str | None = None
    storage_scope: str | None = None
    language_code: str = "vi"
    idempotency_key: str | None = None
    payload: dict[str, str]
    payload_notes: str | None = None
    strict_payload: bool = True


class DocumentTemplateRenderRequest(DocumentGenerationPrepareRequest):
    output_filename: str


class DocumentTemplateSelectionRead(BaseModel):
    family_code: str
    logical_name: str
    template_pattern: str
    source_application: str
    storage_scope: str
    host_procedure: str
    population_procedures: list[str]
    notes: str | None


class DocumentSourceDependencyRead(BaseModel):
    source_family_code: str
    dependency_type: str
    required_bookmarks: list[str]
    condition: str | None


class DocumentSourceBinaryRequirementRead(BaseModel):
    source_document_id: str
    source_document_version_id: str | None
    source_family_code: str
    readiness_status: str
    detail: str
    storage_root: str | None
    folder_relative_path: str | None
    exact_storage_root: str | None
    exact_storage_relative_path: str | None
    original_filename: str | None
    required_bookmarks: list[str]
    legacy_filename_prefix_hints: list[str]


class DocumentTemplateReadinessRead(BaseModel):
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


class DocumentPreparationRead(BaseModel):
    document_id: str
    document_variant_id: str
    generation_run_id: str
    generation_status: str
    reused_generation_run: bool
    render_ready: bool
    template_render_ready: bool
    blocked_reasons: list[str]
    selected_template: DocumentTemplateSelectionRead
    payload_used_fields: list[str]
    missing_registry_fields: list[str]
    unexpected_input_fields: list[str]
    source_dependencies: list[DocumentSourceDependencyRead]
    source_binary_requirements: list[DocumentSourceBinaryRequirementRead]
    template_readiness: DocumentTemplateReadinessRead
    template_definition_id: str | None
    template_binding_id: str | None
    audit_event_id: str


class DocumentRenderRead(BaseModel):
    document_id: str
    document_variant_id: str
    document_version_id: str
    generation_run_id: str
    generation_status: str
    output_storage_root: str
    output_storage_relative_path: str
    output_original_filename: str
    checksum_sha256: str
    byte_size: int
    scalar_replacement_mode: str
    template_variant_key: str | None
    replaced_bookmarks: list[str]
    replaced_table_regions: list[str]
    replaced_parts: list[str]
    audit_event_id: str


class DocumentVersionRead(BaseModel):
    id: str
    version_no: int
    storage_binding_id: str | None
    storage_root: str | None
    storage_relative_path: str | None
    original_filename: str | None
    checksum_sha256: str | None
    is_current: bool
    issued_on: datetime | None


class DocumentVariantRead(BaseModel):
    id: str
    variant_type: str
    language_code: str
    is_active: bool
    versions: list[DocumentVersionRead]


class DocumentGenerationRunStatusRead(BaseModel):
    generation_run_id: str
    document_id: str
    template_binding_id: str | None
    template_definition_id: str | None
    output_document_version_id: str | None
    status: str
    source_application: str | None
    requested_by_user_id: str | None
    input_payload_redacted: dict[str, str] | None
    error_summary: str | None
    idempotency_key: str | None
    source_dependencies: list[DocumentSourceDependencyRead]


class DocumentDetailRead(BaseModel):
    document_id: str
    family_code: str
    document_type_code: str
    title: str | None
    legacy_entity_type: str | None
    case_id: str | None
    capa_cycle_id: str | None
    certificate_id: str | None
    business_eligibility_certificate_id: str | None
    change_request_id: str | None
    variants: list[DocumentVariantRead]
    generation_runs: list[DocumentGenerationRunStatusRead]


class StorageBindingRead(BaseModel):
    case_id: str | None
    year: int | None
    site_legacy_id: int | None
    inspection_legacy_code: str | None
    relative_path: str
    observed_folder_label: str | None
    storage_class: str


class InspectionFolderLookupRead(BaseModel):
    status: str
    source: Literal["binding", "live_resolution"]
    relative_path: str | None
    candidate_count: int
    detail: str | None
    storage_class: str
    binding: StorageBindingRead | None


class DkkdFolderLookupRead(BaseModel):
    status: str
    source: Literal["live_resolution"]
    relative_path: str | None
    candidate_count: int
    detail: str | None
    storage_class: str
