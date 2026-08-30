export type AppStatus = {
  deployment_platform: string;
  frontend_topology: string;
  auth_mode: string;
  auth: {
    mode: string;
    oidc_client_id: string | null;
    allowed_email_domain: string | null;
  };
  deployment: {
    git_sha: string | null;
    git_short_sha: string | null;
    branch: string | null;
    image_uri: string | null;
    deployed_at_utc: string | null;
    cloud_run_service_name: string | null;
    db_name: string | null;
    db_user: string | null;
  };
  phases: {
    phase3_status: string | null;
    phase4_status: string | null;
    phase5_status: string | null;
    phase6_status: string | null;
    phase7_status: string | null;
    current_projection_conflicts_status: string | null;
    current_projection_conflicts_unresolved_count: number | null;
  };
};

export type Company = {
  id: string;
  legacy_company_id: number | null;
  legal_name: string;
  short_name: string | null;
};

export type Site = {
  id: string;
  legacy_site_id: number | null;
  company_id: string;
  site_name: string;
  province_name: string | null;
};

export type CaseListItem = {
  id: string;
  legacy_inspection_id: number | null;
  legacy_inspection_code: string | null;
  site_id: string;
  gxp_type: string;
  state: string;
};

export type CaseDetail = {
  id: string;
  legacy_inspection_id: number | null;
  legacy_inspection_code: string | null;
  site_id: string;
  gxp_type: string;
  scope_code: string | null;
  applicable_standard: string | null;
  inspection_type: string | null;
  state: string;
  opened_year: number | null;
};

export type InspectionCaseCreateRequest = {
  gxp_type: string;
  line_code: string | null;
  inspection_type: string;
  applicable_standard: string | null;
  reason?: string | null;
};

export type InspectionCaseCreateResponse = {
  case_id: string;
  site_id: string;
  gxp_type: string;
  line_code: string | null;
  inspection_type: string;
  applicable_standard: string | null;
  state: string;
  row_version: number;
  legacy_inspection_id: number | null;
  legacy_inspection_code: string | null;
  audit_event_id: string;
};

export type DashboardQueueItem = {
  case_id: string;
  site_id: string;
  facility_name: string;
  company_name: string;
  gxp_type: string;
  state: string;
  reference_code: string | null;
  opened_year: number | null;
};

export type DashboardSummary = {
  total_facilities: number;
  total_cases: number;
  active_cases: number;
  waiting_inspection: number;
  waiting_certificate_decision: number;
  active_certificates: number;
  expiring_certificates_90_days: number;
  incomplete_changes: number;
  queue: DashboardQueueItem[];
};

export type FacilitySearchResult = {
  result_key: string;
  site_id: string;
  legacy_site_id: number | null;
  facility_code: string | null;
  context_code: string | null;
  result_grain: "facility" | "production_line";
  gxp_type: string | null;
  line_code: string | null;
  facility_name: string;
  company_name: string;
  gxp_types: string[];
  certificate_scope_summary: string | null;
  province_name: string | null;
  last_inspection_on: string | null;
  current_state: string | null;
  current_certificate_number: string | null;
  current_certificate_expiry: string | null;
};

export type FacilitySearchPage = {
  items: FacilitySearchResult[];
  total_count: number;
  offset: number;
  limit: number;
};

export type FacilityWorkspaceSummary = {
  context_key: string;
  site_id: string;
  legacy_site_id: number | null;
  facility_code: string | null;
  context_code: string | null;
  context_grain: "facility" | "production_line";
  selected_line_code: string | null;
  facility_name: string;
  company_name: string;
  company_legal_address: string | null;
  company_leader: string | null;
  company_foreign_investment: string | null;
  assigned_specialist: string | null;
  address: string | null;
  contact_information: string | null;
  professional_responsible_person: string | null;
  quality_assurance_person: string | null;
  facility_current_status: string | null;
  province_name: string | null;
  gxp_types: string[];
  selected_gxp_type: string | null;
  current_state: string | null;
  primary_standard: string | null;
  current_certificate_number: string | null;
  current_certificate_issue_date: string | null;
  current_certificate_expiry: string | null;
  current_certificate_standard: string | null;
  current_certificate_status: string | null;
  certificate_scope_summary: string | null;
};

export type FacilityHistoryItem = {
  id: string;
  source_type: "case" | "change_request";
  reference_code: string | null;
  event_type: string;
  gxp_type: string | null;
  standard: string | null;
  occurred_on: string | null;
  state: string;
};

export type FacilityWorkspace = {
  summary: FacilityWorkspaceSummary;
  history: FacilityHistoryItem[];
  action_readiness: WorkspaceActionReadiness[];
};

export type CaseWorkspaceSummary = {
  id: string;
  legacy_inspection_id: number | null;
  legacy_inspection_code: string | null;
  site_id: string;
  facility_name: string;
  company_name: string;
  gxp_type: string;
  scope_code: string | null;
  applicable_standard: string | null;
  inspection_type: string | null;
  state: string;
  opened_year: number | null;
};

export type CaseWorkspaceApplication = {
  submitted_on: string | null;
  dossier_code: string | null;
  dossier_reference: string | null;
  applicant_name: string | null;
  assigned_specialist: string | null;
  assigned_specialist_source: "company_master" | null;
};

export type CaseWorkspaceInspection = {
  decision_reference: string | null;
  decision_document_hint: string | null;
  plan_start_on: string | null;
  plan_end_on: string | null;
  planning_sheet_name: string | null;
  inspected_on: string | null;
  inspected_to_on: string | null;
  executed_on: string | null;
  bbkt_reference: string | null;
  outcome_result: string | null;
  team_display_text: string | null;
};

export type CaseWorkspaceRemediationCycle = {
  capa_cycle_id: string;
  round_no: number;
  requested_on: string | null;
  submitted_on: string | null;
  assessed_on: string | null;
  assessor_name: string | null;
  result: string | null;
  status: string;
  notes: string | null;
};

export type CaseWorkspaceRemediation = {
  cycles: CaseWorkspaceRemediationCycle[];
};

export type CaseWorkspaceProcessingEvent = {
  event_type: string;
  occurred_at: string | null;
  payload: string | null;
};

export type CaseWorkspaceProcessing = {
  assessed_on: string | null;
  assessor_name: string | null;
  assessment_result: string | null;
  notes: string | null;
  events: CaseWorkspaceProcessingEvent[];
};

export type WorkspaceActionReadiness = {
  action_key: string;
  label: string;
  readiness_status: string;
  detail: string;
  required_permissions: string[];
};

export type DocumentChecklistItem = {
  checklist_key: string;
  label: string;
  family_code: string | null;
  parent_scope: "case" | "capa_cycle" | "change_request";
  parent_id: string;
  status: "available" | "missing";
  document_id: string | null;
  document_type_code: string | null;
  title: string | null;
  original_filename: string | null;
  issued_on: string | null;
  available_variant_types: string[];
  detail_available: boolean;
};

export type DocumentChecklist = {
  items: DocumentChecklistItem[];
};

export type GxpCertificateListItem = {
  certificate_id: string;
  site_id: string;
  case_id: string | null;
  certificate_type: string;
  line_code: string | null;
  context_match_kind: "exact_line" | "facility_wide" | "site_wide";
  latest_flag: boolean;
  certificate_number: string | null;
  issue_date: string | null;
  expiry_date: string | null;
  applicable_standard: string | null;
  issuing_authority: string | null;
  status: string | null;
};

export type GxpCertificateList = {
  items: GxpCertificateListItem[];
};

export type GxpCertificateDetail = {
  certificate_id: string;
  site_id: string;
  case_id: string | null;
  certificate_type: string;
  line_code: string | null;
  issuance_basis: string;
  latest_flag: boolean;
  certificate_number: string | null;
  issue_date: string | null;
  expiry_date: string | null;
  applicable_standard: string | null;
  issuing_authority: string | null;
  status: string | null;
  facility_name: string;
  address: string | null;
  company_name: string;
  company_legal_address: string | null;
  scope_summary: string | null;
  limitation_text: string | null;
  source_description: string | null;
};

export type BusinessEligibilityBasisCertificate = {
  certificate_id: string;
  certificate_type: string;
  line_code: string | null;
  certificate_number: string | null;
  issue_date: string | null;
  link_role: string;
};

export type BusinessEligibilityListItem = {
  business_eligibility_certificate_id: string;
  site_id: string;
  company_id: string;
  latest_flag: boolean;
  certificate_number: string | null;
  issued_on: string | null;
  issuance_sequence_text: string | null;
  current_status_text: string | null;
};

export type BusinessEligibilityList = {
  items: BusinessEligibilityListItem[];
};

export type BusinessEligibilityDetail = {
  business_eligibility_certificate_id: string;
  site_id: string;
  company_id: string;
  latest_flag: boolean;
  certificate_number: string | null;
  issued_on: string | null;
  decision_reference: string | null;
  issuance_sequence_text: string | null;
  issuance_history_text: string | null;
  company_name: string;
  company_legal_address: string | null;
  facility_name: string;
  address: string | null;
  professional_responsible_person_name: string | null;
  quality_assurance_person_name: string | null;
  professional_qualification_text: string | null;
  professional_license_number: string | null;
  professional_license_issued_on: string | null;
  professional_license_issuer: string | null;
  responsible_license_issued_on: string | null;
  responsible_license_issuer: string | null;
  business_activity_text: string | null;
  current_status_text: string | null;
  handled_by_name: string | null;
  application_dossier_reference: string | null;
  replaces_certificate_number: string | null;
  replaced_by_certificate_number: string | null;
  linked_gxp_certificates: BusinessEligibilityBasisCertificate[];
};

export type CaseWorkspace = {
  case_summary: CaseWorkspaceSummary;
  application: CaseWorkspaceApplication;
  inspection: CaseWorkspaceInspection;
  remediation: CaseWorkspaceRemediation;
  processing: CaseWorkspaceProcessing;
  documents: DocumentChecklist;
  linked_gxp_certificates: GxpCertificateDetail[];
  linked_business_eligibility_certificates: BusinessEligibilityDetail[];
};

export type ChangeRequestWorkspaceDetail = {
  change_detail_id: string;
  legacy_change_detail_id: number | null;
  classification_id: number | null;
  classification_label: string | null;
  approval_status: string | null;
  old_value: string | null;
  new_value: string | null;
  note: string | null;
};

export type ChangeRequestWorkspace = {
  id: string;
  legacy_change_request_id: number | null;
  site_id: string;
  facility_name: string;
  company_name: string;
  scope_label: string | null;
  description: string | null;
  submitted_on: string | null;
  requester_name: string | null;
  state: string;
  handled_on: string | null;
  handled_by_name: string | null;
  result_label: string | null;
  effective_on: string | null;
  approval_reference: string | null;
  documents: DocumentChecklist;
  details: ChangeRequestWorkspaceDetail[];
};

export type DocumentPreparationResponse = {
  document_id: string;
  document_variant_id: string;
  generation_run_id: string;
  generation_status: string;
  reused_generation_run: boolean;
  render_ready: boolean;
  template_render_ready: boolean;
  blocked_reasons: string[];
  selected_template: {
    family_code: string;
    logical_name: string;
    template_pattern: string;
    source_application: string;
    storage_scope: string;
    host_procedure: string;
    population_procedures: string[];
    notes: string | null;
  };
  payload_used_fields: string[];
  missing_registry_fields: string[];
  unexpected_input_fields: string[];
  source_dependencies: Array<{
    source_family_code: string;
    dependency_type: string;
    required_bookmarks: string[];
    condition: string | null;
  }>;
  source_binary_requirements: Array<{
    source_document_id: string;
    source_document_version_id: string | null;
    source_family_code: string;
    readiness_status: string;
    detail: string;
    storage_root: string | null;
    folder_relative_path: string | null;
    exact_storage_root: string | null;
    exact_storage_relative_path: string | null;
    original_filename: string | null;
    required_bookmarks: string[];
    legacy_filename_prefix_hints: string[];
  }>;
  template_readiness: {
    template_definition_id: string | null;
    family_code: string;
    template_name: string;
    readiness_status: string;
    detail: string;
    storage_root: string | null;
    storage_relative_path: string | null;
    original_filename: string | null;
    checksum_sha256: string | null;
    scalar_replacement_mode: string | null;
    template_variant_key: string | null;
  };
  template_definition_id: string | null;
  template_binding_id: string | null;
  audit_event_id: string;
};

export type DocumentGenerationPrepareRequest = {
  family_code: string;
  case_id?: string | null;
  certificate_id?: string | null;
  business_eligibility_certificate_id?: string | null;
  change_request_id?: string | null;
  gxp_type?: string | null;
  legacy_mode?: string | null;
  storage_scope?: string | null;
  language_code?: string;
  idempotency_key?: string | null;
  payload: Record<string, string>;
  payload_notes?: string | null;
  strict_payload?: boolean;
};

export type DocumentRenderResponse = {
  document_id: string;
  document_variant_id: string;
  document_version_id: string;
  generation_run_id: string;
  generation_status: string;
  output_storage_root: string;
  output_storage_relative_path: string;
  output_original_filename: string;
  checksum_sha256: string;
  byte_size: number;
  scalar_replacement_mode: string;
  template_variant_key: string | null;
  replaced_bookmarks: string[];
  replaced_table_regions: string[];
  replaced_parts: string[];
  audit_event_id: string;
};

export type DocumentGenerationRunStatus = {
  generation_run_id: string;
  document_id: string;
  template_binding_id: string | null;
  template_definition_id: string | null;
  output_document_version_id: string | null;
  status: string;
  source_application: string | null;
  requested_by_user_id: string | null;
  input_payload_redacted: Record<string, string> | null;
  error_summary: string | null;
  idempotency_key: string | null;
  source_dependencies: Array<{
    source_family_code: string;
    dependency_type: string;
    required_bookmarks: string[];
    condition: string | null;
  }>;
};

export type DocumentDetail = {
  document_id: string;
  family_code: string;
  document_type_code: string;
  title: string | null;
  legacy_entity_type: string | null;
  case_id: string | null;
  certificate_id: string | null;
  business_eligibility_certificate_id: string | null;
  change_request_id: string | null;
  variants: Array<{
    id: string;
    variant_type: string;
    language_code: string;
    is_active: boolean;
    versions: Array<{
      id: string;
      version_no: number;
      storage_binding_id: string | null;
      storage_root: string | null;
      storage_relative_path: string | null;
      original_filename: string | null;
      checksum_sha256: string | null;
      is_current: boolean;
      issued_on: string | null;
    }>;
  }>;
  generation_runs: DocumentGenerationRunStatus[];
};

export type StubAuthState = {
  username: string;
  role: "reader" | "inspector" | "manager" | "admin";
};

export type OidcSession = {
  token: string;
  email: string | null;
  name: string | null;
  subject: string | null;
  expires_at_epoch_seconds: number;
};
