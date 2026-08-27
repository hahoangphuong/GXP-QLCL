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
  last_inspection_code: string | null;
  current_state: string | null;
  current_certificate_number: string | null;
  current_certificate_expiry: string | null;
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
  address: string | null;
  province_name: string | null;
  gxp_types: string[];
  selected_gxp_type: string | null;
  current_state: string | null;
  primary_standard: string | null;
  current_certificate_number: string | null;
  current_certificate_expiry: string | null;
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
